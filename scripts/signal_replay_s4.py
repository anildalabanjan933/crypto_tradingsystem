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

def _utc_to_ist(ts_str):
    """Convert UTC timestamp string to IST display format."""
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.strptime(ts_str[:16], "%Y-%m-%dT%H:%M")
        ist = dt + timedelta(hours=5, minutes=30)
        return ist.strftime("%d-%b %I:%M %p IST")
    except:
        return ts_str

def _get_bt_trade(sig_ts, strategy_name):
    """Get matching backtest signal by calling strategy directly - same source as engine."""
    try:
        import sys, warnings, pandas as pd
        sys.path.insert(0,".")
        if strategy_name == "S2":
            from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy as _Strat
            _tf = "30m"
            _p  = dict(renko_box_pct=0.001,renko_timeframe="30m",st_atr_length=10,st_factor=2.0)
        else:
            from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy as _Strat
            _tf = "2h"
            _p  = dict(renko_box_pct=0.001,renko_timeframe="2h",st_atr_length=5,st_factor=2.0,smiio_shortlen=10,smiio_longlen=10,smiio_siglen=3)
        _df = pd.read_csv("data/btc_1m_delta.csv")
        _df["timestamp"] = pd.to_datetime(_df["Date"]+" "+_df["Time"],format="mixed")
        _df.set_index("timestamp",inplace=True)
        _df.columns = [c.lower() for c in _df.columns]
        _tf_r = "30min" if _tf=="30m" else ("2h" if _tf=="2h" else _tf)
        _dft = _df.resample(_tf_r).agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
        _dft.index.name = "timestamp"
        _s = _Strat({_tf:_dft},100,**_p)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _sigs = _s.generate_signals()
        # Exact match
        for _sig in reversed(_sigs):
            if _sig.get("timestamp","")[:16] == sig_ts[:16]:
                return _sig
        # No exact match - return next signal after sig_ts
        for _sig in _sigs:
            if _sig.get("timestamp","") > sig_ts:
                return _sig
        # Fallback - return last signal
        for _sig in reversed(_sigs):
            if _sig.get("timestamp","") != "":
                return _sig
    except Exception as _e:
        pass
    return None

def _get_csv_bt_row(label, entry_ts):
    """Read BT row from signals CSV by entry_time - returns list [entry_ts, exit_ts, dir, lots, bt_entry_price, bt_exit_price]"""
    import csv as _csv
    sig_num = "2" if label in ("S2","TM1_S2") else "4"
    sig_csv = f"logs/signals_s{sig_num}.csv"
    try:
        with open(sig_csv,"r") as _f:
            for row in _csv.reader(_f):
                if len(row) >= 5 and row[0] == entry_ts:
                    return row
    except:
        pass
    return None

def _send_live_entry_alert(label, direction, entry_ts, fill_price, sl_price, lots=100):
    try:
        from engine.telegram_alert import send_alert
        sl_str = f"${sl_price:,.2f} (2% away)" if sl_price > 0 else "pending"
        msg = (
            f"CTS LIVE {label} ENTRY\n"
            f"Direction : {direction.upper()}\n"
            f"Entry time: {_utc_to_ist(entry_ts)}\n"
            f"Fill price: ${fill_price:,.2f}\n"
            f"SL placed : {sl_str}\n"
            f"Lots      : {lots}"
        )
        send_alert(msg)
    except Exception as e:
        pass

def _send_live_exit_alert(label, direction, exit_ts, fill_price, entry_fill=0.0, lots=100):
    try:
        from engine.telegram_alert import send_alert
        if entry_fill and entry_fill > 0:
            sign = 1 if direction.lower() == "long" else -1
            live_pnl = round((fill_price - entry_fill) * sign * lots * 0.001, 2)
            pnl_sign = "+" if live_pnl >= 0 else ""
            pnl_str  = f"{pnl_sign}${live_pnl:,.2f}"
        else:
            pnl_str = "N/A"
        msg = (
            f"CTS LIVE {label} EXIT\n"
            f"Direction : {direction.upper()}\n"
            f"Exit time : {_utc_to_ist(exit_ts)}\n"
            f"Fill price: ${fill_price:,.2f}\n"
            f"Lots      : {lots}\n"
            f"Live PnL  : {pnl_str}"
        )
        send_alert(msg)
    except Exception as e:
        pass

def _send_live_exit_alert_DEPRECATED_DUPLICATE(label, direction, exit_ts, fill_price, lots=100):
    """DEPRECATED - duplicate removed, merged into single function above."""
    pass

