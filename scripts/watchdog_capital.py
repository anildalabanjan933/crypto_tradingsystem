#!/usr/bin/env python3
"""
scripts/watchdog_capital.py  -  READ-ONLY capital-loss + stability watchdog.

Never places/cancels orders, never touches strategy, bot or engine files.
Polls Delta REST every POLL_SEC, writes PERMANENT CSVs (append-only, fsync'd,
never rotated/deleted) and sends a Telegram alert per new event.

  logs/watchdog_capital_loss_events.csv   (confirmed checks 1-3)
  logs/watchdog_system_stability.csv      (suggested extras, section B)

Run:  cd ~/crypto_tradingsystem && source .env && .venv/bin/python3 scripts/watchdog_capital.py
Heartbeat: logs/watchdog_capital_heartbeat.txt (wire into bot_watchdog.sh like the others)
"""
import os, sys, csv, json, time, hmac, hashlib, shutil
from datetime import datetime, timezone, timedelta
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass
try:  # reuse existing alert function - ADJUST import if your function lives elsewhere
    from engine.telegram_alert import send_alert
except Exception:
    send_alert = None

# ------------------------------ CONFIG ------------------------------
from scripts.cts_env import BASE_URL as _CTS_BASE_URL, PRODUCT_ID as _CTS_PRODUCT_ID
BASE = _CTS_BASE_URL                               # resolved via CTS_ENV
PRODUCT_ID = _CTS_PRODUCT_ID                      # resolved via CTS_ENV
SYMBOL = "BTCUSD"
POLL_SEC = 30
BOTS = {  # tf = candle minutes; sig = live signals CSV (bar-OPEN timestamps)
    "S4":   {"tf": 120, "sig": "logs/signals_s4.csv"},
    "S4V2": {"tf": 30,  "sig": "logs/signals_s4v2.csv"},
    "S4V3": {"tf": 240, "sig": "logs/signals_s4v3.csv"},
}
# Slippage thresholds in PRICE POINTS (adverse only). Env-overridable.
SLIP_WARN_PTS = float(os.environ.get("WD_SLIP_WARN_PTS", 100))  # ~$10 impact at 100 lots
SLIP_CRIT_PTS = float(os.environ.get("WD_SLIP_CRIT_PTS", 250))  # = your entry IOC band
MATCH_WINDOW_SEC = 20 * 60        # fill must be within 20 min of (signal ts + TF)
PARTIAL_GRACE_SEC = 120           # order older than this with unfilled>0 = partial
API_DOWN_STREAK = 3               # consecutive failed cycles before API_DOWN
EQUITY_DROP_PCT = float(os.environ.get("WD_EQUITY_DROP_PCT", 5.0))
EQUITY_WINDOW_SEC = 3600
DISK_FREE_MIN_PCT = 10.0
COOLDOWN = {"EQUITY_DROP": 3600, "DISK_LOW": 6 * 3600}

LOSS_CSV = os.path.join(ROOT, "logs", "watchdog_capital_loss_events.csv")
STAB_CSV = os.path.join(ROOT, "logs", "watchdog_system_stability.csv")
STATE_F = os.path.join(ROOT, "logs", "watchdog_capital_state.json")
HB_F = os.path.join(ROOT, "logs", "watchdog_capital_heartbeat.txt")
CSV_COLS = ["logged_at_utc", "bot", "event_type", "severity", "ref_id", "details"]


# ------------------------------ helpers ------------------------------
def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_ts(s):
    s = str(s).strip().replace("Z", "").replace("T", " ", 1)
    if "." in s:
        head, frac = s.split(".", 1)
        s = head + "." + frac[:6]
    return datetime.fromisoformat(s)


