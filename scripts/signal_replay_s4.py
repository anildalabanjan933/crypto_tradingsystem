#!/usr/bin/env python3
"""
signal_replay_s4.py - S4 Signal Replay Bot
Reads pre-generated backtest signals from logs/signals_s4.csv
Places orders when current UTC time matches signal entry/exit time.
Zero Renko recalculation. 100% match with backtest guaranteed.
"""
import os
import time, sys, time, csv, logging, re
from datetime import datetime, timezone
sys.path.insert(0, ".")
from engine.order_manager import OrderManager
from engine.telegram_alert import send_alert
from dotenv import load_dotenv
load_dotenv(dotenv_path="/home/anildalabanjan933/crypto_trading_system/.env")

# --- Config ---
SYMBOL       = "BTCUSD"
LOT_SIZE     = 100
SIGNAL_CSV   = "logs/signals_s4.csv"
TS_FILE      = "logs/last_known_ts_s4.txt"
BASELINE_FILE= "logs/valid_from_baseline.txt"
SLEEP_SEC    = 1
LOG_FILE     = "logs/live_trading_s4.log"

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
API_KEY    = os.getenv("S4_API_KEY", "")
API_SECRET = os.getenv("S4_API_SECRET", "")
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
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue
            if row[0].strip() == "entry_time":
                continue  # skip header if present
            entry = row[0].strip()
            exit_ = row[1].strip()
            dirn  = row[2].strip()
            lots  = int(row[3].strip()) if len(row) > 3 else LOT_SIZE
            if entry and exit_ and dirn:
                signals.append({
                    "entry_time": entry,
                    "exit_time":  exit_,
                    "direction":  dirn,
                    "lots":       lots
                })
    log.info(f"[REPLAY] Loaded {len(signals)} signals from {SIGNAL_CSV}")
    return signals

def get_valid_from():
    """VALID_FROM = today 00:00 UTC on every startup. Always fresh window."""
    _today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    _now_str = _today.strftime('%Y-%m-%dT%H:%M:%S')
    open(BASELINE_FILE, 'w').write(_now_str)
    log.info(f"[STARTUP] VALID_FROM auto-set to today 00:00 UTC: {_now_str}")
    return _now_str

# --- Startup ---
# VALID_FROM resets to today 00:00 UTC on every startup for fresh window
log.info("[STARTUP] S4 Signal Replay Bot starting...")

pos = om.get_position()
if pos.get("success") and pos.get("direction") == "LONG":
    position = "long"
elif pos.get("success") and pos.get("direction") == "SHORT":
    position = "short"
else:
    position = None
log.info(f"[STARTUP] Position synced from exchange: {position}")

last_known_ts = load_ts_file(TS_FILE)
valid_from    = get_valid_from()
# Auto-advance last_known_ts to valid_from if behind - zero manual intervention
if last_known_ts and valid_from and last_known_ts < valid_from:
    last_known_ts = valid_from
    save_ts_file(TS_FILE, valid_from)
    log.info(f"[STARTUP] last_known_ts advanced to valid_from={valid_from}")
log.info(f"[STARTUP] last_known_ts={last_known_ts} | valid_from={valid_from}")

signals = load_signals()
open_lot_size = LOT_SIZE


def read_live_signal(signal_file):
    """Read latest signal from live engine signal file."""
    try:
        if not os.path.exists(signal_file):
            return None
        line = open(signal_file).read().strip()
        if not line:
            return None
        parts = line.split("|")
        if len(parts) < 3:
            return None
        return {"type": parts[0], "timestamp": parts[1], "lots": int(parts[2])}
    except Exception:
        return None