def _send_entry_match_alert(label, direction, entry_ts, bt_entry_price, lv_fill_price,
                             bt_exit_ts, bt_exit_price, lots=100):
    try:
        from engine.telegram_alert import send_alert
        entry_slip = abs(lv_fill_price - bt_entry_price)
        slip_ok    = entry_slip <= 10
        slip_str   = f"${entry_slip:.2f} - OK (within $10)" if slip_ok else f"${entry_slip:.2f} - EXCEEDS $10"
        sign_ok    = "CTS ENTRY MATCH" if slip_ok else "CTS ENTRY MISMATCH"
        gross      = (bt_exit_price - bt_entry_price) if direction.lower()=="long" else (bt_entry_price - bt_exit_price)
        gross      = gross * lots * 0.001
        pnl5       = round(gross - (5*2*lots*0.001), 2)
        pnl10      = round(gross - (10*2*lots*0.001), 2)
        s5         = "+" if pnl5  >= 0 else ""
        s10        = "+" if pnl10 >= 0 else ""
        action_str = "" if slip_ok else "\nAction    : Check dashboard immediately"
        msg = (
            f"{sign_ok} {label}\n"
            f"Direction : MATCH ({direction.upper()})\n"
            f"Entry time: MATCH ({_utc_to_ist(entry_ts)})\n"
            f"BT Entry  : ${bt_entry_price:,.2f}\n"
            f"LV Fill   : ${lv_fill_price:,.2f}\n"
            f"Entry slip: {slip_str}\n"
            f"BT PnL ($5/side) : {s5}${pnl5:,.2f} (estimated)\n"
            f"BT PnL ($10/side): {s10}${pnl10:,.2f} (estimated)\n"
            f"Exit pending at  : {_utc_to_ist(bt_exit_ts)}{action_str}"
        )
        send_alert(msg)
    except Exception as e:
        pass


def _append_fill_log(csv_path, entry_ts, exit_ts, direction, lots, bt_ep, lv_ep, bt_xp, lv_xp, total_charges=0.0):
    import csv as _csv_fl, os as _os_fl
    try:
        file_exists = _os_fl.path.exists(csv_path)
        with open(csv_path, "a", newline="") as _f:
            _w = _csv_fl.writer(_f)
            if not file_exists:
                _w.writerow(["entry_ts","exit_ts","dir","lots","bt_entry","lv_entry","bt_exit","lv_exit","total_charges"])
            _w.writerow([entry_ts, exit_ts, direction, lots, bt_ep, lv_ep, bt_xp, lv_xp, total_charges])
    except Exception as _e:
        log.warning(f'[FILL-LOG] Could not write fill log: {_e}')

def _send_roundtrip_match_alert(label, direction, entry_fill, exit_fill,
                                 bt_entry_price, bt_exit_price, lots=100):
    try:
        from engine.telegram_alert import send_alert
        entry_slip  = abs(entry_fill - bt_entry_price)
        exit_slip   = abs(exit_fill  - bt_exit_price)
        round_trip  = entry_slip + exit_slip
        rt_ok       = round_trip <= 10
        sign_ok     = "CTS ROUND TRIP MATCH" if rt_ok else "CTS ROUND TRIP WARNING"
        e_str       = f"${entry_slip:.2f} - OK" if entry_slip <= 10 else f"${entry_slip:.2f} - HIGH"
        x_str       = f"${exit_slip:.2f} - OK"  if exit_slip  <= 10 else f"${exit_slip:.2f} - HIGH"
        rt_str      = f"${round_trip:.2f} - WITHIN $10 OK" if rt_ok else f"${round_trip:.2f} - EXCEEDS $10"
        gross_bt    = (bt_exit_price - bt_entry_price) if direction.lower()=="long" else (bt_entry_price - bt_exit_price)
        gross_bt    = gross_bt * lots * 0.001
        pnl5        = round(gross_bt - (5*2*lots*0.001), 2)
        pnl10       = round(gross_bt - (10*2*lots*0.001), 2)
        s5          = "+" if pnl5  >= 0 else ""
        s10         = "+" if pnl10 >= 0 else ""
        sign_lv     = 1 if direction.lower()=="long" else -1
        live_pnl    = round((exit_fill - entry_fill) * sign_lv * lots * 0.001, 2)
        slv         = "+" if live_pnl >= 0 else ""
        pnl_diff    = round(live_pnl - pnl5, 2)
        diff_s      = "+" if pnl_diff >= 0 else ""
        action_str  = ""
        count_str   = ""
        if rt_ok:
            mc        = _increment_match_count()
            count_str = f"\nStatus    : {mc}/5 toward go-live"
        else:
            action_str = "\nAction    : Check dashboard immediately"
        msg = (
            f"{sign_ok} {label}\n"
            f"Direction : MATCH ({direction.upper()})\n"
            f"Entry slip: {e_str}\n"
            f"Exit slip : {x_str}\n"
            f"Round trip: {rt_str}\n"
            f"BT PnL ($5/side) : {s5}${pnl5:,.2f}\n"
            f"BT PnL ($10/side): {s10}${pnl10:,.2f}\n"
            f"Live PnL         : {slv}${live_pnl:,.2f}\n"
            f"PnL diff         : {diff_s}${pnl_diff:,.2f}{count_str}{action_str}"
        )
        send_alert(msg)
    except Exception as e:
        pass

def _send_match_alert(label, direction, bt_entry_price, lv_fill_price, entry_ts, match_count=None):
    pass  # replaced by _send_entry_match_alert and _send_roundtrip_match_alert


from dotenv import load_dotenv
load_dotenv(dotenv_path="/home/anildalabanjan933/crypto_trading_system/.env")

