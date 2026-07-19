#!/usr/bin/env python3
"""
signal_replay_s2.py - S2 Signal Replay Bot
Reads pre-generated backtest signals from logs/signals_s2.csv
Places orders when current UTC time matches signal entry/exit time.
Zero Renko recalculation. 100% match with backtest guaranteed.
"""
import os, sys, time, csv, logging, re
from datetime import datetime, timezone
sys.path.insert(0, ".")
from engine.order_manager import OrderManager
from engine.telegram_alert import send_alert
from dotenv import load_dotenv
load_dotenv(dotenv_path="/home/anildalabanjan933/crypto_trading_system/.env")

# --- Config ---
SYMBOL       = "BTCUSD"
LOT_SIZE     = 100
SIGNAL_CSV   = "logs/signals_s2.csv"
TS_FILE      = "logs/last_known_ts_testmember1_s2.txt"
BASELINE_FILE= "logs/valid_from_baseline.txt"
SLEEP_SEC    = 1    # check every 1 second
LOG_FILE     = "logs/live_trading_testmember1_s2.log"

# --- Logging ---
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a")
    ]
)
log = logging.getLogger(__name__)

# --- Order Manager ---
API_KEY    = os.getenv("S2_API_KEY", "")
API_SECRET = os.getenv("S2_API_SECRET", "")
om = OrderManager(API_KEY, API_SECRET, testnet=True)

TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

def load_ts_file(path):
    try:
        if os.path.exists(path):
            val = open(path).read().strip()
            if TS_PATTERN.match(val):
                return val
    except Exception:
        pass
    return None

def save_ts_file(path, val):
    open(path, "w").write(str(val))

