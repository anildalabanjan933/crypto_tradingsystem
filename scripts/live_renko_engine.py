#!/usr/bin/env python3
import os, sys, json, time, logging, threading
import numpy as np
import pandas as pd
from datetime import datetime, timezone
sys.path.insert(0, "/home/anildalabanjan933/crypto_trading_system")
os.chdir("/home/anildalabanjan933/crypto_trading_system")
from indicators.renko import RenkoBuilder, SupertrendIndicator, SwingDetector, _trendline_value_at
from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
from dotenv import load_dotenv
load_dotenv(dotenv_path="/home/anildalabanjan933/crypto_trading_system/.env")
import websocket

WEBSOCKET_URL = "wss://socket.india.delta.exchange"
SYMBOL        = "BTCUSD"
LOT_SIZE      = 100
SIGNAL_S2     = "logs/live_signal_s2.txt"
SIGNAL_S4     = "logs/live_signal_s4.txt"
ENGINE_LOG    = "logs/live_renko_engine.log"
CANDLE_CSV    = "data/btc_1m_delta.csv"
S2_PARAMS     = dict(renko_box_pct=0.001, renko_timeframe="1h", st_atr_length=5, st_factor=1.5)
S4_PARAMS     = dict(renko_box_pct=0.001, renko_timeframe="2h", st_atr_length=10, st_factor=2.0, smiio_shortlen=20, smiio_siglen=7)

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(ENGINE_LOG, mode="a"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

candle_opens   = []
candle_highs   = []
candle_lows    = []
candle_closes  = []
candle_times   = []
candle_volumes = []
last_s2_bricks = 0
last_s4_bricks = 0
last_s2_signal = None
last_s4_signal = None
S2_BRICKS_FILE = "logs/last_s2_bricks.txt"
S4_BRICKS_FILE = "logs/last_s4_bricks.txt"
S2_SIGNAL_FILE_TRACK = "logs/last_s2_signal.txt"
S4_SIGNAL_FILE_TRACK = "logs/last_s4_signal.txt"

def load_last_state():
    global last_s2_bricks, last_s4_bricks, last_s2_signal, last_s4_signal
    try:
        if os.path.exists(S2_BRICKS_FILE):
            last_s2_bricks = int(open(S2_BRICKS_FILE).read().strip())
    except: pass
    try:
        if os.path.exists(S4_BRICKS_FILE):
            last_s4_bricks = int(open(S4_BRICKS_FILE).read().strip())
    except: pass
    try:
        if os.path.exists(S2_SIGNAL_FILE_TRACK):
            last_s2_signal = open(S2_SIGNAL_FILE_TRACK).read().strip()
    except: pass
    try:
        if os.path.exists(S4_SIGNAL_FILE_TRACK):
            last_s4_signal = open(S4_SIGNAL_FILE_TRACK).read().strip()
    except: pass
    log.info(f"[ENGINE] State loaded: s2_bricks={last_s2_bricks} s4_bricks={last_s4_bricks}")

def save_s2_state():
    open(S2_BRICKS_FILE, "w").write(str(last_s2_bricks))
    if last_s2_signal:
        open(S2_SIGNAL_FILE_TRACK, "w").write(last_s2_signal)

def save_s4_state():
    open(S4_BRICKS_FILE, "w").write(str(last_s4_bricks))
    if last_s4_signal:
        open(S4_SIGNAL_FILE_TRACK, "w").write(last_s4_signal)
lock = threading.Lock()

def load_historical_candles():
    global candle_opens, candle_highs, candle_lows, candle_closes, candle_times, candle_volumes
    try:
        df = pd.read_csv(CANDLE_CSV)
        df["dt"] = pd.to_datetime(df["Date"] + " " + df["Time"], utc=True)
        df = df.sort_values("dt").reset_index(drop=True)
        candle_opens   = df["Open"].astype(float).tolist()
        candle_highs   = df["High"].astype(float).tolist()
        candle_lows    = df["Low"].astype(float).tolist()
        candle_closes  = df["Close"].astype(float).tolist()
        candle_times   = df["dt"].tolist()
        candle_volumes = df["Volume"].astype(float).tolist()
        log.info(f"[ENGINE] Loaded {len(candle_closes)} historical candles")
    except Exception as e:
        log.error(f"[ENGINE] Failed to load historical candles: {e}")
        candle_closes = []
        candle_times  = []

def write_signal(signal_file, direction, timestamp_str, lots):
    signal_line = f"{direction.upper()}|{timestamp_str}|{lots}"
    tmp = signal_file + ".tmp"
    with open(tmp, "w") as f:
        f.write(signal_line)
    os.replace(tmp, signal_file)
    log.info(f"[ENGINE] Signal written: {signal_file} -> {signal_line}")

def run_s2_strategy():
    global last_s2_bricks, last_s2_signal
    try:
        if len(candle_closes) < 100:
            return
        closes  = np.array(candle_closes)
        times   = pd.DatetimeIndex(candle_times)
        df_1m   = pd.DataFrame({"open": np.array(candle_opens), "high": np.array(candle_highs), "low": np.array(candle_lows), "close": closes, "volume": np.array(candle_volumes)}, index=times)
        df_1h   = df_1m.resample("1h").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
        df_1h   = df_1h.dropna()
        if len(df_1h) < 10:
            return
        current_price = float(closes[0])
        box_size = max(1, round(current_price * S2_PARAMS["renko_box_pct"]))
        builder  = RenkoBuilder(box_size=box_size)
        renko_raw = builder.build(df_1h["close"].values)
        if renko_raw is None or len(renko_raw) == 0:
            return
        n_bricks = len(renko_raw)
        if n_bricks <= last_s2_bricks:
            return
        log.info(f"[S2] New brick! Total={n_bricks} was={last_s2_bricks}")
        last_s2_bricks = n_bricks
        save_s2_state()
        renko_raw["timestamp"] = renko_raw["bar_index"].apply(
            lambda idx: df_1h.index[idx] if idx < len(df_1h) else df_1h.index[-1]
        )
        strategy = RenkoReversalStrategy(data_dict={"1h": df_1h}, lot_size=LOT_SIZE, **S2_PARAMS)
        signals  = strategy.generate_signals()
        if not signals:
            return
        last_sig = signals[-1]
        ts_str   = last_sig["timestamp"]
        dirn     = last_sig["direction"]
        sig_type = last_sig["signal_type"]
        sig_key  = f"{sig_type}|{dirn}|{ts_str}"
        if sig_key == last_s2_signal:
            return
        last_s2_signal = sig_key
        save_s2_state()
        log.info(f"[S2] Signal: {sig_type} {dirn.upper()} at {ts_str}")
        write_signal(SIGNAL_S2, f"{sig_type}_{dirn.upper()}", ts_str, LOT_SIZE)
    except Exception as e:
        log.error(f"[S2] Error: {e}", exc_info=True)

def run_s4_strategy():
    global last_s4_bricks, last_s4_signal
    try:
        if len(candle_closes) < 200:
            return
        closes  = np.array(candle_closes)
        times   = pd.DatetimeIndex(candle_times)
        df_1m   = pd.DataFrame({"open": np.array(candle_opens), "high": np.array(candle_highs), "low": np.array(candle_lows), "close": closes, "volume": np.array(candle_volumes)}, index=times)
        df_2h   = df_1m.resample("2h").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
        df_2h   = df_2h.dropna()
        if len(df_2h) < 10:
            return
        current_price = float(closes[0])
        box_size = max(1, round(current_price * S4_PARAMS["renko_box_pct"]))
        builder  = RenkoBuilder(box_size=box_size)
        renko_raw = builder.build(df_2h["close"].values)
        if renko_raw is None or len(renko_raw) == 0:
            return
        n_bricks = len(renko_raw)
        if n_bricks <= last_s4_bricks:
            return
        log.info(f"[S4] New brick! Total={n_bricks} was={last_s4_bricks}")
        last_s4_bricks = n_bricks
        save_s4_state()
        renko_raw["timestamp"] = renko_raw["bar_index"].apply(
            lambda idx: df_2h.index[idx] if idx < len(df_2h) else df_2h.index[-1]
        )
        strategy = RenkoSMIIOSupertrendStrategy(data_dict={"2h": df_2h}, lot_size=LOT_SIZE, **S4_PARAMS)
        signals  = strategy.generate_signals()
        if not signals:
            return
        last_sig = signals[-1]
        ts_str   = last_sig["timestamp"]
        dirn     = last_sig["direction"]
        sig_type = last_sig["signal_type"]
        sig_key  = f"{sig_type}|{dirn}|{ts_str}"
        if sig_key == last_s4_signal:
            return
        last_s4_signal = sig_key
        save_s4_state()
        log.info(f"[S4] Signal: {sig_type} {dirn.upper()} at {ts_str}")
        write_signal(SIGNAL_S4, f"{sig_type}_{dirn.upper()}", ts_str, LOT_SIZE)
    except Exception as e:
        log.error(f"[S4] Error: {e}", exc_info=True)

def on_open(ws):
    log.info("[ENGINE] WebSocket connected")
    payload = {"type": "subscribe", "payload": {"channels": [{"name": "candlestick_1m", "symbols": [SYMBOL]}]}}
    ws.send(json.dumps(payload))
    log.info(f"[ENGINE] Subscribed candlestick_1m {SYMBOL}")

# Track last candle start time to detect completed candles
last_candle_start = None

def on_message(ws, message):
    global candle_opens, candle_highs, candle_lows, candle_closes, candle_times, candle_volumes, last_candle_start
    try:
        data = json.loads(message)
        if data.get("type") != "candlestick_1m":
            return
        close       = float(data.get("close", 0))
        open_       = float(data.get("open", close))
        high_       = float(data.get("high", close))
        low_        = float(data.get("low", close))
        vol_        = float(data.get("volume", 0))
        candle_start = data.get("candle_start_time", 0)
        if close <= 0 or candle_start == 0:
            return
        # Convert candle_start microseconds to datetime
        candle_dt = datetime.fromtimestamp(candle_start / 1e6, tz=timezone.utc)
        with lock:
            # Only process when NEW candle starts = previous candle is now complete
            if last_candle_start is None:
                last_candle_start = candle_start
                return
            if candle_start <= last_candle_start:
                # Same candle still forming - update OHLCV
                if candle_times and candle_dt == candle_times[-1]:
                    candle_closes[-1] = close
                    candle_highs[-1]  = max(candle_highs[-1], high_)
                    candle_lows[-1]   = min(candle_lows[-1], low_)
                return
            # New candle started = previous candle is complete
            # Add the completed candle close price
            prev_dt = datetime.fromtimestamp(last_candle_start / 1e6, tz=timezone.utc)
            last_candle_start = candle_start
            if candle_times and prev_dt <= candle_times[-1]:
                return
            candle_opens.append(open_)
            candle_highs.append(high_)
            candle_lows.append(low_)
            candle_closes.append(close)
            candle_times.append(prev_dt)
            candle_volumes.append(vol_)
            if len(candle_closes) > 10000:
                candle_opens   = candle_opens[-10000:]
                candle_highs   = candle_highs[-10000:]
                candle_lows    = candle_lows[-10000:]
                candle_closes  = candle_closes[-10000:]
                candle_times   = candle_times[-10000:]
                candle_volumes = candle_volumes[-10000:]
            log.info(f"[ENGINE] Completed candle: {prev_dt.strftime('%Y-%m-%dT%H:%M')} close={close}")
            run_s2_strategy()
            run_s4_strategy()
    except Exception as e:
        log.error(f"[ENGINE] Message error: {e}", exc_info=True)

def on_error(ws, error):
    log.error(f"[ENGINE] WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    log.warning(f"[ENGINE] WebSocket closed: {close_status_code} {close_msg}")

def main():
    log.info("[ENGINE] Live Renko Engine starting...")
    load_last_state()
    load_historical_candles()
    log.info(f"[ENGINE] Ready. Candles: {len(candle_closes)}")
    while True:
        try:
            ws = websocket.WebSocketApp(
                WEBSOCKET_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            log.error(f"[ENGINE] Connection failed: {e}")
        log.warning("[ENGINE] Reconnecting in 5 seconds...")
        time.sleep(5)

if __name__ == "__main__":
    main()
