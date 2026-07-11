# run_live_trading_s2.py — S2: RenkoReversalStrategy
import time, os, datetime, math
# REMOVED: post_signal call
from dotenv import load_dotenv
load_dotenv()
import logging, pandas as pd
from engine.order_manager import OrderManager
from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from config.symbol_config import get_renko_box_size

logging.basicConfig(
    filename="logs/live_trading_s2.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger(__name__)

SYMBOL     = "BTCUSD"
LOT_SIZE   = 100
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
df_1m["timestamp"] = pd.to_datetime(df_1m["Date"] + " " + df_1m["Time"])
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
    url      = "https://cdn-ind.testnet.deltaex.org/v2/history/candles"
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
    _box_init   = get_renko_box_size(SYMBOL, float(_df_1h_init["close"].iloc[-1]))
    _strat_init = RenkoReversalStrategy(
        data_dict={"1h": _df_1h_init}, lot_size=LOT_SIZE,
        renko_box=_box_init, renko_timeframe="1h"
    )
    _sigs_init    = _strat_init.generate_signals()
    last_known_ts = _sigs_init[-1].get("timestamp") if _sigs_init else None
    log.info(f"[STARTUP] last_known_ts={last_known_ts} | total signals={len(_sigs_init)}")
except Exception as _e:
    last_known_ts = None
    log.warning(f"[STARTUP] Could not pre-load signals: {_e}")

while True:
    try:
        last_ts     = df_1m.index[-1]
        new_candles = fetch_latest_1m(since=last_ts)
        if new_candles is not None and len(new_candles) > 0:
            new_candles = new_candles[new_candles.index > last_ts]
            if len(new_candles) > 0:
                df_1m = pd.concat([df_1m, new_candles]).sort_index()
                log.info(f"[DATA] Appended {len(new_candles)} candles. Total={len(df_1m)}")

        df_1h = build_1h(df_1m)
        log.info(f"[DATA] 1H candles={len(df_1h)}")

        box_size = get_renko_box_size(SYMBOL, float(df_1h["close"].iloc[-1]))
        strategy = RenkoReversalStrategy(
            data_dict={"1h": df_1h}, lot_size=LOT_SIZE,
            renko_box=box_size, renko_timeframe="1h"
        )
        signals = strategy.generate_signals()
        log.info(f"[SIGNALS] total={len(signals)}")

        # --- Only process signals newer than last known ts ---
        new_signals = [
            s for s in signals
            if last_known_ts is None or str(s.get("timestamp", "")) > str(last_known_ts)
        ]

        if new_signals:
            # Take the latest signal only
            sig   = new_signals[-1]
            stype = sig.get("signal_type")
            sdir  = sig.get("direction", "")
            sig_ts = sig.get("timestamp")

            if stype == "ENTRY" and position is None:
                side = "buy" if sdir == "long" else "sell"
                om.place_market_order(side=side, size=LOT_SIZE)
# REMOVED: post_signal call
                position = sdir
                last_known_ts = sig_ts
                log.info(f"[ORDER] ENTRY {side} {LOT_SIZE} lots | type={sig.get("entry_type")} | ts={sig_ts}")

            elif stype == "EXIT" and position is not None:
                side = "sell" if position == "long" else "buy"
                om.close_position(size=LOT_SIZE, side=side)
# REMOVED: post_signal call
                position = None
                last_known_ts = sig_ts
                log.info(f"[ORDER] EXIT {side} {LOT_SIZE} lots | type={sig.get("exit_type")} | ts={sig_ts}")
        else:
            log.info(f"[WAIT] No new signals since {last_known_ts}")

    except Exception as e:
        log.error(f"[ERROR] {e}", exc_info=True)

    time.sleep(CYCLE_SEC)