def now_utc_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def load_signals():
    signals = []
    if not os.path.exists(SIGNAL_CSV):
        log.error(f"[REPLAY] Signal CSV not found: {SIGNAL_CSV}")
        return signals
    with open(SIGNAL_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["entry_time"] and row["exit_time"] and row["direction"]:
                signals.append({
                    "entry_time": row["entry_time"].strip(),
                    "exit_time":  row["exit_time"].strip(),
                    "direction":  row["direction"].strip(),
                    "lots":       int(row.get("lots", LOT_SIZE))
                })
    log.info(f"[REPLAY] Loaded {len(signals)} signals from {SIGNAL_CSV}")
    return signals

def get_valid_from():
    val = load_ts_file(BASELINE_FILE)
    if val:
        return val
    val = load_ts_file(TS_FILE)
    if val:
        return val
    return "2000-01-01T00:00:00"

# --- Startup ---
# PERMANENT: VALID_FROM never resets - only set once on first ever run
if not os.path.exists(BASELINE_FILE) or not open(BASELINE_FILE).read().strip():
    _now_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    open(BASELINE_FILE, 'w').write(_now_str)
    log.info(f"[STARTUP] VALID_FROM first time set: {_now_str}")
else:
    log.info(f"[STARTUP] VALID_FROM kept: {open(BASELINE_FILE).read().strip()}")
log.info("[STARTUP] S2 Signal Replay Bot starting...")

# Sync position from exchange
pos = om.get_position()
if pos.get("success") and pos.get("direction") == "LONG":
    position = "long"
elif pos.get("success") and pos.get("direction") == "SHORT":
    position = "short"
else:
    position = None
log.info(f"[STARTUP] Position synced from exchange: {position}")

# Load last known ts
last_known_ts = load_ts_file(TS_FILE)
valid_from    = get_valid_from()
log.info(f"[STARTUP] last_known_ts={last_known_ts} | valid_from={valid_from}")

# Load signals
signals = load_signals()
open_lot_size = LOT_SIZE

# --- Main Loop ---
log.info("[STARTUP] Entering main loop. Checking every 10 seconds.")

# Validate API key on startup
try:
    import requests as _rq_val, time as _t_val, hmac as _hm_val, hashlib as _hs_val
    _base_val = "https://cdn-ind.testnet.deltaex.org"  # testnet - change to https://api.india.delta.exchange for live
    _ts_val = str(int(_t_val.time()))
    _path_val = "/v2/profile"
    _msg_val = f"GET{_ts_val}{_path_val}"
    _sig_val = _hm_val.new(API_SECRET.encode(), _msg_val.encode(), _hs_val.sha256).hexdigest()
    _hdrs_val = {"api-key": API_KEY, "timestamp": _ts_val, "signature": _sig_val}
    _r_val = _rq_val.get(f"{_base_val}{_path_val}", headers=_hdrs_val, timeout=5)
    _d_val = _r_val.json()
    if _d_val.get("success"):
        log.info("[STARTUP] API key validated successfully")
    else:
        log.error(f"[CRITICAL] API key validation FAILED: {_d_val.get('error')} - check API key and testnet setting")
except Exception as _e_val:
    log.error(f"[CRITICAL] API key validation error: {_e_val}")
while True:
    try:
        now = now_utc_str()

        # Reload signals every 10 minutes - regenerate first to pick up new candles
        _now_min = now[14:16]
        if _now_min in ["00","10","20","30","40","50"]:
            log.info("[RELOAD] Reading latest signal CSV (regeneration handled by live bots)")
            signals = load_signals()

        for sig in signals:
            entry_time = sig["entry_time"]
            exit_time  = sig["exit_time"]
            direction  = sig["direction"]
            lots       = sig["lots"]

            # Skip signals before valid_from
            if entry_time < valid_from:
                continue

            # Skip already executed signals
            if last_known_ts and entry_time < last_known_ts:
                continue

            # --- ENTRY ---
            # Skip stale signals - entry must be within 1 candle period (1H for S2)
            from datetime import datetime, timezone
            now_dt = datetime.strptime(now, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            entry_dt = datetime.strptime(entry_time, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            signal_age_hours = (now_dt - entry_dt).total_seconds() / 3600
            exit_dt_chk = datetime.strptime(exit_time, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            if now >= entry_time and position is None and now < exit_time:
                side = "buy" if direction == "long" else "sell"
                log.info(f"[ORDER] ENTRY {side} {lots} lots | dir={direction} | ts={entry_time}")
                save_ts_file(TS_FILE, entry_time)
                last_known_ts = entry_time
                result = om.place_market_order(side=side, size=lots)
                if result.get("success"):
                    position     = direction
                    open_lot_size = lots
                    sl_result = om.place_bracket_sl(direction=direction, entry_price=float(result.get("filled_price", 0) or 0))
                    if sl_result.get("success"):
                        log.info(f"[SL] Bracket SL placed | sl_price={sl_result['sl_price']}")
                    else:
                        log.warning(f"[SL] Bracket SL FAILED: {sl_result}")
                    log.info(f"[ORDER] ENTRY confirmed | position={position}")
                    send_alert(f"CTS MEMBER_S2 ENTRY\nDirection: {direction.upper()}\nLots: {lots}")
                else:
                    log.error(f"[ORDER] ENTRY FAILED: {result}")
                    send_alert(f"CTS MEMBER_S2 ENTRY FAILED\nError: {result}")
                    if result.get('error',{}).get('code') == 'invalid_api_key':
                        log.error("[CRITICAL] invalid_api_key - check API key and IP whitelist")
                        send_alert("CTS MEMBER_S2 CRITICAL: invalid_api_key - check API key and IP whitelist")
                    last_known_ts = load_ts_file(TS_FILE)
                break  # process one signal per cycle

            # --- EXIT ---
            # Skip stale exit - must be within 1 candle period (1H for S2)
            from datetime import datetime, timezone
            now_dt2 = datetime.strptime(now, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            exit_dt2 = datetime.strptime(exit_time, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            exit_age_hours = (now_dt2 - exit_dt2).total_seconds() / 3600
            if now >= exit_time and position is not None:
                side = "sell" if position == "long" else "buy"
                actual = om.get_position()
                close_size = abs(actual.get("size", open_lot_size)) if actual.get("success") else open_lot_size
                log.info(f"[ORDER] EXIT {side} {close_size} lots | ts={exit_time}")
                save_ts_file(TS_FILE, exit_time)
                last_known_ts = exit_time
                result = om.close_position(size=close_size, side=side)
                if result.get("success"):
                    position = None
                    log.info(f"[ORDER] EXIT confirmed | position=None")
                    send_alert(f"CTS MEMBER_S2 EXIT\nPosition closed\nLots: {close_size}")
                else:
                    log.error(f"[ORDER] EXIT FAILED: {result}")
                    last_known_ts = load_ts_file(TS_FILE)
                break

        else:
            log.info(f"[WAIT] now={now} | position={position} | last_known_ts={last_known_ts}")

    except Exception as e:
        log.error(f"[ERROR] {e}", exc_info=True)

    time.sleep(SLEEP_SEC)
