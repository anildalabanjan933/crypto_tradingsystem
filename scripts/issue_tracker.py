#!/usr/bin/env python3
"""
scripts/issue_tracker.py

Standalone, read-only, background issue tracker.
Zero changes to any bot/engine/order_manager/dashboard file - this
script only READS existing logs/CSVs and calls read-only exchange
GET endpoints (get_position()). It never places, cancels, or modifies
any order, and never writes to any file this script did not itself
create under logs/issue_tracker_*.

Launch (same pattern as flipfix_watch / reconcile_watch):
    screen -dmS issue_tracker bash -c \
      "cd ~/crypto_trading_system && source .env && .venv/bin/python3 scripts/issue_tracker.py >> logs/issue_tracker_stdout.log 2>&1"
"""

import os
import sys
import csv
import time
import glob
import hmac
import hashlib
import logging
import datetime as dt

import requests
import pandas as pd

sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

from engine.order_manager import OrderManager

BOTS = ["S4", "S4V2", "S4V3"]

API_KEY_ENV = {
    "S4":     ("S4_API_KEY", "S4_API_SECRET"),
    "S4V2":   ("S4V2_API_KEY", "S4V2_API_SECRET"),
    "S4V3":   ("S4V3_API_KEY", "S4V3_API_SECRET"),
}

SIGNAL_CSV = {
    "S4":     "logs/signals_s4.csv",
    "S4V2":   "logs/signals_s4v2.csv",
    "S4V3":   "logs/signals_s4v3.csv",
}

LIVE_LOG = {
    "S4":     "logs/live_trading_s4.log",
    "S4V2":   "logs/live_trading_s4v2.log",
    "S4V3":   "logs/live_trading_s4v3.log",
}

TF_MIN = {"S4": 120, "S4V2": 30, "S4V3": 240}

BT_CSV_PATTERN = {
    "S4":     "output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv",
    "S4V2":   "output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv",
    "S4V3":   "output/trade_log_RenkoSMIIOCrossV3Strategy_BTCUSD_*.csv",
}

PRODUCT_ID = 84
INR_RATE = 84.0
CONTRACT_MULT = 100 * 0.001

POLL_INTERVAL_SEC = 45
LOOKBACK_DAYS = 2
ORPHAN_BUFFER_MIN = 60

TRADES_CSV   = "logs/issue_tracker_trades.csv"
EVENTS_CSV   = "logs/issue_tracker_events.csv"
SUMMARY_TXT  = "logs/issue_tracker_summary.txt"
REPORT_TXT   = "logs/issue_tracker_report.txt"
HEARTBEAT    = "logs/issue_tracker_heartbeat.txt"

TRADES_FIELDS = [
    "date", "bot", "entry_ts", "exit_ts", "direction",
    "entry_slip_$", "entry_slip_tag", "exit_slip_$", "exit_slip_tag",
    "bt_lv_pnl_gap_$", "flip_yn", "flip_damage_$", "missed_yn",
    "close_escalation_yn", "system_side_flag", "verdict",
]
EVENTS_FIELDS = ["timestamp", "bot", "event_type", "detail"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("logs/issue_tracker.log"), logging.StreamHandler()]
)
log = logging.getLogger("issue_tracker")

def _ensure_csv(path, fields):
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()

def _read_existing_rows_by_entry():
    rows = {}
    if not os.path.exists(TRADES_CSV):
        return rows
    try:
        with open(TRADES_CSV) as f:
            for r in csv.DictReader(f):
                rows[(r.get("bot"), r.get("entry_ts"))] = r
    except Exception as e:
        log.warning(f"Could not read existing trades CSV: {e}")
    return rows

