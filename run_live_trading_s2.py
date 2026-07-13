# run_live_trading_s2.py — S2: RenkoReversalStrategy
import time, os, datetime, math, json, re
# REMOVED: post_signal call
from dotenv import load_dotenv
load_dotenv()
import logging, pandas as pd
from engine.order_manager import OrderManager
from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy

logging.basicConfig(
    filename="logs/live_trading_s2.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger(__name__)

SYMBOL     = "BTCUSD"
LOT_SIZE   = 100  # default - overridden by algo_config.json

def get_lot_size():
    try:
        cfg = json.load(open('dashboard/algo_config.json'))
        for a in cfg.get('algos', []):
            if a.get('name') == 'S2':
                return int(a.get('lots', 100))
    except:
        pass
    return LOT_SIZE
CSV_PATH   = "data/btc_1m_delta.csv"
CYCLE_SEC  = 60          # fallback only
CANDLE_SEC = 3600        # 1H candle = 3600 seconds

def sleep_until_next_candle_close(candle_seconds, buffer_sec=5):
    """Sleep until next candle close + buffer. Matches backtest entry timing exactly."""
    now = datetime.now(timezone.utc).timestamp()
    next_close = (math.floor(now / candle_seconds) + 1) * candle_seconds
    sleep_secs = next_close - now + buffer_sec
    next_close_dt = datetime.fromtimestamp(next_close, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    log.info(f'[SLEEP] Next candle close: {next_close_dt} | Sleeping {sleep_secs:.0f}s')
    time.sleep(max(sleep_secs, 1))
API_KEY    = os.getenv("S2_API_KEY")
API_SECRET = os.getenv("S2_API_SECRET")

om = OrderManager(api_key=API_KEY, api_secret=API_SECRET, testnet=True)

log.info("[STARTUP] Loading 1M CSV history...")
df_1m = pd.read_csv(CSV_PATH)
df_1m["timestamp"] = pd.to_datetime(df_1m["Date"] + " " + df_1m["Time"], format="mixed")
df_1m = df_1m.rename(columns={
    "Open": "open", "High": "high",
    "Low": "low", "Close": "close", "Volume": "volume"
})
df_1m = df_1m.set_index("timestamp").sort_index()
log.info(f"[STARTUP] Loaded {len(df_1m)} 1M candles ({df_1m.index[0]} to {df_1m.index[-1]})")

def fetch_latest_1m(since):
    import requests
    since_ts = int(since.timestamp())
    now_ts   = int(time.time())
    url      = "https://api.india.delta.exchange/v2/history/candles"
    params   = {"symbol": SYMBOL, "resolution": "1m", "start": since_ts, "end": now_ts}
    resp     = requests.get(url, params=params, timeout=10)
    data     = resp.json()
    if not data.get("success") or not data.get("result"):
        return None
    rows = []
    for c in data["result"]:
        rows.append({
            "timestamp": datetime.datetime.fromtimestamp(c["time"]),
            "open": c["open"], "high": c["high"],
            "low": c["low"],   "close": c["close"], "volume": c["volume"]
        })
    df = pd.DataFrame(rows).set_index("timestamp").sort_index()
    return df

def build_1h(df):
    from datetime import datetime, timezone
    df_1h = df.resample("1h").agg(
        open=("open","first"), high=("high","max"),
        low=("low","min"),     close=("close","last"),
        volume=("volume","sum")
    ).dropna()
    return df_1h

# --- Position state ---
pos = om.get_position()
if pos.get("success") and pos.get("direction") == "LONG":
    position = "long"
elif pos.get("success") and pos.get("direction") == "SHORT":
    position = "short"
else:
    position = None
open_lot_size = get_lot_size()  # Initialize lot size
log.info(f"[STARTUP] Position synced from exchange: {position}")

# --- Fetch live candles first so last_known_ts covers all existing signals ---
log.info("[STARTUP] Fetching latest candles before pre-loading signals...")
try:
    _last_ts = df_1m.index[-1]
    _new = fetch_latest_1m(since=_last_ts)
    if _new is not None and len(_new) > 0:
        _new = _new[_new.index > _last_ts]
        if len(_new) > 0:
            df_1m = pd.concat([df_1m, _new]).sort_index()
            log.info(f"[STARTUP] Pre-fetched {len(_new)} candles. Total={len(df_1m)}")
except Exception as _e:
    log.warning(f"[STARTUP] Pre-fetch failed: {_e}")

# --- Pre-load signals from full data to get last known ts ---
log.info("[STARTUP] Pre-loading signals to find last known timestamp...")
try:
    _df_1h_init = build_1h(df_1m)
    _strat_init = RenkoReversalStrategy(
        data_dict={"1h": _df_1h_init}, lot_size=LOT_SIZE,
        renko_box_pct=0.001, renko_timeframe="1h",
        st_atr_length=5, st_factor=1.5
    )
    _sigs_init    = _strat_init.generate_signals()
    last_known_ts = _sigs_init[-1].get("timestamp") if _sigs_init else None
    log.info(f"[STARTUP] last_known_ts={last_known_ts} | total signals={len(_sigs_init)}")
except Exception as _e:
    last_known_ts = None
    log.warning(f"[STARTUP] Could not pre-load signals: {_e}")

# Load last_known_ts from file if exists (survives restart)
try:
    _ts_file = 'logs/last_known_ts_s2.txt'
    if os.path.exists(_ts_file):
        _saved_ts = open(_ts_file).read().strip()
        # FIX ROOT CAUSE 3: validate format - reject garbage/manual edits
        if _saved_ts and re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$', _saved_ts):
            if last_known_ts is None or str(_saved_ts) > str(last_known_ts):
                last_known_ts = _saved_ts
                log.info(f"[STARTUP] Loaded last_known_ts from file: {last_known_ts}")
        elif _saved_ts:
            log.warning(f"[STARTUP] Rejected invalid ts file value: {repr(_saved_ts)}")
except Exception as _e2:
    log.warning(f"[STARTUP] Could not load ts file: {_e2}")

# FIX ROOT CAUSE 1+2: reconcile exchange position vs last signal
# If exchange has open position but bot thinks FLAT (crash between ts-save and order)
# OR if bot thinks open but exchange is FLAT (crash after order but before position update)
try:
    _exch_pos = om.get_position()
    _exch_dir = None
    if _exch_pos.get('success'):
        if _exch_pos.get('direction') == 'LONG':
            _exch_dir = 'long'
        elif _exch_pos.get('direction') == 'SHORT':
            _exch_dir = 'short'

    if _exch_dir != position:
        log.warning(f"[STARTUP] Position mismatch: exchange={_exch_dir} bot={position} - syncing to exchange")
        position = _exch_dir
        if position is not None:
            # Find the entry signal for this open position from pre-loaded signals
            _entry_sigs = [s for s in (_sigs_init or [])
                           if s.get('signal_type') == 'ENTRY'
                           and s.get('direction') == position]
            if _entry_sigs:
                _last_entry = _entry_sigs[-1]
                _entry_ts   = _last_entry.get('timestamp')
                # Lock open_lot_size from exchange actual size
                _actual = om.get_position()
                if _actual.get('success') and abs(_actual.get('size', 0)) > 0:
                    open_lot_size = abs(_actual.get('size', open_lot_size))
                log.info(f"[STARTUP] Reconciled: position={position} | entry_ts={_entry_ts} | lots={open_lot_size}")
            else:
                log.warning(f"[STARTUP] Open position on exchange but no matching entry signal found")
        else:
            log.info(f"[STARTUP] Reconciled: both exchange and bot now FLAT")
except Exception as _e3:
    log.warning(f"[STARTUP] Reconciliation check failed: {_e3}")

while True:
    try:
        last_ts     = df_1m.index[-1]
        new_candles = fetch_latest_1m(since=last_ts)
        if new_candles is not None and len(new_candles) > 0:
            new_candles = new_candles[new_candles.index > last_ts]
            if len(new_candles) > 0:
                df_1m = pd.concat([df_1m, new_candles]).sort_index()
                log.info(f"[DATA] Appended {len(new_candles)} candles. Total={len(df_1m)}")

                # Sync new candles to CSV so backtest uses identical data


        df_1h = build_1h(df_1m)
        log.info(f"[DATA] 1H candles={len(df_1h)}")

        strategy = RenkoReversalStrategy(
            data_dict={"1h": df_1h}, lot_size=LOT_SIZE,
            renko_box_pct=0.001, renko_timeframe="1h",
            st_atr_length=5, st_factor=1.5
        )
        signals = strategy.generate_signals()
        log.info(f"[SIGNALS] total={len(signals)}")

        # --- Only process signals newer than last known ts ---
        new_signals = [
            s for s in signals
            if last_known_ts is None or str(s.get("timestamp", "")) > str(last_known_ts)
        ]

        if new_signals:
            # Process signals IN ORDER - EXIT first then ENTRY
            for sig in new_signals:
                stype  = sig.get("signal_type")
                sdir   = sig.get("direction", "")
                sig_ts = sig.get("timestamp")

                if stype == "EXIT" and position is not None:
                    side = "sell" if position == "long" else "buy"
                    # Save ts BEFORE order to prevent duplicate on crash/restart
                    last_known_ts = sig_ts
                    open('logs/last_known_ts_s2.txt','w').write(str(sig_ts))
                    # Use actual exchange position size to close correctly
                    actual = om.get_position()
                    close_size = abs(actual.get('size', open_lot_size)) if actual.get('success') else open_lot_size
                    result = om.close_position(size=close_size, side=side)
                    if result.get("success"):
                        position = None
                        log.info(f"[ORDER] EXIT {side} {close_size} lots | type={sig.get('exit_type')} | ts={sig_ts}")
                    else:
                        log.error(f"[ORDER] EXIT FAILED | error={result.get('error')} | ts={sig_ts}")
                        break  # Stop processing if exit failed

                elif stype == "ENTRY" and position is None:
                    side = "buy" if sdir == "long" else "sell"
                    # Save ts BEFORE order to prevent duplicate on crash/restart
                    last_known_ts = sig_ts
                    open('logs/last_known_ts_s2.txt','w').write(str(sig_ts))
                    open_lot_size = get_lot_size()  # Lock lot size at entry
                    result = om.place_market_order(side=side, size=open_lot_size)
                    if result.get("success"):
                        position = sdir
                        log.info(f"[ORDER] ENTRY {side} {open_lot_size} lots | type={sig.get('entry_type')} | ts={sig_ts}")
                    else:
                        log.error(f"[ORDER] ENTRY FAILED | error={result.get('error')} | ts={sig_ts}")
                        break  # Stop processing if entry failed

                else:
                    log.info(f"[SKIP] Signal blocked | sig_type={stype} | position={position} | ts={sig_ts}")
        else:
            log.info(f"[WAIT] No new signals since {last_known_ts}")

    except Exception as e:
        log.error(f"[ERROR] {e}", exc_info=True)

    time.sleep(CYCLE_SEC)