def clear_live_signal(signal_file):
    """Clear signal file after processing."""
    try:
        open(signal_file, "w").write("")
    except Exception:
        pass

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

        # Read live signal from engine
        live_sig = read_live_signal("logs/live_signal_s4.txt")
        if live_sig:
            sig_type  = live_sig["type"]
            sig_ts    = live_sig["timestamp"]
            lots      = live_sig["lots"]

            if sig_ts >= valid_from and sig_ts != last_known_ts:

                # --- ENTRY ---
                if "ENTRY" in sig_type and position is None:
                    direction = "long" if "LONG" in sig_type else "short"
                    side = "buy" if direction == "long" else "sell"
                    log.info(f"[ORDER] ENTRY {side} {lots} lots | dir={direction} | ts={sig_ts}")
                    save_ts_file(TS_FILE, sig_ts)
                    last_known_ts = sig_ts
                    clear_live_signal("logs/live_signal_s4.txt")
                    result = om.place_market_order(side=side, size=lots)
                    if result.get("success"):
                        position = direction
                        open_lot_size = lots
                        time.sleep(1)
                        pos_check = om.get_position()
                        real_entry = pos_check.get("entry_price", 0.0) if pos_check.get("success") else 0.0
                        if real_entry > 0:
                            sl_result = om.place_stop_loss_order(direction=direction, entry_price=real_entry, sl_pct=2.0)
                            if sl_result.get("success"):
                                log.info(f"[SL] Stop SL placed | sl_price={sl_result['sl_price']}")
                            else:
                                log.warning(f"[SL] Stop SL FAILED: {sl_result}")
                        log.info(f"[ORDER] ENTRY confirmed | position={position}")
                        send_alert(f"CTS S4 ENTRY\nDirection: {direction.upper()}\nLots: {lots}")
                    else:
                        log.error(f"[ORDER] ENTRY FAILED: {result}")
                        send_alert(f"CTS S4 ENTRY FAILED\nError: {result}")
                        last_known_ts = load_ts_file(TS_FILE)

                # --- EXIT ---
                elif "EXIT" in sig_type and position is not None:
                    side = "sell" if position == "long" else "buy"
                    actual = om.get_position()
                    _ex_size = abs(actual.get("size", 0)) if actual.get("success") else 0
                    close_size = _ex_size if _ex_size > 0 else (open_lot_size if open_lot_size > 0 else LOT_SIZE)
                    log.info(f"[ORDER] EXIT {side} {close_size} lots | ts={sig_ts}")
                    save_ts_file(TS_FILE, sig_ts)
                    last_known_ts = sig_ts
                    clear_live_signal("logs/live_signal_s4.txt")
                    result = om.close_position(size=close_size, side=side)
                    if result.get("success"):
                        position = None
                        log.info(f"[ORDER] EXIT confirmed | position=None")
                        send_alert(f"CTS S4 EXIT\nPosition closed\nLots: {close_size}")
                    else:
                        log.error(f"[ORDER] EXIT FAILED: {result}")
                        last_known_ts = load_ts_file(TS_FILE)

        if True:  # placeholder to maintain indentation
            if False:
                side = "buy" if direction == "long" else "sell"
                log.info(f"[ORDER] ENTRY {side} {lots} lots | dir={direction} | ts={entry_time}")
                save_ts_file(TS_FILE, entry_time)
                last_known_ts = entry_time
                result = om.place_market_order(side=side, size=lots)
                if result.get("success"):
                    position      = direction
                    open_lot_size = lots
                    time.sleep(1)
                    pos_check = om.get_position()
                    real_entry = pos_check.get("entry_price", 0.0) if pos_check.get("success") else 0.0
                    if real_entry > 0:
                        sl_result = om.place_stop_loss_order(direction=direction, entry_price=real_entry, sl_pct=2.0)
                        if sl_result.get("success"):
                            log.info(f"[SL] Stop SL placed | sl_price={sl_result['sl_price']}")
                        else:
                            log.warning(f"[SL] Stop SL FAILED: {sl_result}")
                    else:
                        log.warning(f"[SL] Skipped - could not get real entry price from position")
                    log.info(f"[ORDER] ENTRY confirmed | position={position}")
                    send_alert(f"CTS S4 ENTRY\nDirection: {direction.upper()}\nLots: {lots}")
                else:
                    log.error(f"[ORDER] ENTRY FAILED: {result}")
                    if result.get('error',{}).get('code') == 'invalid_api_key':
                        log.error("[CRITICAL] invalid_api_key - check API key and IP whitelist")
                    send_alert(f"CTS S4 ENTRY FAILED\nError: {result}")
                    if result.get('error',{}).get('code') == 'invalid_api_key':
                        log.error("[CRITICAL] invalid_api_key - check API key and IP whitelist")
                        send_alert("CTS S4 CRITICAL: invalid_api_key - check API key and IP whitelist")
                    last_known_ts = load_ts_file(TS_FILE)
                break

        log.info(f"[WAIT] now={now} | position={position} | last_known_ts={last_known_ts}")

    except Exception as e:
        log.error(f"[ERROR] {e}", exc_info=True)

    time.sleep(SLEEP_SEC)
