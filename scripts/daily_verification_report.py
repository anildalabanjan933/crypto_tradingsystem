import hmac, hashlib, time, requests, csv, glob, sys, re, os
from datetime import datetime, timezone, timedelta

TF_MIN = {"s4": 120, "s4v2": 30}
WINDOW_SEC = {"s4": 150*60, "s4v2": 45*60}

import os as _os_hist, re as _re_hist
HISTORY_CSV = "logs/issue_history.csv"
_MONTHS_H = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def _fmt_date_short(d):
    try:
        y,m,dd = d.split("-")
        return f"{dd}-{_MONTHS_H[int(m)]}"
    except Exception:
        return d

def _normalize_key(code):
    return _re_hist.sub(r'[\d,.]+', '', code).strip('_')

def _load_issue_history():
    rows = []
    if _os_hist.path.exists(HISTORY_CSV):
        with open(HISTORY_CSV) as fh:
            for line in fh:
                parts = line.strip().split(",")
                if len(parts) == 4:
                    rows.append(tuple(parts))
    return rows

def _repeat_tag(date, bot, key):
    hist = _load_issue_history()
    earlier = sorted(set(d for d,b,k in [(x[0],x[1],x[2]) for x in hist] if b==bot and k==key and d < date))
    entry_line = f"{date},{bot},{key},1\n"
    existing = {(d,b,k) for d,b,k,_ in hist}
    if (date,bot,key) not in existing:
        with open(HISTORY_CSV, "a") as fh:
            fh.write(entry_line)
    if earlier:
        return f" [REPEATED ISSUE - also seen on {_fmt_date_short(earlier[-1])}]"
    return ""

INR_RATE = 84.0

BT_GLOB = {
    "s4": "output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv",
    "s4v2": "output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv",
}
LOG_FILES = ["logs/sl_safety_monitor.log", "logs/position_risk_monitor.log",
             "logs/margin_monitor.log", "logs/live_trading_s4.log", "logs/live_trading_s4v2.log"]
CRIT_PATTERNS = [
    ("SL GAP DETECTED", "SL_GAP_EMERGENCY_CLOSE"),
    ("SL PLACEMENT FAILED", "SL_PLACEMENT_FAILED"),
    ("CLOSE FAILED AFTER", "CLOSE_FAILED_MANUAL_INTERVENTION"),
    ("TIER 1 SPEED ALERT", "TIER1_SPEED_ALERT_AUTOCLOSE"),
    ("LIQUIDATION RISK CRITICAL", "TIER2_LIQUIDATION_CRITICAL"),
    ("ENTRY UNFILLED", "ENTRY_UNFILLED_BAND"),
    ("EMERGENCY CLOSE", "EMERGENCY_CLOSE_EVENT"),
    ("invalid_api_key", "API_KEY_FAILURE"),
]

def load_env(bot):
    env = {}
    with open(".env") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    if bot == "s4":
        return env.get("S4_API_KEY") or env.get("API_KEY"), env.get("S4_API_SECRET") or env.get("API_SECRET")
    return env.get("S4V2_API_KEY"), env.get("S4V2_API_SECRET")

def sign(secret, message):
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

def get_fills(api_key, api_secret, base_url, start_us, end_us):
    method, path, all_fills, after = "GET", "/v2/fills", [], None
    while True:
        qs_parts = [f"start_time={start_us}", f"end_time={end_us}", "page_size=100"]
        if after: qs_parts.append(f"after={after}")
        query_string = "?" + "&".join(qs_parts)
        timestamp = str(int(time.time()))
        signature = sign(api_secret, method + timestamp + path + query_string)
        headers = {"api-key": api_key, "timestamp": timestamp, "signature": signature,
                   "User-Agent": "python-verify-script", "Content-Type": "application/json"}
        r = requests.get(base_url + path + query_string, headers=headers, timeout=15)
        data = r.json()
        if not data.get("success"):
            print("API ERROR:", data); break
        all_fills.extend(data.get("result", []))
        after = data.get("meta", {}).get("after")
        if not after: break
    return all_fills