def _update_trade_row(bot, entry_ts, new_row):
    if not os.path.exists(TRADES_CSV):
        _append_trade_row(new_row)
        return
    rows = []
    updated = False
    try:
        with open(TRADES_CSV) as f:
            for r in csv.DictReader(f):
                if r.get("bot") == bot and r.get("entry_ts") == str(entry_ts):
                    rows.append(new_row)
                    updated = True
                else:
                    rows.append(r)
    except Exception as e:
        log.warning(f"Could not read existing trades CSV for update: {e}")
        _append_trade_row(new_row)
        return
    if not updated:
        rows.append(new_row)
    with open(TRADES_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRADES_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

def _append_trade_row(row):
    _ensure_csv(TRADES_CSV, TRADES_FIELDS)
    with open(TRADES_CSV, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=TRADES_FIELDS).writerow(row)

def _append_event(bot, event_type, detail):
    _ensure_csv(EVENTS_CSV, EVENTS_FIELDS)
    with open(EVENTS_CSV, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=EVENTS_FIELDS).writerow({
            "timestamp": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            "bot": bot, "event_type": event_type, "detail": detail,
        })

def _read_lines(path):
    try:
        with open(path) as f:
            return f.readlines()
    except Exception:
        return []

def _parse_bot_log_ts(line):
    try:
        return dt.datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S,%f")
    except Exception:
        return None

def _parse_ist_log_ts(line):
    try:
        ts_part = line.split(" IST")[0].strip()
        ist = dt.datetime.strptime(ts_part, "%d-%b-%Y %I:%M:%S %p")
        return ist - dt.timedelta(hours=5, minutes=30)
    except Exception:
        return None

def scan_system_side_flags(bot, entry_dt, exit_dt):
    window_start = entry_dt - dt.timedelta(minutes=10)
    window_end = (exit_dt if exit_dt else entry_dt) + dt.timedelta(minutes=10)
    flags = []
    close_escalation_yn = "N"

    for line in _read_lines("logs/flipfix_watch.log"):
        if f"[{bot}]" not in line:
            continue
        ts = _parse_ist_log_ts(line)
        if ts and window_start <= ts <= window_end:
            flags.append("FLIP_FIRE")
            _append_event(bot, "FLIP_FIRE", line.strip())
            break

    for line in _read_lines("logs/reconcile_watch_output.txt"):
        if f"[{bot}]" not in line or "mismatches=" not in line:
            continue
        ts = _parse_ist_log_ts(line)
        if ts and window_start <= ts <= window_end:
            flags.append("WS_REST_RECONCILE")
            _append_event(bot, "WS_REST_RECONCILE", line.strip())
            break

    for line in _read_lines(LIVE_LOG.get(bot, "")):
        ts = _parse_bot_log_ts(line)
        if not ts or not (window_start <= ts <= window_end):
            continue
        if "[STARTUP]" in line and "Bot starting" in line:
            flags.append("BOT_RESTART")
            _append_event(bot, "BOT_RESTART", line.strip())
        if "CLOSE TIME CAP EXCEEDED" in line:
            flags.append("CLOSE_LOSS_CAP_STAGE")
            close_escalation_yn = "Y"
            _append_event(bot, "CLOSE_LOSS_CAP_STAGE", line.strip())
        if "CLOSE FAILED AFTER" in line:
            flags.append("CLOSE_FAILED_MANUAL_REQUIRED")
            close_escalation_yn = "Y"
            _append_event(bot, "CLOSE_FAILED_MANUAL_REQUIRED", line.strip())

    for line in _read_lines("logs/renko_state_engine.log"):
        if "[ENGINE] Renko State Engine starting" not in line:
            continue
        ts = _parse_ist_log_ts(line)
        if ts and window_start <= ts <= window_end:
            flags.append("ENGINE_RESTART")
            _append_event(bot, "ENGINE_RESTART", line.strip())
            break

    return ("|".join(dict.fromkeys(flags)), close_escalation_yn)

_FILLS_CACHE = {}
_FILLS_CACHE_TTL = 30

def fetch_fills(bot, window_hours=48):
    now = time.time()
    ck = (bot, window_hours)
    cached = _FILLS_CACHE.get(ck)
    if cached and (now - cached[0]) < _FILLS_CACHE_TTL:
        return cached[1]

    key_env, sec_env = API_KEY_ENV.get(bot, (None, None))
    k = os.environ.get(key_env or "", "")
    s = os.environ.get(sec_env or "", "")
    if not k or not s:
        return []

    base = "https://cdn-ind.testnet.deltaex.org"
    path = "/v2/fills"
    start = int((now - window_hours * 3600) * 1e6)
    end = int((now + 300) * 1e6)
    all_fills = []
    after = None
    for _page in range(1, 50):
        ts = str(int(time.time()))
        params = {"product_id": PRODUCT_ID, "page_size": 50, "start_time": start, "end_time": end}
        if after:
            params["after"] = after
        qs = "&".join(f"{a}={b}" for a, b in sorted(params.items()))
        msg = "GET" + ts + path + "?" + qs
        sig = hmac.new(s.encode(), msg.encode(), hashlib.sha256).hexdigest()
        hdr = {"api-key": k, "timestamp": ts, "signature": sig}
        try:
            r = requests.get(f"{base}{path}?{qs}", headers=hdr, timeout=10)
            d = r.json()
            if not d.get("success"):
                break
            page = d.get("result", [])
            if not page:
                break
            all_fills.extend(page)
            meta = d.get("meta", {})
            after = meta.get("after")
            if not after:
                break
        except Exception as e:
            log.warning(f"[{bot}] fetch_fills failed: {e}")
            break

    _FILLS_CACHE[ck] = (now, all_fills)
    return all_fills

def pair_fills(fills):
    fills_sorted = sorted(fills, key=lambda f: f.get("created_at", ""))
    queue = []
    pairs = []
    baseline = 0.0
    for f in fills_sorted:
        side = str(f.get("side", "")).upper()
        size = float(f.get("size", 0) or 0)
        if size <= 0:
            continue
        price = float(f.get("price", 0) or 0)
        ftime = f.get("created_at", "")
        commission = abs(float(f.get("commission", 0) or 0))
        comm_per_unit = commission / size if size else 0.0
        meta = f.get("meta_data", {}) or {}
        new_pos = meta.get("new_position", {}) or {}
        raw_cumulative = float(new_pos.get("realized_pnl", 0) or 0)
        pos_size_after = new_pos.get("size", None)
        realized_pnl = raw_cumulative - baseline

        avail_opposite = sum(q["remaining"] for q in queue if q["side"] != side)
        closed_qty = min(size, avail_opposite)
        remaining_to_close = closed_qty

        while remaining_to_close > 1e-9 and queue and queue[0]["side"] != side:
            head = queue[0]
            match_size = min(remaining_to_close, head["remaining"])
            frac = (match_size / closed_qty) if closed_qty > 1e-9 else 0.0
            chunk_pnl = realized_pnl * frac
            _dir = "LONG" if head["side"] == "BUY" else "SHORT"
            pairs.append({
                "dir": _dir, "entry_ts_raw": head["time"], "exit_ts_raw": ftime,
                "entry_p": head["price"], "exit_p": price, "lot": match_size,
                "charges": comm_per_unit * match_size + head["comm_per_unit"] * match_size,
                "pnl_usd": chunk_pnl,
            })
            head["remaining"] -= match_size
            remaining_to_close -= match_size
            if head["remaining"] <= 1e-9:
                queue.pop(0)

        opening_qty = size - closed_qty
        if opening_qty > 1e-9 and pos_size_after != 0:
            queue.append({"remaining": opening_qty, "price": price, "time": ftime,
                          "side": side, "comm_per_unit": comm_per_unit})
        baseline = 0.0 if pos_size_after == 0 else raw_cumulative
    return pairs

def get_live_rows(bot, from_date, to_date):
    window_hours = max(24, (dt.datetime.utcnow().date() - from_date).days * 24 + 48)
    fills = fetch_fills(bot, window_hours)
    if not fills:
        return []
    pairs = pair_fills(fills)
    out = []
    for p in pairs:
        try:
            entry_date = pd.Timestamp(p["entry_ts_raw"]).date()
        except Exception:
            continue
        if from_date <= entry_date <= to_date:
            out.append(p)
    return out

def get_bt_rows(bot, from_date, to_date):
    pattern = BT_CSV_PATTERN.get(bot)
    if not pattern:
        return []
    files = sorted(glob.glob(pattern), reverse=True)
    if not files:
        return []
    try:
        dfc = pd.read_csv(files[0])
    except Exception as e:
        log.warning(f"[{bot}] BT CSV read failed: {e}")
        return []

    dfc["entry_datetime"] = pd.to_datetime(dfc["entry_datetime"])
    dfc["exit_datetime"] = pd.to_datetime(dfc["exit_datetime"])
    dfc = dfc[
        ((dfc["entry_datetime"].dt.date >= from_date) & (dfc["entry_datetime"].dt.date <= to_date)) |
        ((dfc["exit_datetime"].dt.date >= from_date) & (dfc["exit_datetime"].dt.date <= to_date))
    ]
    rows = []
    for _, r in dfc.iterrows():
        pnl_inr = float(r.get("net_pnl_inr", 0))
        net_pnl_inr = pnl_inr - (max(pnl_inr, 0) * 0.10)
        rows.append({
            "dir": str(r.get("direction", "")).upper(),
            "entry_ts_raw": str(r.get("entry_datetime", "")),
            "exit_ts_raw": str(r.get("exit_datetime", "")),
            "entry_p": float(r.get("entry_price", 0)),
            "exit_p": float(r.get("exit_price", 0)),
            "net_pnl_inr": net_pnl_inr,
        })
    return rows

def _offset_bt_ts(raw, bot):
    try:
        tf = TF_MIN.get(bot, 0)
        t = dt.datetime.fromisoformat(str(raw).replace("T", " "))
        t_off = t + dt.timedelta(minutes=tf)
        if t_off > dt.datetime.utcnow():
            return raw
        return t_off
    except Exception:
        return None

def pair_bt_lv(bt_rows, lv_rows, bot):
    window = pd.Timedelta(minutes=TF_MIN.get(bot, 120) + 15)
    lv_used = set()
    matched = []
    for bt in bt_rows:
        bt_entry_close = _offset_bt_ts(bt["entry_ts_raw"], bot)
        if bt_entry_close is None:
            continue
        best, best_diff = None, None
        for i, lv in enumerate(lv_rows):
            if i in lv_used:
                continue
            try:
                lv_entry = pd.Timestamp(lv["entry_ts_raw"])
                if lv_entry.tzinfo is not None:
                    lv_entry = lv_entry.tz_localize(None)
            except Exception:
                continue
            if lv["dir"] != bt["dir"]:
                continue
            diff = abs((lv_entry - bt_entry_close).total_seconds())
            if diff <= window.total_seconds() and (best_diff is None or diff < best_diff):
                best, best_diff = i, diff
        if best is not None:
            lv_used.add(best)
            matched.append((bt, lv_rows[best]))
        else:
            matched.append((bt, None))
    missed_lv = [lv for i, lv in enumerate(lv_rows) if i not in lv_used]
    return matched, missed_lv

def compute_slip(bt_p, lv_p, direction):
    if bt_p is None or lv_p is None or bt_p == 0:
        return 0.0, "-"
    signed = (bt_p - lv_p) if direction == "LONG" else (lv_p - bt_p)
    tag = "FAVORABLE" if signed >= 0 else "UNFAVORABLE"
    return round(abs(signed) * CONTRACT_MULT, 2), tag

FLIP_DAMAGE_NORMAL_CEILING = 20.0  # 2x documented $8-10/side target - normal flip
                                    # stacks entry+exit slip, so up to ~$20 combined
                                    # is ordinary double-slip, not a system fault
_ANOMALY_TAGS = {"BOT_RESTART", "ENGINE_RESTART", "CLOSE_LOSS_CAP_STAGE", "CLOSE_FAILED_MANUAL_REQUIRED"}

def build_verdict(system_flag, close_escalation_yn, missed_yn, flip_yn, flip_damage=0.0):
    _flags = set(f for f in system_flag.split("|") if f)
    if close_escalation_yn == "Y" or (_flags & _ANOMALY_TAGS):
        return "SYSTEM-SIDE"
    if flip_yn == "Y" and flip_damage > FLIP_DAMAGE_NORMAL_CEILING:
        return "SYSTEM-SIDE"
    if missed_yn == "OPEN":
        return "OPEN-PENDING"
    if missed_yn == "Y":
        return "UNEXPLAINED"
    return "MARKET-SIDE"

def check_orphan_stuck_pending(bot):
    sig_path = SIGNAL_CSV.get(bot)
    if not sig_path or not os.path.exists(sig_path):
        return
    try:
        with open(sig_path) as f:
            rows = list(csv.reader(f))
    except Exception:
        return
    if not rows:
        return
    last = rows[-1]
    if len(last) < 3 or last[1] != "PENDING":
        return

    entry_ts_str = last[0]
    try:
        entry_ts = dt.datetime.strptime(entry_ts_str, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return

    tf = TF_MIN.get(bot, 120)
    age_min = (dt.datetime.utcnow() - entry_ts).total_seconds() / 60
    if age_min <= (tf + ORPHAN_BUFFER_MIN):
        return

    key_env, sec_env = API_KEY_ENV.get(bot, (None, None))
    k = os.environ.get(key_env or "", "")
    s = os.environ.get(sec_env or "", "")
    if not k or not s:
        return
    try:
        om = OrderManager(k, s, testnet=True)
        pos = om.get_position()
    except Exception as e:
        log.warning(f"[{bot}] orphan check get_position failed: {e}")
        return

    if not pos.get("success"):
        return

    exch_size = pos.get("size", 0)
    csv_dir = last[2]

    if exch_size == 0:
        _append_event(bot, "STUCK_PENDING",
                       f"CSV shows open ({csv_dir}) entry_ts={entry_ts_str}, "
                       f"exchange FLAT - orphaned row, age={age_min:.0f}min")
    else:
        exch_dir = "long" if exch_size > 0 else "short"
        if exch_dir != csv_dir:
            _append_event(bot, "ORPHAN_POSITION",
                           f"CSV shows {csv_dir} entry_ts={entry_ts_str}, "
                           f"exchange shows {exch_dir} size={exch_size} - direction mismatch")

def _is_live_still_open(bot, bt_entry_ts_raw, bt_dir):
    """Read-only check: does this BT entry correspond to a live trade that is
    still genuinely open (PENDING in local signals CSV), not actually missed?
    No API call - reads the same local signals_*.csv the live bot itself writes."""
    path = SIGNAL_CSV.get(bot)
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path, "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
    except Exception:
        return False
    if not lines:
        return False
    last = lines[-1]
    parts = last.split(",")
    if len(parts) < 3:
        return False
    sig_entry_ts, sig_exit_ts, sig_dir = parts[0], parts[1], parts[2]
    if sig_exit_ts.strip().upper() != "PENDING":
        return False
    if sig_dir.strip().lower() != str(bt_dir).lower():
        return False
    try:
        bt_ts = pd.Timestamp(str(bt_entry_ts_raw).replace("T", " "))
        sig_ts = pd.Timestamp(sig_entry_ts.strip().replace("T", " "))
        return abs((bt_ts - sig_ts).total_seconds()) < 3600
    except Exception:
        return False

def process_bot(bot, from_date, to_date, existing_rows):
    bt_rows = get_bt_rows(bot, from_date, to_date)
    lv_rows = get_live_rows(bot, from_date, to_date)
    matched, missed_lv = pair_bt_lv(bt_rows, lv_rows, bot)

    for bt, lv in matched:
        entry_ts = bt["entry_ts_raw"]
        exit_ts = bt["exit_ts_raw"]
        entry_key = (bot, entry_ts)
        prev_row = existing_rows.get(entry_key)
        if prev_row is not None and prev_row.get("exit_ts") == str(exit_ts) and prev_row.get("verdict") not in ("UNEXPLAINED","OPEN-PENDING"):
            continue

        missed_yn = "Y" if lv is None else "N"
        if missed_yn == "Y":
            if _is_live_still_open(bot, entry_ts, bt["dir"]):
                missed_yn = "OPEN"
                _append_event(bot, "OPEN_LIVE_TRADE", f"BT entry {entry_ts} matches still-open live position - not missed")
            else:
                _append_event(bot, "ENTRY_MISMATCH", f"BT entry {entry_ts} has no matched LV fill")

        entry_slip, entry_tag = (0.0, "-")
        exit_slip, exit_tag = (0.0, "-")
        pnl_gap = 0.0
        if lv is not None:
            entry_slip, entry_tag = compute_slip(bt["entry_p"], lv["entry_p"], bt["dir"])
            exit_slip, exit_tag = compute_slip(bt["exit_p"], lv.get("exit_p"), bt["dir"])
            pnl_gap = round(bt["net_pnl_inr"] - (lv.get("pnl_usd", 0) * INR_RATE - lv.get("charges", 0) * INR_RATE), 2)

        try:
            entry_dt = dt.datetime.fromisoformat(str(entry_ts).replace("T", " ").split(".")[0])
        except Exception:
            entry_dt = dt.datetime.utcnow()
        try:
            exit_dt = dt.datetime.fromisoformat(str(exit_ts).replace("T", " ").split(".")[0]) if exit_ts and str(exit_ts) != "nan" else None
        except Exception:
            exit_dt = None

        system_flag, close_escalation_yn = scan_system_side_flags(bot, entry_dt, exit_dt)
        flip_yn = "Y" if "FLIP_FIRE" in system_flag else "N"
        flip_damage = round(entry_slip + exit_slip, 2) if flip_yn == "Y" else 0.0

        verdict = build_verdict(system_flag, close_escalation_yn, missed_yn, flip_yn, flip_damage)

        row = {
            "date": str(entry_ts)[:10], "bot": bot, "entry_ts": entry_ts, "exit_ts": exit_ts,
            "direction": bt["dir"], "entry_slip_$": entry_slip, "entry_slip_tag": entry_tag,
            "exit_slip_$": exit_slip, "exit_slip_tag": exit_tag, "bt_lv_pnl_gap_$": pnl_gap,
            "flip_yn": flip_yn, "flip_damage_$": flip_damage, "missed_yn": missed_yn,
            "close_escalation_yn": close_escalation_yn, "system_side_flag": system_flag, "verdict": verdict,
        }
        if prev_row is not None:
            _update_trade_row(bot, entry_ts, row)
        else:
            _append_trade_row(row)
        existing_rows[entry_key] = row

    for lv in missed_lv:
        _append_event(bot, "UNMATCHED_LV_ENTRY",
                       f"LV fill entry={lv.get('entry_ts_raw')} dir={lv.get('dir')} has no matched BT row")

    check_orphan_stuck_pending(bot)

def recompute_summary_and_report():
    if not os.path.exists(TRADES_CSV):
        return
    try:
        df = pd.read_csv(TRADES_CSV)
    except Exception:
        return
    if df.empty:
        return

    fav = df.apply(lambda r: r["entry_slip_$"] if r["entry_slip_tag"] == "FAVORABLE" else 0, axis=1).sum() + \
          df.apply(lambda r: r["exit_slip_$"] if r["exit_slip_tag"] == "FAVORABLE" else 0, axis=1).sum()
    unfav = df.apply(lambda r: r["entry_slip_$"] if r["entry_slip_tag"] == "UNFAVORABLE" else 0, axis=1).sum() + \
            df.apply(lambda r: r["exit_slip_$"] if r["exit_slip_tag"] == "UNFAVORABLE" else 0, axis=1).sum()
    total_gap = df["bt_lv_pnl_gap_$"].sum()
    biggest_idx = df["bt_lv_pnl_gap_$"].abs().idxmax()
    biggest = df.loc[biggest_idx]

    with open(SUMMARY_TXT, "w") as f:
        f.write(f"Issue Tracker Summary - updated {dt.datetime.utcnow().isoformat()}Z\n")
        f.write(f"Total favorable $ : {fav:,.2f}\n")
        f.write(f"Total unfavorable $ : {unfav:,.2f}\n")
        f.write(f"Total BT-LV PnL gap $ : {total_gap:,.2f}\n")
        f.write(f"Biggest single damage event : {biggest['bot']} {biggest['entry_ts']} "
                f"gap=${biggest['bt_lv_pnl_gap_$']:,.2f} verdict={biggest['verdict']}\n")

    unexplained = df[df["verdict"] == "UNEXPLAINED"]
    with open(REPORT_TXT, "w") as f:
        f.write(f"=== ISSUE TRACKER REPORT - {dt.datetime.utcnow().isoformat()}Z ===\n\n")
        f.write(f"Total trades tracked : {len(df)}\n")
        f.write(f"SYSTEM-SIDE : {(df['verdict']=='SYSTEM-SIDE').sum()}\n")
        f.write(f"MARKET-SIDE : {(df['verdict']=='MARKET-SIDE').sum()}\n")
        f.write(f"UNEXPLAINED : {len(unexplained)}  <-- only these need manual review\n\n")
        if not unexplained.empty:
            f.write("--- UNEXPLAINED rows ---\n")
            f.write(unexplained.to_string(index=False))
            f.write("\n\n")
        f.write("--- Running totals ---\n")
        f.write(open(SUMMARY_TXT).read())

def main():
    log.info("Issue Tracker started - read-only, zero writes outside logs/issue_tracker_*")
    _ensure_csv(TRADES_CSV, TRADES_FIELDS)
    _ensure_csv(EVENTS_CSV, EVENTS_FIELDS)
    while True:
        try:
            with open(HEARTBEAT, "w") as f:
                f.write(str(time.time()))
        except Exception as e:
            log.warning(f"Heartbeat write failed: {e}")

        try:
            to_date = dt.datetime.utcnow().date()
            from_date = to_date - dt.timedelta(days=LOOKBACK_DAYS)
            existing_rows = _read_existing_rows_by_entry()
            for bot in BOTS:
                try:
                    process_bot(bot, from_date, to_date, existing_rows)
                except Exception as e:
                    log.error(f"[{bot}] process_bot failed: {e}", exc_info=True)
            recompute_summary_and_report()
        except Exception as e:
            log.error(f"Main loop error: {e}", exc_info=True)

        time.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":
    main()