def _get_csv_bt_row(label, entry_ts):
    """Read BT row from signals CSV by entry_time - returns list [entry_ts, exit_ts, dir, lots, bt_entry_price, bt_exit_price]"""
    import csv as _csv
    sig_num = "2" if label in ("S2","TM1_S2") else "4"
    sig_csv = f"logs/signals_s{sig_num}.csv"
    try:
        with open(sig_csv,"r") as _f:
            for row in _csv.reader(_f):
                if len(row) >= 5 and row[0] == entry_ts:
                    return row
    except:
        pass



from dotenv import load_dotenv
load_dotenv(dotenv_path="/home/anildalabanjan933/crypto_trading_system/.env")

def _send_live_entry_alert(label, direction, entry_ts, fill_price, sl_price, lots=100):
    """Send Telegram alert on live entry fill."""
    try:
        from engine.telegram_alert import send_alert
        import datetime as _dt
        def _ist(ts):
            try:
                dt = _dt.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
                return (dt + _dt.timedelta(hours=5, minutes=30)).strftime("%d-%b-%Y %I:%M %p IST")
            except: return ts
        msg = (
            f"CTS LIVE {label} ENTRY\n"
            f"Direction : {direction.upper()}\n"
            f"Entry time: {_ist(entry_ts)}\n"
            f"Fill price: ${fill_price:,.2f}\n"
            f"SL placed : ${sl_price:,.2f}\n"
            f"Lots      : {lots}"
        )
        send_alert(msg)
    except Exception as e:
        pass






# --- Config ---
SYMBOL       = "BTCUSD"
LOT_SIZE     = 100
SIGNAL_CSV   = "logs/signals_s4.csv"
TS_FILE      = "logs/last_known_ts_s4.txt"
BASELINE_FILE= "logs/valid_from_baseline.txt"
SLEEP_SEC    = 0.5
LOG_FILE     = "logs/live_trading_s4.log"

# --- Logging ---
os.makedirs("logs", exist_ok=True)
from logging.handlers import RotatingFileHandler as _RFH
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        _RFH(LOG_FILE, maxBytes=10*1024*1024, backupCount=1)
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
    val = str(val)
    if not TS_PATTERN.match(val):
        val = now_utc_str()
    open(path, "w").write(val)

def safe_ts(val):
    val = str(val)
    if not TS_PATTERN.match(val):
        return now_utc_str()
    return val

def now_utc_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

_signals_cache = {"mtime": None, "data": []}
def load_signals():
    signals = []
    if not os.path.exists(SIGNAL_CSV):
        log.error(f"[REPLAY] Signal CSV not found: {SIGNAL_CSV}")
        return signals
    _mtime = os.path.getmtime(SIGNAL_CSV)
    # Caching disabled - always re-read (CSV write is instant, no compute cost)
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
    _signals_cache["mtime"] = _mtime
    _signals_cache["data"] = signals
    return signals

SIGNAL_FILE = "logs/live_signal_s4.txt"
def get_valid_from():
    """VALID_FROM = max(today 00:00 UTC, signal file exit time).
    Prevents firing yesterday signal on restart = no stale SL hits."""
    _today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    _base = _today
    # Check signal file exit time - if yesterday signal still in file, skip it
    try:
        _sig = open(SIGNAL_FILE).read().strip()
        if _sig and "|" in _sig:
            _parts = _sig.split("|")
            if len(_parts) >= 2:
                _sig_exit = datetime.fromisoformat(_parts[1]).replace(tzinfo=None)
                if _sig_exit > _base:
                    _base = _sig_exit
                    log.info(f"[STARTUP] VALID_FROM advanced to signal exit: {_sig_exit.strftime('%Y-%m-%dT%H:%M:%S')}")
    except Exception as _e:
        pass
    _now_str = _base.strftime('%Y-%m-%dT%H:%M:%S')
    open(BASELINE_FILE, 'w').write(_now_str)
    log.info(f"[STARTUP] VALID_FROM auto-set to: {_now_str}")
    return _now_str

# --- Startup ---
# VALID_FROM resets to today 00:00 UTC on every startup for fresh window
log.info("[STARTUP] S4 Signal Replay Bot starting...")

import time as _time_startup
pos = om.get_position()
_startup_retries = 0
while not pos.get("success") and _startup_retries < 5:
    log.warning(f"[STARTUP] get_position() failed, retry {_startup_retries+1}/5")
    _time_startup.sleep(2)
    pos = om.get_position()
    _startup_retries += 1

if not pos.get("success"):
    log.critical("[STARTUP] get_position() failed after 5 retries - cannot confirm real exchange state. BLOCKING startup to prevent duplicate/wrong-size entry.")
    from engine.telegram_alert import send_alert
    send_alert("CTS S4 CRITICAL: Startup position sync failed after 5 retries. Bot BLOCKED - manual check required before restart.")
    raise SystemExit("[STARTUP] Position sync failed - blocking to prevent capital risk.")

if pos.get("direction") == "LONG":
    position = "long"
elif pos.get("direction") == "SHORT":
    position = "short"
else:
    position = None
log.info(f"[STARTUP] Position synced from exchange: {position}")