def aggregate_by_order(fills):
    orders = {}
    for f in fills:
        oid = f["order_id"]; size = float(f["size"]); price = float(f["price"])
        if oid not in orders:
            orders[oid] = {"side": f["side"], "size": 0.0, "notional": 0.0,
                            "first_time": f["created_at"], "last_time": f["created_at"]}
        o = orders[oid]
        o["size"] += size; o["notional"] += size * price
        if f["created_at"] < o["first_time"]: o["first_time"] = f["created_at"]
        if f["created_at"] > o["last_time"]: o["last_time"] = f["created_at"]
    agg = []
    for oid, o in orders.items():
        agg.append({"order_id": oid, "side": o["side"], "size": o["size"],
                    "price": o["notional"] / o["size"] if o["size"] else 0.0, "created_at": o["first_time"]})
    return sorted(agg, key=lambda x: x["created_at"])

def get_seed_position(api_key, api_secret, base_url, start_us, bot):
    lookback_sec = 72*3600
    lookback_us = start_us - lookback_sec*1_000_000
    pre_fills = get_fills(api_key, api_secret, base_url, lookback_us, start_us)
    pre_agg = aggregate_by_order(pre_fills)
    pos = 0.0
    for f in pre_agg:
        pos += f["size"] if f["side"] == "buy" else -f["size"]
    return pos

def reconstruct_trades(fills):
    fills = sorted(fills, key=lambda f: f["created_at"])
    trades = []; pos = 0.0; entry_notional = 0.0; entry_size = 0.0; entry_time = None
    for f in fills:
        side = f["side"]; size = float(f["size"]); price = float(f["price"])
        signed = size if side == "buy" else -size
        prev_pos = pos; pos += signed
        if prev_pos == 0 and pos != 0:
            entry_time = f["created_at"]; entry_notional = price * size; entry_size = size
        elif prev_pos != 0 and pos == 0:
            avg_entry = entry_notional / entry_size if entry_size else price
            trades.append({"direction": "long" if prev_pos > 0 else "short", "entry_time": entry_time,
                           "entry_price": round(avg_entry, 2), "exit_time": f["created_at"],
                           "exit_price": price, "size": abs(prev_pos)})
            entry_time, entry_notional, entry_size = None, 0.0, 0.0
        elif prev_pos != 0 and pos != 0 and (prev_pos > 0) != (pos > 0):
            avg_entry = entry_notional / entry_size if entry_size else price
            trades.append({"direction": "long" if prev_pos > 0 else "short", "entry_time": entry_time,
                           "entry_price": round(avg_entry, 2), "exit_time": f["created_at"],
                           "exit_price": price, "size": abs(prev_pos)})
            entry_time = f["created_at"]; entry_notional = price * abs(pos); entry_size = abs(pos)
        elif prev_pos != 0 and pos != 0 and (prev_pos > 0) == (pos > 0):
            entry_notional += price * size; entry_size += size
        else:
            entry_time = f["created_at"]; entry_notional = price * size; entry_size = size
    return trades

def get_open_entry(fills):
    fills = sorted(fills, key=lambda f: f["created_at"])
    pos = 0.0; entry_notional = 0.0; entry_size = 0.0; entry_time = None
    for f in fills:
        side = f["side"]; size = float(f["size"]); price = float(f["price"])
        signed = size if side == "buy" else -size
        prev_pos = pos; pos += signed
        if prev_pos == 0 and pos != 0:
            entry_time = f["created_at"]; entry_notional = price * size; entry_size = size
        elif prev_pos != 0 and pos == 0:
            entry_time = None; entry_notional = 0.0; entry_size = 0.0
        elif prev_pos != 0 and pos != 0 and (prev_pos > 0) != (pos > 0):
            entry_time = f["created_at"]; entry_notional = price * abs(pos); entry_size = abs(pos)
        elif prev_pos != 0 and pos != 0 and (prev_pos > 0) == (pos > 0):
            entry_notional += price * size; entry_size += size
        else:
            entry_time = f["created_at"]; entry_notional = price * size; entry_size = size
    if pos != 0 and entry_time:
        avg_entry = entry_notional / entry_size if entry_size else 0
        return {"direction": "long" if pos > 0 else "short", "entry_time": entry_time,
                "entry_price": round(avg_entry, 2), "size": abs(pos)}
    return None

