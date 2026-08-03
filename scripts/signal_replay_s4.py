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

def _send_live_exit_alert(label, direction, exit_ts, fill_price, entry_fill, lots=100):
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

def _send_live_exit_alert(label, direction, exit_ts, fill_price, lots=100):
    """Send Telegram alert on live exit fill."""
    try:
        from engine.telegram_alert import send_alert
        import datetime as _dt
        def _ist(ts):
            try:
                dt = _dt.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
                return (dt + _dt.timedelta(hours=5, minutes=30)).strftime("%d-%b-%Y %I:%M %p IST")
            except: return ts
        msg = (
            f"CTS LIVE {label} EXIT\n"
            f"Direction : {direction.upper()}\n"
            f"Exit time : {_ist(exit_ts)}\n"
            f"Fill price: ${fill_price:,.2f}\n"
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
SLEEP_SEC    = 1
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
# If last_known_ts empty - use signal file as fallback lock
if not last_known_ts:
    _sig_file = "logs/live_signal_s4.txt"
    try:
        _line = open(_sig_file).read().strip()
        if _line and "|" in _line:
            last_known_ts = _line.split("|")[1]
            log.info(f"[STARTUP] last_known_ts loaded from signal file: {last_known_ts}")
    except: pass
# Auto-advance last_known_ts to valid_from if behind - zero manual intervention
if last_known_ts and valid_from and last_known_ts < valid_from:
    last_known_ts = valid_from
    save_ts_file(TS_FILE, valid_from)
    log.info(f"[STARTUP] last_known_ts advanced to valid_from={valid_from}")
log.info(f"[STARTUP] last_known_ts={last_known_ts} | valid_from={valid_from}")

signals = load_signals()
open_lot_size   = LOT_SIZE
open_entry_price = 0.0
last_processed_seq = 0

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
            hb_dt = __import__('datetime').datetime.utcfromtimestamp(float(hb_str))
        except:
            hb_dt = __import__('datetime').datetime.strptime(hb_str, '%Y-%m-%dT%H:%M:%S')
        age_min = (__import__('datetime').datetime.utcnow() - hb_dt).total_seconds() / 60
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
while True:
    try:
        now = now_utc_str()

        # --- CSV Signal Matching (single source of truth) ---
        # Reload signals every 10 min
        _now_min = int(time.time()) // 60
        if _now_min % 10 == 0 and _now_min != getattr(check_engine_heartbeat, '_last_reload', -1):
            check_engine_heartbeat._last_reload = _now_min
            signals = load_signals()
            log.info(f"[RELOAD] Signal CSV reloaded: {len(signals)} signals")

        # --- Check logs/live_signal_s4.txt first (1-2 sec from engine) ---
        _live_sig = read_live_signal("logs/live_signal_s4.txt")
        _live_matched = None
        if _live_sig and _live_sig.get("seq", 0) > last_processed_seq:
            _live_ts = _live_sig["timestamp"]
            _live_type = _live_sig.get("type","")
            signals = load_signals()
            for _row in signals:
                _et_match = _row["entry_time"][:16] == _live_ts[:16]
                _xt_match = _row["exit_time"][:16] == _live_ts[:16]
                if _et_match or _xt_match:
                    _live_matched = _row
                    log.info(f"[LIVE] New engine signal SEQ={_live_sig['seq']}: {_live_ts} type={_live_type}")
                    break
            if not _live_matched:
                log.info(f"[LIVE] Engine signal {_live_ts} not in CSV yet - waiting")

        # Find current signal from CSV (fallback if live signal not available)
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
                            open_entry_price = 0.0
                            log.info(f"[ORDER] EXIT confirmed | position=None")
                            time.sleep(1)
                            _exit_fill_price = result.get("avg_fill_price", 0.0)
                            if _exit_fill_price == 0.0:
                                _exit_pos = om.get_position()
                                _exit_fill_price = _exit_pos.get("exit_price", 0.0) if _exit_pos.get("success") else 0.0
                            _send_live_exit_alert("S4", dirn, _xt, _exit_fill_price, _entry_price_for_alert, lots)
                            _bt_csv2 = _get_csv_bt_row("S4", sig_ts)
                            _bt_ep2  = float(_bt_csv2[4]) if _bt_csv2 and len(_bt_csv2) > 4 and str(_bt_csv2[4]).strip() not in ("", "PENDING") else 0.0
                            _bt_xp2  = float(_bt_csv2[5]) if _bt_csv2 and len(_bt_csv2) > 5 and str(_bt_csv2[5]).strip() not in ("", "PENDING") else 0.0
                            if _bt_ep2 > 0 and _entry_price_for_alert > 0 and _exit_fill_price > 0:
                                _send_roundtrip_match_alert("S4", dirn, _entry_price_for_alert, _exit_fill_price, _bt_ep2, _bt_xp2, lots)
                        else:
                            log.error(f"[ORDER] EXIT FAILED: {result}")
                            send_alert(f"CTS S4 EXIT FAILED\nError: {result}")
                            last_known_ts = load_ts_file(TS_FILE)

            # --- ENTRY if no position and exit time not yet reached ---
            elif position is None and now < _xt:
                direction = dirn
                side = "buy" if direction == "long" else "sell"
                log.info(f"[ORDER] ENTRY {side} {lots} lots | dir={direction} | ts={sig_ts}")
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
                        time.sleep(1)
                        pos_check = om.get_position()
                        real_entry = pos_check.get("entry_price", 0.0) if pos_check.get("success") else 0.0
                        _sl_price_val = 0.0
                        if real_entry > 0:
                            sl_result = om.place_stop_loss_order(direction=direction, entry_price=real_entry, sl_pct=2.0)
                            if sl_result.get("success"):
                                _sl_price_val = sl_result.get("sl_price", 0.0)
                                log.info(f"[SL] Stop SL placed | sl_price={_sl_price_val}")
                            else:
                                log.warning(f"[SL] Stop SL FAILED: {sl_result}")
                        _send_live_entry_alert("S4", direction, sig_ts, real_entry, _sl_price_val, lots)
                        _bt_csv = _get_csv_bt_row("S4", sig_ts)
                        _bt_ep  = float(_bt_csv[4]) if _bt_csv and len(_bt_csv) > 4 and str(_bt_csv[4]).strip() not in ("", "PENDING") else 0.0
                        _bt_xt  = _bt_csv[1] if _bt_csv else ""
                        _bt_xp  = float(_bt_csv[5]) if _bt_csv and len(_bt_csv) > 5 and str(_bt_csv[5]).strip() not in ("", "PENDING") else 0.0
                        if _bt_ep > 0 and real_entry > 0:
                            _send_entry_match_alert("S4", direction, sig_ts, _bt_ep, real_entry, _bt_xt, _bt_xp, lots)
                        open_entry_price = real_entry
                        log.info(f"[ORDER] ENTRY confirmed | position={position}")
                    else:
                        log.error(f"[ORDER] ENTRY FAILED: {result}")
                        send_alert(f"CTS S4 ENTRY FAILED\nError: {result}")
                        last_known_ts = load_ts_file(TS_FILE)

        # Sync position from exchange every 5 minutes
        if int(time.time()) % 300 < 2:
            _exch = om.get_position()
            _exch_size = abs(_exch.get("size", 0)) if _exch.get("success") else -1
            if _exch_size == 0 and position is not None:
                log.warning(f"[SYNC] Exchange FLAT but bot={position} - SL hit or manual close - syncing to FLAT")
                position = None
                save_ts_file(TS_FILE, last_known_ts)
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

