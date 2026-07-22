#!/usr/bin/env python3
"""
live_signal_generator.py
========================
Renko Chart Engine - runs 24/7 like chart always open.
Runs backtest every 60 seconds.
Detects new signals and writes to signal files instantly.
Bot watches signal files every second and copies order immediately.
Zero calculation in bot. Pure copy trading of backtest.
"""
import os, sys, time, logging, csv
sys.path.insert(0, "/home/anildalabanjan933/crypto_trading_system")
os.chdir("/home/anildalabanjan933/crypto_trading_system")

from datetime import datetime, timezone, timedelta
import warnings, io, contextlib
warnings.filterwarnings("ignore")

from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
from engine.backtest_engine import BacktestEngine
from data.download_market_data import download_or_update

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("logs/live_signal_generator.log", mode="a"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

REPO     = "/home/anildalabanjan933/crypto_trading_system"
CSV_PATH = "data/btc_1m_delta.csv"
LOT_SIZE = 100
SLEEP_SEC = 60

S2_PARAMS = dict(renko_box_pct=0.001, renko_timeframe="1h", st_atr_length=5, st_factor=1.5)
S4_PARAMS = dict(renko_box_pct=0.001, renko_timeframe="2h", st_atr_length=10, st_factor=2.0,
                 smiio_shortlen=20, smiio_siglen=7)

# Track last signal to detect new ones
last_s2_signal = None
last_s4_signal = None

def load_last_signals():
    global last_s2_signal, last_s4_signal
    try:
        if os.path.exists("logs/live_signal_s2.txt"):
            last_s2_signal = open("logs/live_signal_s2.txt").read().strip()
    except: pass
    try:
        if os.path.exists("logs/live_signal_s4.txt"):
            last_s4_signal = open("logs/live_signal_s4.txt").read().strip()
    except: pass
    log.info(f"[GENERATOR] Last S2 signal: {last_s2_signal}")
    log.info(f"[GENERATOR] Last S4 signal: {last_s4_signal}")

def write_signal(signal_file, sig_type, direction, timestamp_str, lots):
    signal_line = f"{sig_type}_{direction.upper()}|{timestamp_str}|{lots}"
    tmp = signal_file + ".tmp"
    with open(tmp, "w") as f:
        f.write(signal_line)
    os.replace(tmp, signal_file)
    log.info(f"[GENERATOR] Signal written: {signal_file} -> {signal_line}")

def run_backtest(strategy_class, params, label):
    end = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        engine = BacktestEngine(
            strategy_class=strategy_class,
            symbol="BTCUSD",
            lot_size=LOT_SIZE,
            start_date="2024-01-10",
            end_date=end,
            csv_path=CSV_PATH,
            strategy_params=params,
            slippage=5.0
        )
        result = engine.run()
    return result.get("trades", [])

def check_new_signal(trades, last_signal, signal_file, label):
    global last_s2_signal, last_s4_signal
    if not trades:
        return
    last_trade = trades[-1]
    entry_dt = str(last_trade.get("entry_datetime", ""))
    exit_dt  = str(last_trade.get("exit_datetime",  ""))
    direction = str(last_trade.get("direction", ""))

    now_utc = datetime.now(timezone.utc)

    # Parse exit time
    try:
        exit_time = datetime.strptime(exit_dt[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except:
        return

    # Parse entry time
    try:
        entry_time = datetime.strptime(entry_dt[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except:
        return

    # Determine signal type
    if exit_time > now_utc:
        # Position should be open = ENTRY signal
        sig_type = "ENTRY"
        sig_ts   = entry_dt[:19]
    else:
        # Position should be closed = EXIT signal
        sig_type = "EXIT"
        sig_ts   = exit_dt[:19]

    sig_line = f"{sig_type}_{direction.upper()}|{sig_ts}|{LOT_SIZE}"

    # Only write if new signal different from last
    if sig_line != last_signal:
        write_signal(signal_file, sig_type, direction, sig_ts, LOT_SIZE)
        if label == "S2":
            last_s2_signal = sig_line
        else:
            last_s4_signal = sig_line
        log.info(f"[{label}] NEW signal detected: {sig_line}")
    else:
        log.info(f"[{label}] No new signal")

def update_market_data():
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            download_or_update("BTC")
        log.info("[GENERATOR] Market data updated")
    except Exception as e:
        log.error(f"[GENERATOR] Market data update failed: {e}")

if __name__ == "__main__":
    log.info("[GENERATOR] Live Signal Generator starting...")
    load_last_signals()
    while True:
        try:
            log.info("[GENERATOR] Updating market data...")
            update_market_data()

            log.info("[GENERATOR] Running S2 backtest...")
            s2_trades = run_backtest(RenkoReversalStrategy, S2_PARAMS, "S2")
            check_new_signal(s2_trades, last_s2_signal, "logs/live_signal_s2.txt", "S2")

            log.info("[GENERATOR] Running S4 backtest...")
            s4_trades = run_backtest(RenkoSMIIOSupertrendStrategy, S4_PARAMS, "S4")
            check_new_signal(s4_trades, last_s4_signal, "logs/live_signal_s4.txt", "S4")

        except Exception as e:
            log.error(f"[GENERATOR] Error: {e}", exc_info=True)

        log.info(f"[GENERATOR] Sleeping {SLEEP_SEC} seconds...")
        time.sleep(SLEEP_SEC)