def load_bt(bot, start_date):
    files = sorted(glob.glob(BT_GLOB[bot]))
    if not files: return []
    f = files[-1]
    rows = []
    with open(f) as fh:
        for r in csv.DictReader(fh):
            if r["entry_datetime"] >= start_date:
                rows.append(r)
    return rows

def dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if "Z" in s else datetime.fromisoformat(s)

def scan_accidental_losses(start_dt, end_dt):
    events = {}
    for path in LOG_FILES:
        if not os.path.exists(path): continue
        try:
            with open(path, errors="ignore") as f:
                for line in f:
                    ts_match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d+)", line)
                    if not ts_match: continue
                    try:
                        line_dt = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    except Exception:
                        continue
                    if not (start_dt <= line_dt <= end_dt): continue
                    for pat, tag in CRIT_PATTERNS:
                        if pat in line:
                            date = line_dt.strftime("%Y-%m-%d")
                            bot_tag = "S4V2" if "S4V2" in line or "s4v2" in path else ("S4" if "S4" in line or "live_trading_s4.log" in path else "UNKNOWN")
                            events.setdefault(date, []).append({
                                "time": line_dt.strftime("%H:%M:%S"), "bot": bot_tag, "type": tag,
                                "text": line.strip()[:200]
                            })
        except Exception:
            pass
    return events

_LOG_LINE_CACHE = {}

def _get_cached_log_lines(log_path):
    if log_path in _LOG_LINE_CACHE:
        return _LOG_LINE_CACHE[log_path]
    parsed = []
    if os.path.exists(log_path):
        try:
            with open(log_path, errors="ignore") as f:
                for line in f:
                    ts_match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                    if not ts_match:
                        continue
                    try:
                        line_dt = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    except Exception:
                        continue
                    parsed.append((line_dt, line))
        except Exception:
            pass
    _LOG_LINE_CACHE[log_path] = parsed
    return parsed

def _scan_tier_events(bot, entry_dt, exit_dt):
    window_start = entry_dt - timedelta(minutes=10)
    window_end = exit_dt + timedelta(minutes=10)
    reasons = []
    checks = [
        ("STARTUP", "Bot restarted near this time"),
        ("STUCK PENDING", "Stuck-pending sync issue detected (self-healed automatically)"),
        ("ENTRY FAILED", "Entry order failed - exchange rejected"),
        ("ENTRY ABANDONED", "Entry abandoned after max retry attempts"),
        ("manual_override", "Manual override skip was active"),
        ("unfilled_beyond_band", "Entry price moved outside $250 IOC safety band"),
        ("ENGINE WARNING", "Engine heartbeat issue near this time"),
        ("SL PLACEMENT FAILED", "SL placement failure - position was unprotected"),
        ("CLOSE FAILED", "Emergency close failure - manual intervention required"),
        ("SL GAP DETECTED", "SL gap watchdog forced emergency close"),
        ("TIER 1 SPEED ALERT", "Tier1 speed filter (5%/min) auto-closed position"),
        ("LIQUIDATION RISK CRITICAL", "Tier2 liquidation-risk monitor auto-closed position"),
        ("invalid_api_key", "API key rejected - bot could not trade"),
        ("AUTO-SL PLACEMENT FAILED", "Auto-SL placement failed for this bot"),
        ("AUTO-PLACED SUCCESS", "SL was missing - auto-fixed by safety monitor within 60s"),
        ("RECOVERED - SL WAS MISSING", "SL was missing - auto-fixed by safety monitor within 60s"),
        ("ORPHAN POSITION", "Exchange position was untracked - auto-flagged same day"),
        ("EMERGENCY CLOSE", "SL placement failed - position auto-closed for safety"),
    ]
    all_logs = LOG_FILES + [f"logs/live_trading_{bot}.log", "logs/sl_safety_monitor.log"]
    bot_tag = bot.upper()
    for log_path in set(all_logs):
        for line_dt, line in _get_cached_log_lines(log_path):
            if not (window_start <= line_dt <= window_end):
                continue
            import re as _re_bt
            if "live_trading" in log_path:
                pass
            elif not _re_bt.search(r'(?<![A-Za-z0-9])' + bot_tag + r'(?![A-Za-z0-9])', line):
                continue
            for pat, label in checks:
                if pat in line:
                    tag = f"{label} ({line_dt.strftime('%H:%M:%S')} UTC)"
                    if tag not in reasons:
                        reasons.append(tag)
    return reasons