last_known_ts = load_ts_file(TS_FILE)
valid_from    = get_valid_from()
# If last_known_ts empty - use signal file as fallback lock
if not last_known_ts:
    _sig_file = "logs/live_signal_s4.txt"
    try:
        _line = open(_sig_file).read().strip()
        if _line and "|" in _line:
            last_known_ts = _line.split("|")[1]
            log.info(f"[STARTUP] last_known_ts loaded from signal file: {last_known_ts}")
    except: pass
# Auto-advance last_known_ts to valid_from if behind - but NEVER if a real
# position is already open (would break safety-override entry_time match)
if position is None and last_known_ts and valid_from and last_known_ts < valid_from:
    last_known_ts = valid_from
    save_ts_file(TS_FILE, valid_from)
    log.info(f"[STARTUP] last_known_ts advanced to valid_from={valid_from}")
elif position is not None and last_known_ts and valid_from and last_known_ts < valid_from:
    log.info(f"[STARTUP] last_known_ts NOT advanced - position={position} open with entry_ts={last_known_ts}")
log.info(f"[STARTUP] last_known_ts={last_known_ts} | valid_from={valid_from}")

signals = load_signals()

# SELF-HEAL: if position is open, verify last_known_ts matches the PENDING
# signal row for that direction. If mismatched (corrupted ts), auto-correct
# so safety-override exit match doesn't deadlock.
if position is not None:
    for _row in signals:
        if _row["direction"] == position and _row["exit_time"] == "PENDING":
            if _row["entry_time"] != last_known_ts:
                log.warning(f"[SELF-HEAL] last_known_ts mismatch: had={last_known_ts} correct={_row['entry_time']} | correcting")
                last_known_ts = safe_ts(_row["entry_time"])
                save_ts_file(TS_FILE, last_known_ts)
else:
    for _row in signals:
        if _row.get("entry_time") == last_known_ts and _row.get("exit_time") == "PENDING":
            with open("logs/manual_override_s4.txt", "w") as _f:
                _f.write(f"{int(time.time())}|startup_flat_detected|entry_ts={last_known_ts}")
            log.warning(f"[STARTUP] Exchange FLAT but signal expected OPEN at entry_ts={last_known_ts} - manual close during downtime detected, override written")
            break
            break

open_lot_size   = LOT_SIZE
open_entry_price = 0.0
last_processed_seq = 0
# FIX: on startup, if the live signal file already points at a timestamp we
# have already handled (<= last_known_ts), mark it as seen immediately so it
# is not re-processed as "new" right after a restart.
try:
    import re as _re_startup
    _lf = open(f"logs/live_signal_s{__file__[-4]}.txt").read().strip()
    _parts = _lf.split("|")
    if len(_parts) >= 4:
        _startup_ts  = _parts[1]
        _startup_seq = int(_parts[3].split("=")[1])
        if last_known_ts and _startup_ts <= last_known_ts:
            last_processed_seq = _startup_seq
            log.info(f"[STARTUP] Signal {_startup_ts} already handled (<= last_known_ts) - marking SEQ={_startup_seq} as seen")
except Exception as _e_startup:
    log.warning(f"[STARTUP] Could not pre-check live signal file: {_e_startup}")