def log_event(path, bot, etype, sev, ref, details, alert=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(CSV_COLS)
        w.writerow([now_utc().isoformat(), bot, etype, sev, ref, details])
        f.flush()
        os.fsync(f.fileno())
    if alert and send_alert:
        try:
            send_alert(f"CTS [{bot}] {etype} ({sev}) - {details}")
        except Exception:
            pass
    print(f"{now_utc().isoformat()} [{bot}] {etype} {sev} {details}", flush=True)


def load_state():
    try:
        with open(STATE_F) as f:
            return json.load(f)
    except Exception:
        return {"seen": {}, "api_fail": {}, "api_down": {}, "cool": {}, "equity": {}}


def save_state(st):
    for b in st["seen"]:
        st["seen"][b] = st["seen"][b][-5000:]
    tmp = STATE_F + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.replace(tmp, STATE_F)


def api_get(path, params, key, secret):
    """Signed GET (same signing pattern as trade_audit_tab). Returns dict or None."""
    try:
        qs = "&".join(f"{a}={b}" for a, b in sorted(params.items()))
        ts = str(int(time.time()))
        sig = hmac.new(secret.encode(), ("GET" + ts + path + ("?" + qs if qs else "")).encode(),
                       hashlib.sha256).hexdigest()
        r = requests.get(f"{BASE}{path}" + ("?" + qs if qs else ""),
                         headers={"api-key": key, "timestamp": ts, "signature": sig,
                                  "User-Agent": "python-rest-client"}, timeout=10)
        d = r.json()
        return d if d.get("success") else None
    except Exception:
        return None


def fetch_fills(key, secret, hours):
    out, after = [], None
    now = int(time.time())
    for _ in range(20):
        p = {"product_id": PRODUCT_ID, "page_size": 50,
             "start_time": int((now - hours * 3600) * 1e6), "end_time": int((now + 300) * 1e6)}
        if after:
            p["after"] = after
        d = api_get("/v2/fills", p, key, secret)
        if d is None:
            return None if not out else out
        out.extend(d.get("result", []))
        after = (d.get("meta") or {}).get("after")
        if not after or not d.get("result"):
            break
    return out


def product_info():
    """tick_size / contract_value from product config - nothing hardcoded except last-resort fallback."""
    try:
        r = requests.get(f"{BASE}/v2/products/{SYMBOL}", timeout=10).json()["result"]
        return float(r.get("tick_size") or 0.5), float(r.get("contract_value") or 0.001)
    except Exception:
        return 0.5, 0.001


def load_refs(bot):
    """Reference (expected) prices from the bot's own signals CSV: (fill_time, price, side)."""
    cfg, refs = BOTS[bot], []
    try:
        with open(os.path.join(ROOT, cfg["sig"])) as f:
            for ln in f:
                p = ln.strip().split(",")
                if len(p) < 5:
                    continue
                try:
                    et = parse_ts(p[0]) + timedelta(minutes=cfg["tf"])
                    ep = float(p[4])
                    long_ = p[2].strip().lower() == "long"
                except Exception:
                    continue
                refs.append((et, ep, "BUY" if long_ else "SELL"))
                try:
                    xp = float(p[5]) if len(p) > 5 and p[5] else 0.0
                    if xp > 0:
                        xt = parse_ts(p[1]) + timedelta(minutes=cfg["tf"])
                        refs.append((xt, xp, "SELL" if long_ else "BUY"))
                except Exception:
                    pass
    except Exception:
        pass
    return refs


# ------------------------------ A. CONFIRMED CHECKS ------------------------------
def check_fills(bot, fills, seen, refs, tick, cval, first_run):
    by_order = {}
    for f in sorted(fills, key=lambda x: x.get("created_at", "")):
        fid = str(f.get("id"))
        oid = str(f.get("order_id"))
        by_order.setdefault(oid, []).append(f)
        if fid in seen:
            continue
        seen.append(fid)
        if first_run:
            continue
        meta = f.get("meta_data") or {}
        side = str(f.get("side", "")).upper()
        size = float(f.get("size", 0) or 0)
        price = float(f.get("price", 0) or 0)

        # 1. Liquidation / ADL (never our own SL)
        reason = str(f.get("fill_type") or f.get("reason") or meta.get("reason") or "normal").lower()
        if reason in ("liquidation", "adl"):
            log_event(LOSS_CSV, bot, "LIQUIDATION_OR_ADL_FILL", "CRITICAL", fid,
                      f"reason={reason} side={side} size={size} price={price} order={oid} "
                      f"- must never happen with healthy bot, check position + margin NOW")

        # 2/3. Abnormal slippage vs the bot's own expected (BT) price
        try:
            ft = parse_ts(f.get("created_at"))
            cands = [r for r in refs if r[2] == side and abs((ft - r[0]).total_seconds()) <= MATCH_WINDOW_SEC]
            if cands:
                t0, ref_p, _ = min(cands, key=lambda r: (abs((ft - r[0]).total_seconds()), abs(price - r[1])))
                adverse = (price - ref_p) if side == "BUY" else (ref_p - price)
                if adverse >= SLIP_WARN_PTS:
                    sev = "CRITICAL" if adverse >= SLIP_CRIT_PTS else "WARN"
                    log_event(LOSS_CSV, bot, "ABNORMAL_SLIPPAGE", sev, fid,
                              f"{side} fill {price:.2f} vs expected {ref_p:.2f} = {adverse:.2f} pts "
                              f"({adverse / tick:.0f} ticks, ~${adverse * size * cval:.2f} impact) "
                              f"size={size} - possible spike/thin liquidity")
        except Exception:
            pass

    # 3b. Thin liquidity: order ended with unfilled remainder (e.g. IOC 62/100 case)
    for oid, fl in by_order.items():
        key = "P:" + oid
        if key in seen:
            continue
        last = fl[-1]
        try:
            age = (now_utc() - parse_ts(last.get("created_at"))).total_seconds()
            unfilled = float((last.get("meta_data") or {}).get("order_unfilled_size", 0) or 0)
        except Exception:
            continue
        if age < PARTIAL_GRACE_SEC:
            continue
        seen.append(key)
        if unfilled > 1e-9 and not first_run:
            filled = sum(float(x.get("size", 0) or 0) for x in fl)
            log_event(LOSS_CSV, bot, "THIN_LIQUIDITY_PARTIAL_FILL", "WARN", oid,
                      f"filled={filled:.0f} unfilled={unfilled:.0f} side={last.get('side')} "
                      f"- position size may not match strategy lots")


# ------------------------------ B. SUGGESTED EXTRAS (system stability) ------------------------------
def check_api_health(bot, ok, st):
    fails = st["api_fail"].get(bot, 0)
    if ok:
        if st["api_down"].get(bot):
            log_event(STAB_CSV, bot, "API_RECOVERED", "INFO", "", f"API OK again after {fails} failed cycles")
        st["api_fail"][bot], st["api_down"][bot] = 0, False
    else:
        fails += 1
        st["api_fail"][bot] = fails
        if fails >= API_DOWN_STREAK and not st["api_down"].get(bot):
            st["api_down"][bot] = True
            log_event(STAB_CSV, bot, "API_DOWN", "CRITICAL", "",
                      f"{fails} consecutive failed/non-JSON fills calls (~{fails * POLL_SEC}s) - "
                      f"fill checks blind, testnet may be down")


def cooled(st, bot, name):
    k = f"{bot}:{name}"
    if time.time() - st["cool"].get(k, 0) < COOLDOWN[name]:
        return False
    st["cool"][k] = time.time()
    return True


def check_equity_drop(bot, key, secret, st):
    d = api_get("/v2/wallet/balances", {}, key, secret)
    if d is None:
        return
    try:
        res = d.get("result", [])
        row = next((r for r in res if str(r.get("asset_symbol", "")).upper() in ("USD", "USDT", "USDC")), res[0])
        eq = float(row.get("balance"))
    except Exception:
        return
    hist = [h for h in st["equity"].get(bot, []) if time.time() - h[0] <= EQUITY_WINDOW_SEC]
    hist.append([time.time(), eq])
    st["equity"][bot] = hist
    peak = max(h[1] for h in hist)
    if peak > 0 and (peak - eq) / peak * 100 >= EQUITY_DROP_PCT and cooled(st, bot, "EQUITY_DROP"):
        log_event(LOSS_CSV, bot, "EQUITY_DROP", "CRITICAL", "",
                  f"balance {peak:.2f} -> {eq:.2f} ({(peak - eq) / peak * 100:.1f}%) within "
                  f"{EQUITY_WINDOW_SEC // 60} min - big loss, unknown cause")


def check_disk(st):
    u = shutil.disk_usage(ROOT)
    pct = u.free / u.total * 100
    if pct < DISK_FREE_MIN_PCT and cooled(st, "SYS", "DISK_LOW"):
        log_event(STAB_CSV, "SYS", "DISK_LOW", "WARN", "", f"only {pct:.1f}% disk free - logs/CSV writes may fail")


# ------------------------------ main ------------------------------
def main():
    st = load_state()
    tick, cval = product_info()
    print(f"watchdog_capital started tick={tick} contract_value={cval}", flush=True)
    while True:
        try:
            for bot in BOTS:
                key = os.environ.get(f"{bot}_API_KEY", "")
                secret = os.environ.get(f"{bot}_API_SECRET", "")
                if not key or not secret:
                    continue
                first_run = bot not in st["seen"]
                seen = st["seen"].setdefault(bot, [])
                fills = fetch_fills(key, secret, 48 if first_run else 6)
                check_api_health(bot, fills is not None, st)
                if fills is not None:
                    check_fills(bot, fills, seen, load_refs(bot), tick, cval, first_run)
                    if first_run:
                        log_event(STAB_CSV, bot, "WATCHDOG_BASELINE", "INFO", "",
                                  f"seeded {len(fills)} existing fills, alerts start from now", alert=False)
                check_equity_drop(bot, key, secret, st)
            check_disk(st)
            save_state(st)
            with open(HB_F, "w") as f:
                f.write(str(int(time.time())))
        except Exception as e:
            print(f"loop error: {e}", flush=True)
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