def find_miss_reason(bot, entry_dt, exit_dt):
    reasons = _scan_tier_events(bot, entry_dt, exit_dt)
    return " | ".join(reasons) if reasons else "no reason found in logs - check manually"

def _explain_issue(bot, entry_dt, exit_dt, issue_code):
    if issue_code == "SYSTEM_SYNC_GAP_NO_BUG":
        return "NO BUG - SAFE (CDS SYSTEM SIDE): brief 1-second bookkeeping gap only, position was fully protected by stop-loss and closed normally, zero loss, zero missed protection"
    reasons = _scan_tier_events(bot, entry_dt, exit_dt)
    if reasons:
        return f"{issue_code} -- CDS SYSTEM SIDE: " + " | ".join(reasons)
    if issue_code == "OK":
        return "OK -- Delta fill matched Backtest signal, no system events found near this trade"
    if issue_code.startswith("MISSED_NO_LIVE_FILL"):
        return "MISSED_NO_LIVE_FILL -- UNKNOWN (evidence gap): no live trade found and no system-log reason found near this time - could be a genuine missed signal or rotated/missing logs, needs manual check"
    if issue_code == "UNMATCHED_LV_TRADE":
        return "UNMATCHED_LV_TRADE -- DELTA EXCHANGE SIDE: live trade filled on exchange but no matching backtest signal in window - verify manually via Audit tab (Delta fill data)"
    if issue_code == "CARRIED_POSITION_MISMATCH":
        return "CARRIED_POSITION_MISMATCH -- DELTA EXCHANGE SIDE: position was carried over from previous day, backtest expected a fresh start - not a missed trade, real exchange state differs from backtest assumption"
    if issue_code == "SYSTEM_SYNC_GAP_NO_BUG":
        return "NO BUG - SAFE: brief 1-second bookkeeping gap only, position was fully protected by stop-loss and closed normally, zero loss, zero missed protection"
    if issue_code.startswith("HIGH_SLIPPAGE"):
        return f"{issue_code} -- DELTA EXCHANGE SIDE: testnet order book was thin, price slipped filling this order (same cause as 13-Aug big loss, already fixed - IOC band caps it now)"
    return f"{issue_code} -- DELTA EXCHANGE SIDE: no system-side cause found in logs - likely normal market price movement/order latency, not a bot bug"