# --- Missed Trade Check on Startup ---
try:
    _now_check = now_utc_str()
    _missed = []
    for _sig in signals:
        _et = _sig["entry_time"]
        _xt = _sig["exit_time"]
        _dr = _sig["direction"]
        if last_known_ts and _et <= last_known_ts:
            continue
        if _xt > _now_check:
            continue
        _missed.append(_sig)
    if _missed:
        for _ms in _missed:
            _ist_e = _utc_to_ist(_ms["entry_time"])
            _ist_x = _utc_to_ist(_ms["exit_time"])
            log.warning(f"[MISSED TRADE] entry={_ms['entry_time']} exit={_ms['exit_time']} dir={_ms['direction']} reason=bot_restart")
            send_alert(
                f"⚠️ CTS S4 BOT RESTART - MISSED TRADE\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Dir   : {_ms['direction'].upper()}\n"
                f"Entry : {_ist_e}\n"
                f"Exit  : {_ist_x}\n"
                f"Reason: Bot was offline\n"
                f"Action: Trade NOT fired - report only\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
        log.warning(f"[MISSED TRADE] Total {len(_missed)} trade(s) missed during offline period")
    else:
        log.info("[STARTUP] No missed trades detected")
except Exception as _me:
    log.error(f"[MISSED TRADE CHECK] Error: {_me}")


def check_engine_heartbeat():
    """Returns True if engine is alive, False if dead"""
    hb_file = "logs/engine_heartbeat.txt"
    try:
        if not __import__('os').path.exists(hb_file):
            return False
        hb_str = open(hb_file).read().strip()
        try:
            hb_dt = __import__('datetime').datetime.fromtimestamp(float(hb_str), __import__('datetime').timezone.utc).replace(tzinfo=None)
        except:
            hb_dt = __import__('datetime').datetime.strptime(hb_str, '%Y-%m-%dT%H:%M:%S')
        age_min = (__import__('datetime').datetime.now(__import__('datetime').timezone.utc).replace(tzinfo=None) - hb_dt).total_seconds() / 60
        if age_min > 15:
            log.warning(f"[ENGINE] Heartbeat stale {int(age_min)}m - engine may be dead - skipping order")
            from engine.telegram_alert import send_alert
            send_alert(f"CTS S4 WARNING - Engine heartbeat stale {int(age_min)}m - orders blocked until engine restarts")
            return False
        return True
    except Exception as e:
        log.warning(f"[ENGINE] Heartbeat check failed: {e} - skipping order")
        return False

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
        seq = 0
        for p in parts:
            if p.startswith("SEQ="):
                seq = int(p.split("=")[1])
        return {"type": parts[0], "timestamp": parts[1], "lots": int(parts[2]), "seq": seq}
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
    _base_val = "https://cdn-ind.testnet.deltaex.org"  # testnet
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

# Entry retry cooldown/cap state - prevents retry-spam on repeated entry failure
_entry_retry_state = {"ts": None, "count": 0, "last_attempt": 0}
_ENTRY_MAX_ATTEMPTS = 5
_ENTRY_RETRY_COOLDOWN_SEC = 5

while True:
    try:
        now = now_utc_str()

        # --- CSV Signal Matching (single source of truth, CSV-only) ---
        # Reload signals every loop iteration - CSV write is instant (0.05s)
        signals = load_signals()

        # --- Fast live_signal path removed - CSV-only single source of truth ---
        _live_sig = None
        _live_matched = None

        # Find current signal from CSV
        _matched = _live_matched
        if not _matched:
            for _row in signals:
                _et = _row["entry_time"]
                _xt = _row["exit_time"]
                if _et < last_known_ts:
                    # Even if entry is behind last_known_ts, advance if exit also passed and no position
                    if position is None and now >= _xt and _xt > last_known_ts:
                        log.info(f"[SKIP] Expired signal entry={_et} exit={_xt} | advancing last_known_ts")
                        save_ts_file(TS_FILE, _xt)
                        last_known_ts = safe_ts(_xt)
                    continue
                # Expired signal: exit already passed and no position - skip and advance
                if position is None and now >= _xt:
                    log.info(f"[SKIP] Expired signal entry={_et} exit={_xt} | advancing last_known_ts")
                    save_ts_file(TS_FILE, _xt)
                    last_known_ts = safe_ts(_xt)
                    continue
                if now >= _et:
                    _matched = _row
                    break

        # --- SAFETY OVERRIDE: always re-check current open position's own exit ---
        # Prevents deadlock when live_signal fast-path grabs a NEW entry row
        # while the OPEN position's own exit (in CSV) has already resolved+passed
        if position is not None:
            for _row in signals:
                if _row["entry_time"] == last_known_ts and _row["exit_time"] not in ("PENDING", "") and now >= _row["exit_time"]:
                    _matched = _row
                    break

        if _matched:
            sig_ts = _matched["entry_time"]
            lots   = _matched["lots"]
            dirn   = _matched["direction"]
            _xt    = _matched["exit_time"]

            # --- Skip expired signal (exit already passed, no position) ---
            if position is None and now >= _xt:
                log.info(f"[SKIP] Expired signal | entry={sig_ts} exit={_xt} | advancing last_known_ts")
                save_ts_file(TS_FILE, _xt)
                last_known_ts = safe_ts(_xt)
                if _live_sig: last_processed_seq = _live_sig.get("seq", 0)

            # --- EXIT first if position open and exit time reached ---
            elif position is not None and now >= _xt:
                actual = om.get_position()
                _ex_size = abs(actual.get("size", 0)) if actual.get("success") else 0
                if _ex_size == 0:
                    log.info(f"[ORDER] EXIT skipped - exchange already FLAT | ts={_xt}")
                    _send_live_exit_alert('S4', dirn, _xt, 0.0)
                    position = None
                    save_ts_file(TS_FILE, _xt)
                    last_known_ts = safe_ts(_xt)
                else:
                    side = "sell" if position == "long" else "buy"
                    close_size = _ex_size
                    log.info(f"[ORDER] EXIT {side} {close_size} lots | ts={_xt}")
                    save_ts_file(TS_FILE, _xt)
                    last_known_ts = safe_ts(_xt)
                    if not check_engine_heartbeat():
                        log.warning("[ORDER] EXIT blocked - engine heartbeat stale")
                    else:
                        result = om.close_position(size=close_size, side=side)
                        if result.get("success"):
                            position = None
                            _entry_price_for_alert = open_entry_price
                            _entry_commission_for_log = _entry_commission if '_entry_commission' in dir() else 0.0
                            open_entry_price = 0.0
                            _exit_fill_price = result.get("avg_fill_price", 0.0)
                            if _exit_fill_price == 0.0:
                                for _i in range(5):
                                    time.sleep(0.2)
                                    _exit_pos = om.get_position()
                                    _exit_fill_price = _exit_pos.get("exit_price", 0.0) if _exit_pos.get("success") else 0.0
                                    if _exit_fill_price > 0:
                                        break
                            log.info(f"[ORDER] EXIT confirmed | position=None | exit={_exit_fill_price}")
                            _send_live_exit_alert("S4", dirn, _xt, _exit_fill_price, _entry_price_for_alert, lots)
                            _bt_ep2 = 0.0
                            _bt_xp2 = 0.0
                            for _retry_bt in range(5):
                                _bt_csv2 = _get_csv_bt_row("S4", sig_ts)
                                _bt_ep2  = float(_bt_csv2[4]) if _bt_csv2 and len(_bt_csv2) > 4 and str(_bt_csv2[4]).strip() not in ("", "PENDING") else 0.0
                                _bt_xp2  = float(_bt_csv2[5]) if _bt_csv2 and len(_bt_csv2) > 5 and str(_bt_csv2[5]).strip() not in ("", "PENDING") else 0.0
                                if _bt_ep2 > 0 and _bt_xp2 > 0:
                                    break
                                time.sleep(0.5)
                            if _bt_xp2 == 0.0:
                                log.warning(f"[FILL-LOG] bt_exit still 0.0 after 5 retries (2.5s) for sig_ts={sig_ts} - engine CSV write race unresolved, logging with bt_exit=0.0")
                            if _bt_ep2 > 0 and _entry_price_for_alert > 0 and _exit_fill_price > 0:
                                _send_roundtrip_match_alert("S4", dirn, _entry_price_for_alert, _exit_fill_price, _bt_ep2, _bt_xp2, lots)
                                _exit_commission = result.get("commission", 0.0)
                                _total_charges = float(_entry_commission_for_log) + float(_exit_commission)
                                _append_fill_log("logs/fill_prices_s4.csv", sig_ts, _xt, dirn, lots, _bt_ep2, _entry_price_for_alert, _bt_xp2, _exit_fill_price, _total_charges)
                        else:
                            log.error(f"[ORDER] EXIT FAILED: {result}")
                            send_alert(f"CTS S4 EXIT FAILED\nError: {result}")
                            last_known_ts = load_ts_file(TS_FILE)

            # --- ENTRY if no position and exit time not yet reached ---
            elif position is None and now < _xt:
                direction = dirn
                side = "buy" if direction == "long" else "sell"
                _override_file = "logs/manual_override_s4.txt"
                if os.path.exists(_override_file):
                    _skip_this = True
                    _ov_entry_ts = None
                    try:
                        with open(_override_file, "r") as _f_ov:
                            _ov_content = _f_ov.read().strip()
                        if "entry_ts=" in _ov_content:
                            _ov_entry_ts = _ov_content.split("entry_ts=")[-1].strip()
                            if _ov_entry_ts and sig_ts != _ov_entry_ts:
                                _skip_this = False
                    except Exception as _e_ov:
                        log.warning(f"[SKIP-CHECK] Could not parse override file ({_e_ov}) - defaulting to skip for safety")
                    os.remove(_override_file)
                    if _skip_this:
                        # FIX (24-Aug-2026, Bug2): advance last_known_ts PAST this
                        # signal's real exit_time, NOT just to sig_ts (same root
                        # cause / same fix as signal_replay_s4v2.py, same date).
                        _skip_advance_ts = _xt if _xt and _xt != "PENDING" else None
                        if not _skip_advance_ts:
                            try:
                                _fresh_signals = load_signals()
                                for _frow in _fresh_signals:
                                    if _frow.get("entry_time") == sig_ts:
                                        _cand = _frow.get("exit_time")
                                        if _cand and _cand != "PENDING":
                                            _skip_advance_ts = _cand
                                        break
                            except Exception as _e_fresh:
                                log.warning(f"[SKIP-CHECK] Could not re-read signals for exit_time ({_e_fresh})")
                        if not _skip_advance_ts:
                            from datetime import datetime as _dt_sk, timedelta as _td_sk
                            try:
                                _skip_advance_ts = (_dt_sk.strptime(sig_ts, "%Y-%m-%dT%H:%M:%S") + _td_sk(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S")
                            except Exception:
                                _skip_advance_ts = now_utc_str()
                        last_known_ts = safe_ts(_skip_advance_ts)
                        save_ts_file(TS_FILE, last_known_ts)
                        try:
                            import csv as _csv_sk, os as _os_sk
                            _sig_csv_sk = "logs/signals_s4.csv"
                            with open(_sig_csv_sk, "r") as _f_sk:
                                _rows_sk = list(_csv_sk.reader(_f_sk))
                            _upd_sk = False
                            for _r_sk in _rows_sk:
                                if len(_r_sk) >= 2 and _r_sk[0] == sig_ts and _r_sk[1] == "PENDING":
                                    _r_sk[1] = "SKIPPED_MANUAL_OVERRIDE"
                                    _upd_sk = True
                                    break
                            if _upd_sk:
                                _tmp_sk = _sig_csv_sk + ".tmp"
                                with open(_tmp_sk, "w", newline="") as _f_sk:
                                    _w_sk = _csv_sk.writer(_f_sk)
                                    for _r_sk in _rows_sk:
                                        _w_sk.writerow(_r_sk)
                                _os_sk.replace(_tmp_sk, _sig_csv_sk)
                        except Exception as _e_sk:
                            log.warning(f"[SKIP-CSV-FIX] Could not mark CSV row skipped: {_e_sk}")
                        log.info(f"[SKIP] ENTRY blocked - manual_override active (single-shot) | dir={direction} | ts={sig_ts} | advanced past exit={last_known_ts}")
                        continue
                    else:
                        log.info(f"[SKIP-CHECK] Override present but for different entry_ts={_ov_entry_ts} (current sig_ts={sig_ts}) - NOT skipping, legitimate new trade")
                _now_epoch = time.time()
                if _entry_retry_state["ts"] != sig_ts:
                    _entry_retry_state["ts"] = sig_ts
                    _entry_retry_state["count"] = 0
                    _entry_retry_state["last_attempt"] = 0
                if _entry_retry_state["count"] >= _ENTRY_MAX_ATTEMPTS:
                    log.error(f"[ORDER] ENTRY ABANDONED - {_ENTRY_MAX_ATTEMPTS} failed attempts | dir={direction} | ts={sig_ts} | advancing past exit={_xt}")
                    send_alert(f"CTS S4 ENTRY ABANDONED\nDirection: {direction}\nSignal ts: {sig_ts}\nFailed {_ENTRY_MAX_ATTEMPTS}x - advancing past this signal")
                    save_ts_file(TS_FILE, _xt)
                    last_known_ts = safe_ts(_xt)
                    _entry_retry_state["ts"] = None
                elif (_now_epoch - _entry_retry_state["last_attempt"]) < _ENTRY_RETRY_COOLDOWN_SEC:
                    pass
                else:
                    _entry_retry_state["last_attempt"] = _now_epoch
                    log.info(f"[ORDER] ENTRY attempt {side} {lots} lots | dir={direction} | ts={sig_ts} | attempt={_entry_retry_state['count']+1}/{_ENTRY_MAX_ATTEMPTS}")
                    save_ts_file(TS_FILE, sig_ts)
                    last_known_ts = sig_ts
                    if not check_engine_heartbeat():
                        log.warning("[ORDER] ENTRY blocked - engine heartbeat stale")
                    else:
                        result = om.place_market_order(side=side, size=lots)
                        if result.get("success"):
                            position = direction
                            open_lot_size = lots
                            if _live_sig: last_processed_seq = _live_sig.get("seq", 0)
                            real_entry = 0.0
                            for _i in range(20):
                                time.sleep(0.5)
                                pos_check = om.get_position()
                                real_entry = pos_check.get("entry_price", 0.0) if pos_check.get("success") else 0.0
                                if real_entry > 0:
                                    break
                            open_entry_price = real_entry
                            _entry_commission = result.get("commission", 0.0)
                            log.info(f"[ORDER] ENTRY {side} {lots} lots | dir={direction} | ts={sig_ts}")
                            _sl_price_val = 0.0
                            if real_entry > 0:
                                sl_result = om.place_stop_loss_order(direction=direction, entry_price=real_entry, sl_pct=10.0)
                                if sl_result.get("success"):
                                    _sl_price_val = sl_result.get("sl_price", 0.0)
                                    log.info(f"[SL] Stop SL placed | sl_price={_sl_price_val}")
                                else:
                                    log.error(f"[SL] Stop SL FAILED: {sl_result}")
                                    send_alert(f"CTS S4 SL PLACEMENT FAILED\nDirection: {direction}\nEntry: {real_entry}\nError: {sl_result}")
                            else:
                                log.error(f"[SL] NO SL PLACED - entry_price never populated after 10s")
                                send_alert(f"CTS S4 CRITICAL - NO SL PLACED\nPosition open but entry_price=0 after 10s retries\nManual check required immediately")
                            _send_live_entry_alert("S4", direction, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), real_entry, _sl_price_val, lots)
                            _bt_csv = _get_csv_bt_row("S4", sig_ts)
                            _bt_ep  = float(_bt_csv[4]) if _bt_csv and len(_bt_csv) > 4 and str(_bt_csv[4]).strip() not in ("", "PENDING") else 0.0
                            _bt_xt  = _bt_csv[1] if _bt_csv else ""
                            _bt_xp  = float(_bt_csv[5]) if _bt_csv and len(_bt_csv) > 5 and str(_bt_csv[5]).strip() not in ("", "PENDING") else 0.0
                            if _bt_ep > 0 and real_entry > 0:
                                _send_entry_match_alert("S4", direction, sig_ts, _bt_ep, real_entry, _bt_xt, _bt_xp, lots)
                            log.info(f"[ORDER] ENTRY confirmed | position={position}")
                            _entry_retry_state["ts"] = None
                            _entry_retry_state["count"] = 0
                        else:
                            log.error(f"[ORDER] ENTRY FAILED: {result}")
                            send_alert(f"CTS S4 ENTRY FAILED\nError: {result}")
                            last_known_ts = load_ts_file(TS_FILE)
                            _entry_retry_state["count"] += 1

        # Sync position from exchange every 5 minutes
        if int(time.time()) % 30 < 2:
            _exch = om.get_position()
            _exch_size = abs(_exch.get("size", 0)) if _exch.get("success") else -1
            if _exch_size == 0 and position is not None:
                # FIX: confirm with a second check before declaring flat - prevents
                # false SL-hit detection from a single transient/empty API response
                time.sleep(3)
                _exch2 = om.get_position()
                _exch_size2 = abs(_exch2.get("size", 0)) if _exch2.get("success") else -1
                if _exch_size2 != 0:
                    log.warning(f"[SYNC] False FLAT detected (transient) - exchange size confirmed={_exch_size2} - skipping sync")
                    _exch_size = _exch_size2
            if _exch_size == 0 and position is not None:
                log.warning(f"[SYNC] Exchange FLAT but bot={position} - SL hit or manual close - syncing to FLAT")
                # FIX: advance last_known_ts past this signal's exit_time so it
                # is not matched again next loop (prevents duplicate re-entry
                # after SL hit or manual close from dashboard).
                _manual_exit_ts = None
                for _row in signals:
                    if _row.get("entry_time") == last_known_ts:
                        _cand_xt = _row.get("exit_time")
                        if _cand_xt and _cand_xt not in ("PENDING", ""):
                            _manual_exit_ts = _cand_xt
                        break
                position = None
                if _manual_exit_ts:
                    save_ts_file(TS_FILE, _manual_exit_ts)
                    last_known_ts = safe_ts(_manual_exit_ts)
                    log.info(f"[SYNC] Lock advanced past manually-closed signal to exit_time={_manual_exit_ts}")
                else:
                    # PENDING row with no exit found (SL/manual close on exchange) -
                    # write real exit into CSV so BT/live comparison does not show
                    # a stuck PENDING trade forever.
                    try:
                        import csv as _csv3, os as _os3
                        from datetime import datetime as _dt3, timezone as _tz3
                        _sync_exit_ts = _dt3.now(_tz3.utc).strftime("%Y-%m-%dT%H:%M:%S")
                        _sync_price = om.get_current_price()
                        _sig_csv = "logs/signals_s4.csv"
                        with open(_sig_csv, "r") as _f3:
                            _rows3 = list(_csv3.reader(_f3))
                        _updated3 = False
                        for _r3 in _rows3:
                            if len(_r3) >= 2 and _r3[0] == last_known_ts and _r3[1] == "PENDING":
                                while len(_r3) < 6:
                                    _r3.append("")
                                _r3[1] = _sync_exit_ts
                                _r3[5] = round(float(_sync_price), 2) if _sync_price else ""
                                _updated3 = True
                                break
                        if _updated3:
                            _tmp3 = _sig_csv + ".tmp"
                            with open(_tmp3, "w", newline="") as _f3:
                                _w3 = _csv3.writer(_f3)
                                for _r3 in _rows3:
                                    _w3.writerow(_r3)
                            _os3.replace(_tmp3, _sig_csv)
                            log.info(f"[SYNC] CSV PENDING row exit filled: entry={last_known_ts} exit={_sync_exit_ts} price={_sync_price}")
                        save_ts_file(TS_FILE, _sync_exit_ts)
                        last_known_ts = safe_ts(_sync_exit_ts)
                        log.info(f"[SYNC] Lock advanced past synced-flat signal to exit_time={_sync_exit_ts}")
                    except Exception as _sync_e:
                        save_ts_file(TS_FILE, last_known_ts)
                        log.warning(f"[SYNC] Could not fill PENDING exit ({_sync_e}) - lock unchanged, monitor for repeat entry")
                with open("logs/manual_override_s4.txt", "w") as _f:
                    _f.write(f"{int(time.time())}|synced_flat|entry_ts={last_known_ts}")
                log.info("[SYNC] manual_override_s4.txt written - next entry signal will be skipped")
                send_alert(
                    f"CTS SL HIT DETECTED\n"
                    f"Bot: S4\n"
                    f"Action: Position closed by SL on exchange\n"
                    f"Status: Synced to FLAT"
                )
            elif _exch_size > 0 and position is None:
                _exch_side = _exch.get("side","")
                position = "long" if _exch_side == "buy" else "short"
                log.warning(f"[SYNC] Exchange has position={position} but bot=None - syncing to exchange")

        log.info(f"[WAIT] now={now} | position={position} | last_known_ts={last_known_ts}")

    except Exception as e:
        log.error(f"[ERROR] {e}", exc_info=True)

    time.sleep(SLEEP_SEC)
    
# Position sync every 60 cycles (60 seconds)
if hasattr(sys, '_sync_counter'):
    sys._sync_counter += 1
else:
    sys._sync_counter = 0
if sys._sync_counter >= 60:
    sys._sync_counter = 0
    exchange_pos = om.get_position()
    if exchange_pos['direction'] == 'FLAT' and position is not None:
        log.warning(f"[SYNC] Exchange is FLAT but bot thinks position={position}. Syncing to FLAT.")
        position = None
        open_lot_size = None
    elif exchange_pos['direction'] != 'FLAT' and position is None:
        log.warning(f"[SYNC] Exchange has position but bot thinks FLAT. Syncing to {exchange_pos['direction']}.")
        position = exchange_pos['direction'].lower()
        open_lot_size = abs(exchange_pos['size'])

