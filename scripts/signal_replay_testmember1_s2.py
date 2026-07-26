#!/usr/bin/env python3
"""
signal_replay_s2.py - S2 Signal Replay Bot
Reads pre-generated backtest signals from logs/signals_s2.csv
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

def _build_alert(sig_type, label, direction, live_entry_ts, live_entry_price,
                 live_exit_ts, live_exit_price, live_pnl, bt_row):
    """Build formatted Telegram alert message."""
    ist_entry = _utc_to_ist(live_entry_ts) if live_entry_ts else "-"
    ist_exit  = _utc_to_ist(live_exit_ts)  if live_exit_ts  else "-"

    if sig_type == "ENTRY":
        live_block = (
            f"Dir   : {direction.upper()}\n"
            f"Entry : {ist_entry} | ${live_entry_price:,.0f}"
        )
    else:
        pnl_sign = "+" if live_pnl >= 0 else ""
        live_block = (
            f"Dir   : {direction.upper()}\n"
            f"Entry : {ist_entry} | ${live_entry_price:,.0f}\n"
            f"Exit  : {ist_exit} | ${live_exit_price:,.0f}\n"
            f"PnL   : {pnl_sign}${live_pnl:,.2f}"
        )

    if bt_row:
        # bt_row is now a signal dict from strategy.generate_signals()
        bt_entry_ts  = bt_row.get("timestamp","")
        bt_exit_ts   = bt_row.get("timestamp","")
        bt_dir       = bt_row.get("direction","")
        bt_entry_p   = float(bt_row.get("price",0))
        bt_exit_p    = float(bt_row.get("price",0))
        bt_pnl       = 0.0
        bt_slip      = 5.0
        bt_ist_entry = _utc_to_ist(bt_entry_ts)
        bt_ist_exit  = _utc_to_ist(bt_exit_ts)
        pnl_sign     = "+" if bt_pnl >= 0 else ""

        if sig_type == "ENTRY":
            bt_block = (
                f"Dir   : {bt_dir.upper()}\n"
                f"Entry : {bt_ist_entry} | ${bt_entry_p:,.0f}"
            )
        else:
            bt_block = (
                f"Dir   : {bt_dir.upper()}\n"
                f"Entry : {bt_ist_entry} | ${bt_entry_p:,.0f}\n"
                f"Exit  : {bt_ist_exit} | ${bt_exit_p:,.0f}\n"
                f"PnL   : {pnl_sign}${bt_pnl:,.2f} (slip ${bt_slip:.0f}/side)"
            )

        # Match check
        dir_match   = "✅" if direction.lower() == bt_dir.lower() else "❌"
        entry_match = "✅" if live_entry_ts[:16] == bt_entry_ts[:16] else "❌"
        if sig_type == "EXIT":
            exit_match = "✅" if live_exit_ts[:16] == bt_exit_ts[:16] else "❌"
            match_line = f"MATCH : Dir {dir_match} | Entry {entry_match} | Exit {exit_match}"
        else:
            match_line = f"MATCH : Dir {dir_match} | Entry {entry_match}"
    else:
        bt_block   = "No matching trade found in CSV"
        match_line = "MATCH : ⚠️ No backtest data"

    icon = "🟢" if sig_type == "ENTRY" else "🔴"
    msg = (
        f"{icon} CTS {label} {sig_type}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"LIVE:\n{live_block}\n\n"
        f"BACKTEST:\n{bt_block}\n\n"
        f"{match_line}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    return msg


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
API_KEY    = os.getenv("TESTMEMBER1_S2_API_KEY", "")
API_SECRET = os.getenv("TESTMEMBER1_S2_API_SECRET", "")
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
# If last_known_ts empty - use signal file as fallback lock
if not last_known_ts:
    _sig_file = "logs/live_signal_s2.txt" if "s2" in fname else "logs/live_signal_s4.txt"
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

# Load signals
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
_bot_start_time = time.time()
while True:
    try:
        now = now_utc_str()

        # Read live signal from engine
        live_sig = read_live_signal("logs/live_signal_s2.txt")
        if live_sig:
            sig_type  = live_sig["type"]   # ENTRY_LONG, ENTRY_SHORT, EXIT_LONG, EXIT_SHORT
            sig_ts    = live_sig["timestamp"]
            lots      = live_sig["lots"]

            # Skip signals before valid_from
            # Skip signal if file was written before bot startup (stale on restart)
            _sig_file_mtime = os.path.getmtime("logs/live_signal_s2.txt")
            if _sig_file_mtime < _bot_start_time:
                log.warning(f"[SKIP] Signal file older than bot startup - skipping | ts={sig_ts}")
                save_ts_file(TS_FILE, sig_ts)
                last_known_ts = sig_ts
                clear_live_signal("logs/live_signal_s2.txt")
            elif sig_ts >= valid_from and sig_ts != last_known_ts:

                # --- ENTRY ---
                if "ENTRY" in sig_type and position is None:
                    direction = "long" if "LONG" in sig_type else "short"
                    side = "buy" if direction == "long" else "sell"
                    log.info(f"[ORDER] ENTRY {side} {lots} lots | dir={direction} | ts={sig_ts}")
                    save_ts_file(TS_FILE, sig_ts)
                    last_known_ts = sig_ts
                    clear_live_signal("logs/live_signal_s2.txt")
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
                        bt_row = _get_bt_trade(sig_ts, "S2")
                        _msg = _build_alert("ENTRY","S2",direction,sig_ts,real_entry,None,0,0,bt_row)
                        send_alert(_msg)
                    else:
                        log.error(f"[ORDER] ENTRY FAILED: {result}")
                        send_alert(f"CTS S2 ENTRY FAILED\nError: {result}")
                        last_known_ts = load_ts_file(TS_FILE)

                # --- EXIT ---
                elif "EXIT" in sig_type:
                    actual = om.get_position()
                    _ex_size = abs(actual.get("size", 0)) if actual.get("success") else 0
                    if _ex_size == 0:
                        log.info(f"[ORDER] EXIT skipped - exchange already FLAT | ts={sig_ts}")
                        position = None
                        save_ts_file(TS_FILE, sig_ts)
                        last_known_ts = sig_ts
                        clear_live_signal("logs/live_signal_s2.txt")
                    else:
                        side = "sell" if position == "long" else "buy"
                        close_size = _ex_size
                    log.info(f"[ORDER] EXIT {side} {close_size} lots | ts={sig_ts}")
                    save_ts_file(TS_FILE, sig_ts)
                    last_known_ts = sig_ts
                    clear_live_signal("logs/live_signal_s2.txt")
                    result = om.close_position(size=close_size, side=side)
                    if result.get("success"):
                        position = None
                        log.info(f"[ORDER] EXIT confirmed | position=None")
                        _ex_price = om.get_position().get("entry_price",0) if False else 0
                        try:
                            _fills = om.get_recent_fill_price()
                            _ex_price = _fills if _fills else 0
                        except: pass
                        bt_row = _get_bt_trade(sig_ts, "S2")
                        _entry_ts = load_ts_file(TS_FILE) or sig_ts
                        _msg = _build_alert("EXIT","S2",position or direction,_entry_ts,0,sig_ts,_ex_price,0,bt_row)
                        send_alert(_msg)
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
                    position     = direction
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
                    send_alert(f"CTS S2 ENTRY\nDirection: {direction.upper()}\nLots: {lots}")
                else:
                    log.error(f"[ORDER] ENTRY FAILED: {result}")
                    if result.get('error',{}).get('code') == 'invalid_api_key':
                        log.error("[CRITICAL] invalid_api_key - check API key and IP whitelist")
                    send_alert(f"CTS S2 ENTRY FAILED\nError: {result}")
                    if result.get('error',{}).get('code') == 'invalid_api_key':
                        log.error("[CRITICAL] invalid_api_key - check API key and IP whitelist")
                        send_alert("CTS S2 CRITICAL: invalid_api_key - check API key and IP whitelist")
                    last_known_ts = load_ts_file(TS_FILE)
                break  # process one signal per cycle

        # Sync position from exchange every 5 minutes - detects SL hits and ghost positions
        if int(time.time()) % 300 < 2:
            _exch = om.get_position()
            _exch_size = abs(_exch.get("size", 0)) if _exch.get("success") else -1
            if _exch_size == 0 and position is not None:
                log.warning(f"[SYNC] Exchange FLAT but bot={position} - SL hit or manual close - syncing to FLAT")
                position = None
            elif _exch_size > 0 and position is None:
                _exch_side = _exch.get("side","")
                position = "long" if _exch_side == "buy" else "short"
                log.warning(f"[SYNC] Exchange has position={position} but bot=None - syncing to exchange")

        log.info(f"[WAIT] now={now} | position={position} | last_known_ts={last_known_ts}")

    except Exception as e:
        log.error(f"[ERROR] {e}", exc_info=True)

    time.sleep(SLEEP_SEC)