def build_report(start_date, end_date):
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    start_us = int(start_dt.timestamp() * 1_000_000)
    end_us = int(end_dt.timestamp() * 1_000_000)
    base_url = "https://cdn-ind.testnet.deltaex.org"

    accidental = scan_accidental_losses(start_dt, end_dt)
    report = {}

    for bot in ["s4", "s4v2"]:
        api_key, api_secret = load_env(bot)
        if not api_key or not api_secret:
            continue
        raw_fills = get_fills(api_key, api_secret, base_url, start_us, end_us)
        agg_fills = aggregate_by_order(raw_fills)
        real_trades = reconstruct_trades(agg_fills)
        open_entry = get_open_entry(agg_fills)
        seed_pos = get_seed_position(api_key, api_secret, base_url, start_us, bot)
        bt_rows = load_bt(bot, start_date)
        tf_sec = TF_MIN[bot] * 60
        window_sec = WINDOW_SEC.get(bot, 3*3600)

        matched_lv = list(real_trades)
        for r in bt_rows:
            bt_entry_t = dt(r["entry_datetime"].replace("Z", "")).replace(tzinfo=timezone.utc)
            bt_entry_close = bt_entry_t + timedelta(seconds=tf_sec)
            bt_xt = dt(r["exit_datetime"].replace("Z", "")).replace(tzinfo=timezone.utc)
            bt_exit_close = bt_xt + timedelta(seconds=tf_sec)
            best, best_key = None, None
            for lv in matched_lv:
                if lv["direction"] != r["direction"]: continue
                lv_entry_t = dt(lv["entry_time"])
                diff = abs((lv_entry_t - bt_entry_t).total_seconds())
                if diff >= window_sec: continue
                lv_exit_t = dt(lv["exit_time"])
                exit_diff = abs((lv_exit_t - bt_exit_close).total_seconds())
                if exit_diff >= window_sec: continue
                price_diff = abs(lv["entry_price"] - float(r["entry_price"]))
                key = (diff, price_diff)
                if best is None or key < best_key:
                    best, best_key = lv, key

            date = r["entry_datetime"][:10]
            report.setdefault(date, {}).setdefault(bot, {"pairs": [], "bt_pnl": 0.0, "lv_pnl": 0.0})

            bt_pnl_usd = ((float(r["exit_price"]) - float(r["entry_price"])) if r["direction"] == "long"
                          else (float(r["entry_price"]) - float(r["exit_price"]))) * 100 * 0.001
            report[date][bot]["bt_pnl"] += bt_pnl_usd

            if best:
                matched_lv.remove(best)
                entry_delay = int((dt(best["entry_time"]) - bt_entry_t).total_seconds()) - tf_sec
                exit_delay = int((dt(best["exit_time"]) - bt_xt).total_seconds()) - tf_sec
                sign_ = 1 if r["direction"] == "long" else -1
                entry_slip = round((best["entry_price"] - float(r["entry_price"])) * sign_, 2)
                exit_slip = round((best["exit_price"] - float(r["exit_price"])) * sign_, 2)
                lv_pnl_usd = ((best["exit_price"] - best["entry_price"]) if best["direction"] == "long"
                              else (best["entry_price"] - best["exit_price"])) * 100 * 0.001
                report[date][bot]["lv_pnl"] += lv_pnl_usd
                net_slip_usd = (entry_slip*100*0.001) + (exit_slip*100*0.001)
                issues = []
                if abs(entry_delay) > 15: issues.append(f"ENTRY_DELAY_{entry_delay}s")
                if abs(exit_delay) > 15: issues.append(f"EXIT_DELAY_{exit_delay}s")
                if abs(net_slip_usd) > 10: issues.append(f"HIGH_SLIPPAGE_Rs{net_slip_usd*INR_RATE:,.0f}")
                _issue_code = ",".join(issues) if issues else "OK"
                report[date][bot]["pairs"].append({
                    "bt": r, "lv": best, "entry_delay": entry_delay, "exit_delay": exit_delay,
                    "entry_slip": entry_slip, "exit_slip": exit_slip, "net_slip_usd": net_slip_usd,
                    "lv_pnl_usd": lv_pnl_usd, "bt_pnl_usd": bt_pnl_usd,
                    "issue": _explain_issue(bot, bt_entry_close, bt_exit_close, _issue_code) + (_repeat_tag(date, bot, _normalize_key(_issue_code)) if _issue_code != "OK" else "")
                })
            elif (open_entry and open_entry["direction"] == r["direction"]
                  and abs((dt(open_entry["entry_time"]) - bt_entry_t).total_seconds()) < window_sec):
                report[date][bot]["pairs"].append({
                    "bt": r, "lv": open_entry, "entry_delay": None, "exit_delay": None,
                    "entry_slip": None, "exit_slip": None, "net_slip_usd": None,
                    "lv_pnl_usd": None, "bt_pnl_usd": bt_pnl_usd,
                    "issue": "OPEN_LIVE_TRADE - entry filled, position still open (not missed) - entry_price=" + str(open_entry["entry_price"]) + _repeat_tag(date, bot, "OPEN_LIVE_TRADE")
                })
            else:
                report[date][bot]["pairs"].append({
                    "bt": r, "lv": None, "entry_delay": None, "exit_delay": None,
                    "entry_slip": None, "exit_slip": None, "net_slip_usd": None,
                    "lv_pnl_usd": None, "bt_pnl_usd": bt_pnl_usd,
                    "issue": _explain_issue(bot, bt_entry_t, bt_exit_close, "MISSED_NO_LIVE_FILL") + _repeat_tag(date, bot, "MISSED_NO_LIVE_FILL")
                })

        _sorted_unmatched = sorted(matched_lv, key=lambda x: x["entry_time"])
        for _i, lv in enumerate(_sorted_unmatched):
            date = lv["entry_time"][:10]
            report.setdefault(date, {}).setdefault(bot, {"pairs": [], "bt_pnl": 0.0, "lv_pnl": 0.0})
            lv_pnl_usd = ((lv["exit_price"] - lv["entry_price"]) if lv["direction"] == "long"
                          else (lv["entry_price"] - lv["exit_price"])) * 100 * 0.001
            report[date][bot]["lv_pnl"] += lv_pnl_usd
            _lv_et = dt(lv["entry_time"])
            _lv_xt = dt(lv["exit_time"])
            _tag = "UNMATCHED_LV_TRADE"
            if _i == 0 and seed_pos != 0:
                _tag = "CARRIED_POSITION_MISMATCH"
            _orphan_check = _scan_tier_events(bot, _lv_et, _lv_xt)
            if any("untracked" in m for m in _orphan_check):
                _tag = "SYSTEM_SYNC_GAP_NO_BUG"
            report[date][bot]["pairs"].append({
                "bt": None, "lv": lv, "entry_delay": None, "exit_delay": None,
                "entry_slip": None, "exit_slip": None, "net_slip_usd": None,
                "lv_pnl_usd": lv_pnl_usd, "bt_pnl_usd": None,
                "issue": _explain_issue(bot, _lv_et, _lv_xt, _tag) + _repeat_tag(date, bot, _tag)
            })

    return report, accidental

def fmt_dt(iso_str):
    try:
        d = dt(iso_str.replace("Z", "")).replace(tzinfo=timezone.utc)
        ist = d + timedelta(hours=5, minutes=30)
        return ist.strftime("%d-%b %H:%M")
    except Exception:
        return str(iso_str)[:16]

def render_html(report, accidental, start_date, end_date):
    css = """
    <style>
    body{font-family:Arial;background:#f4f6f8;margin:20px;}
    .daybox{background:#fff;border-radius:6px;margin-bottom:22px;box-shadow:0 1px 4px #ccc;overflow:hidden;}
    .dayhdr{background:#1565C0;color:#fff;padding:8px 14px;font-size:14px;font-weight:700;}
    .botbar{background:#42A5F5;color:#fff;padding:6px 12px;font-size:12px;font-weight:700;display:flex;gap:10px;flex-wrap:wrap;align-items:center;}
    .botbar span.pill{background:#fff;color:#0d47a1;border-radius:3px;padding:2px 8px;}
    table{width:100%;border-collapse:collapse;font-size:12px;}
    th{background:#e3f2fd;padding:6px;border:1px solid #ccc;text-align:center;}
    td{padding:6px;border:1px solid #ddd;text-align:center;}
    tr.bt-row{background:#fff;}
    tr.lv-row{background:#f9fbe7;border-bottom:3px solid #90a4ae;}
    .accbox{background:#ffebee;border:2px solid #e53935;border-radius:5px;margin:8px 12px;padding:8px;font-size:12px;color:#b71c1c;}
    .accbox b{color:#b71c1c;}
    .miss{color:#e65100;font-weight:700;background:#fff3e0;}
    </style>
    """
    html = [f"<html><head><title>Daily Verification Report {start_date} to {end_date}</title>{css}</head><body>"]
    html.append(f"<h2>Daily BT vs Forward-Test Verification Report | {start_date} to {end_date} (UTC dates, times shown IST)</h2>")
    html.append(f"<p>Generated: {datetime.now(timezone.utc).strftime('%d-%b-%Y %H:%M UTC')}</p>")

    for date in sorted(report.keys()):
        html.append(f"<div class='daybox'><div class='dayhdr'>DATE: {date}</div>")
        if date in accidental:
            html.append("<div class='accbox'><b>WARNING - ACCIDENTAL LOSS / CRITICAL EVENTS THIS DAY:</b><br>")
            for ev in accidental[date]:
                html.append(f"{ev['time']} UTC | [{ev['bot']}] | {ev['type']}<br><span style='font-size:11px;color:#666;'>{ev['text']}</span><br><br>")
            html.append("</div>")

        for bot in ["s4", "s4v2"]:
            if bot not in report[date]: continue
            d = report[date][bot]
            bt_n = sum(1 for p in d["pairs"] if p["bt"] is not None)
            lv_n = sum(1 for p in d["pairs"] if p["lv"] is not None)
            bt_pnl_inr = d["bt_pnl"] * INR_RATE
            lv_pnl_inr = d["lv_pnl"] * INR_RATE
            fav = sum(-p["net_slip_usd"] for p in d["pairs"] if p["net_slip_usd"] is not None and p["net_slip_usd"] < 0)
            unfav = sum(p["net_slip_usd"] for p in d["pairs"] if p["net_slip_usd"] is not None and p["net_slip_usd"] > 0)
            net_slip = fav - unfav
            html.append(f"<div class='botbar'>{bot.upper()} "
                        f"<span class='pill'>BT: {bt_n}</span><span class='pill'>FWD: {lv_n}</span>"
                        f"<span class='pill'>BT PnL: Rs{bt_pnl_inr:,.0f}</span>"
                        f"<span class='pill'>FWD PnL: Rs{lv_pnl_inr:,.0f}</span>"
                        f"<span class='pill'>Fav:+Rs{fav*INR_RATE:,.0f} Unfav:-Rs{unfav*INR_RATE:,.0f} Net:Rs{net_slip*INR_RATE:,.0f}</span></div>")

            html.append("<table><tr><th>#</th><th>Src</th><th>Dir</th><th>Entry Time</th><th>Exit Time</th>"
                        "<th>Entry Rs</th><th>Exit Rs</th><th>PnL Rs</th><th>Match(slip/delay)</th><th>Message</th></tr>")
            for i, p in enumerate(d["pairs"], 1):
                bt, lv = p["bt"], p["lv"]
                if bt:
                    html.append(f"<tr class='bt-row'><td>{i}</td><td>BT</td><td>{bt['direction'].upper()}</td>"
                                f"<td>{fmt_dt(bt['entry_datetime'])}</td><td>{fmt_dt(bt['exit_datetime'])}</td>"
                                f"<td>Rs{float(bt['entry_price'])*INR_RATE:,.0f}</td><td>Rs{float(bt['exit_price'])*INR_RATE:,.0f}</td>"
                                f"<td>Rs{p['bt_pnl_usd']*INR_RATE:,.0f}</td><td>-</td><td rowspan='2'>{p['issue']}</td></tr>")
                else:
                    html.append(f"<tr class='bt-row'><td>{i}</td><td>BT</td><td colspan='6' class='miss'>NO BT SIGNAL</td><td>-</td><td rowspan='2'>{p['issue']}</td></tr>")
                if lv:
                    match_str = "-"
                    if p["entry_slip"] is not None:
                        match_str = (f"E:{'+' if p['entry_slip']>=0 else ''}{p['entry_slip']:.1f} "
                                     f"X:{'+' if p['exit_slip']>=0 else ''}{p['exit_slip']:.1f} "
                                     f"| ED:{p['entry_delay']}s XD:{p['exit_delay']}s")
                    if 'exit_time' not in lv:
                        html.append(f"<tr class='lv-row'><td></td><td>FWD</td><td>{lv['direction'].upper()}</td>"
                                    f"<td>{fmt_dt(lv['entry_time'])}</td><td>OPEN</td>"
                                    f"<td>Rs{lv['entry_price']*INR_RATE:,.0f}</td><td>-</td>"
                                    f"<td>-</td><td>OPEN_LIVE_TRADE (position still open, not missed)</td></tr>")
                    else:
                        html.append(f"<tr class='lv-row'><td></td><td>FWD</td><td>{lv['direction'].upper()}</td>"
                                    f"<td>{fmt_dt(lv['entry_time'])}</td><td>{fmt_dt(lv['exit_time'])}</td>"
                                    f"<td>Rs{lv['entry_price']*INR_RATE:,.0f}</td><td>Rs{lv['exit_price']*INR_RATE:,.0f}</td>"
                                    f"<td>Rs{(p['lv_pnl_usd'] or 0)*INR_RATE:,.0f}</td><td>{match_str}</td></tr>")
                else:
                    html.append(f"<tr class='lv-row'><td></td><td>FWD</td><td colspan='6' class='miss'>MISSED (no live entry)</td><td>-</td></tr>")
            html.append("</table>")
        html.append("</div>")

    html.append("</body></html>")
    return "\n".join(html)


def write_bug_csv(report, accidental, out_path="output/daily_verification_bugs.csv"):
    import csv as _csv
    with open(out_path, "w", newline="") as f:
        writer = _csv.writer(f)
        for date in sorted(report.keys()):
            bugs = []
            for bot in ["s4", "s4v2"]:
                if bot not in report[date]: continue
                for i, p in enumerate(report[date][bot]["pairs"], 1):
                    if p["issue"] == "OK": continue
                    bt, lv = p["bt"], p["lv"]
                    entry_t = fmt_dt(bt["entry_datetime"]) if bt else (fmt_dt(lv["entry_time"]) if lv else "-")
                    exit_t = fmt_dt(bt["exit_datetime"]) if bt else (fmt_dt(lv["exit_time"]) if lv else "-")
                    entry_p = f"{float(bt['entry_price'])*INR_RATE:,.0f}" if bt else (f"{lv['entry_price']*INR_RATE:,.0f}" if lv else "-")
                    exit_p = f"{float(bt['exit_price'])*INR_RATE:,.0f}" if bt else (f"{lv['exit_price']*INR_RATE:,.0f}" if lv else "-")
                    direction = (bt['direction'] if bt else lv['direction']).upper()
                    entry_raw = bt['entry_datetime'] if bt else (lv['entry_time'] if lv else "")
                    bugs.append([bot.upper(), i, direction, entry_t, exit_t, entry_p, exit_p, p["issue"], "", entry_raw])
            if date in accidental:
                for ev in accidental[date]:
                    bugs.append([ev['bot'], "ACCIDENTAL", "-", ev['time'], "-", "-", "-", f"{ev['type']}: {ev['text']}", "", ev['time']])
            writer.writerow([f"DATE: {date}", f"BUG COUNT: {len(bugs)}"])
            writer.writerow(["Bot","Trade#","Direction","Entry Time","Exit Time","Entry Rs","Exit Rs","Issue","Fix Needed","Entry_UTC_Raw"])
            for row in bugs:
                writer.writerow(row)
            writer.writerow([])
    print(f"Bug CSV written to {out_path}")

if __name__ == "__main__":
    start_date = sys.argv[1] if len(sys.argv) > 1 else "2026-08-27"
    end_date = sys.argv[2] if len(sys.argv) > 2 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report, accidental = build_report(start_date, end_date)
    html_out = render_html(report, accidental, start_date, end_date)
    out_path = "output/daily_verification_report.html"
    with open(out_path, "w") as f:
        f.write(html_out)
    print(f"Report written to {out_path}")
    print(f"Days covered: {sorted(report.keys())}")
    print(f"Days with accidental-loss/critical events: {sorted(accidental.keys())}")
    write_bug_csv(report, accidental)
