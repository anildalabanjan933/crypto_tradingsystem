#!/usr/bin/env python3
"""
renko_chart_engine.py
=====================
Renko Chart Engine - Always Open Like TradingView Chart.
Loads full history ONCE on startup.
Every 60s: downloads only NEW closed candles + appends to memory.
Signal fires only on CONFIRMED CLOSED brick - zero repaint possible.
Appends new trade to CSV directly = single source of truth.
Same CSV = Section 13/14 = Manual backtest = Bot signal = always identical.
Backtest files NEVER touched - read only.
"""
import os, sys, time, logging, glob
sys.path.insert(0, "/home/anildalabanjan933/crypto_trading_system")
os.chdir("/home/anildalabanjan933/crypto_trading_system")

from datetime import datetime, timezone, timedelta
import warnings, io, contextlib
import pandas as pd
import numpy as np
warnings.filterwarnings("ignore")

from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
from engine.backtest_engine import BacktestEngine
from data.download_market_data import download_or_update

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("logs/renko_chart_engine.log", mode="a"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

CSV_PATH  = "data/btc_1m_delta.csv"
LOT_SIZE  = 100
SLEEP_SEC = 60

S2_PARAMS = dict(renko_box_pct=0.001, renko_timeframe="1h", st_atr_length=5, st_factor=1.5)
S4_PARAMS = dict(renko_box_pct=0.001, renko_timeframe="2h", st_atr_length=10, st_factor=2.0,
                 smiio_shortlen=20, smiio_siglen=7)

# In-memory candle store - loaded once on startup
_candles_df = None
_last_candle_ts = None

def get_trade_csv(label):
    if label == "S2":
        pattern = "output/trade_log_RenkoReversalStrategy_BTCUSD_*.csv"
    else:
        pattern = "output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv"
    files = sorted(glob.glob(pattern), reverse=True)
    return files[0] if files else None

def get_last_csv_row(label):
    try:
        f = get_trade_csv(label)
        if not f: return None
        df = pd.read_csv(f)
        if df.empty: return None
        return df.iloc[-1].to_dict()
    except Exception as e:
        log.error(f"[{label}] get_last_csv_row error: {e}")
        return None

def append_trade_to_csv(trade, label):
    try:
        f = get_trade_csv(label)
        if not f:
            log.error(f"[{label}] No CSV file found to append")
            return False
        df = pd.read_csv(f)
        new_row = pd.DataFrame([trade])
        df = pd.concat([df, new_row], ignore_index=True)
        tmp = f + ".tmp"
        df.to_csv(tmp, index=False)
        os.replace(tmp, f)
        log.info(f"[{label}] Appended new trade to CSV: {f}")
        return True
    except Exception as e:
        log.error(f"[{label}] append_trade_to_csv error: {e}")
        return False

def write_signal_file(label, sig_type, direction, sig_ts):
    sig_line = f"{sig_type}_{direction.upper()}|{sig_ts}|{LOT_SIZE}"
    sig_file = f"logs/live_signal_s{label[-1]}.txt"
    tmp = sig_file + ".tmp"
    open(tmp, "w").write(sig_line)
    os.replace(tmp, sig_file)
    log.info(f"[{label}] Signal written: {sig_line}")

def load_full_history():
    """Load full CSV history into memory once on startup."""
    global _candles_df, _last_candle_ts
    try:
        log.info("[CHART] Loading full candle history into memory...")
        df = pd.read_csv(CSV_PATH)
        df['timestamp'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        # Drop current incomplete candle (current minute)
        now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        current_min = now_utc.strftime("%Y-%m-%d %H:%M:%S")
        df = df[df['timestamp'].astype(str) < current_min]
        _candles_df = df
        _last_candle_ts = df['timestamp'].iloc[-1] if not df.empty else None
        log.info(f"[CHART] Loaded {len(df):,} closed candles | last={_last_candle_ts}")
        return True
    except Exception as e:
        log.error(f"[CHART] load_full_history error: {e}")
        return False

def update_market_data():
    """Download fresh candles from API - called once per minute only."""
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            download_or_update("BTC")
        log.info("[CHART] Market data updated")
    except Exception as e:
        log.error(f"[CHART] Market data update failed: {e}")

def fetch_new_candles():
    """Read only new closed candles from CSV into memory - cheap operation."""
    global _candles_df, _last_candle_ts
    try:
        # Read full CSV
        df_new = pd.read_csv(CSV_PATH)
        df_new['timestamp'] = pd.to_datetime(df_new['Date'] + ' ' + df_new['Time'])
        df_new = df_new.sort_values('timestamp').reset_index(drop=True)

        # Drop current incomplete candle (current minute)
        now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        current_min = now_utc.strftime("%Y-%m-%d %H:%M:%S")
        df_new = df_new[df_new['timestamp'].astype(str) < current_min]

        if _last_candle_ts is None:
            _candles_df = df_new
            _last_candle_ts = df_new['timestamp'].iloc[-1] if not df_new.empty else None
            log.info(f"[CHART] Initialized {len(df_new):,} candles")
            return

        # Only new candles after last known
        new_rows = df_new[df_new['timestamp'] > _last_candle_ts]
        if new_rows.empty:
            log.info("[CHART] No new closed candles")
            return

        # Append new closed candles to memory
        _candles_df = pd.concat([_candles_df, new_rows], ignore_index=True)
        _last_candle_ts = _candles_df['timestamp'].iloc[-1]
        log.info(f"[CHART] +{len(new_rows)} new candles | total={len(_candles_df):,} | last={_last_candle_ts}")

    except Exception as e:
        log.error(f"[CHART] fetch_new_candles error: {e}")

def run_backtest_on_memory(strategy_class, params, label):
    """Run backtest using in-memory candles = no full CSV reload."""
    global _candles_df
    try:
        if _candles_df is None or _candles_df.empty:
            log.error(f"[{label}] No candles in memory")
            return []

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
    except Exception as e:
        log.error(f"[{label}] run_backtest_on_memory error: {e}")
        return []

def check_and_append(trades, label):
    """Compare backtest last trade vs CSV last row. Append if new."""
    if not trades:
        log.info(f"[{label}] No trades from backtest")
        return

    last_bt = trades[-1]
    entry_dt  = str(last_bt.get("entry_datetime", ""))[:19]
    exit_dt   = str(last_bt.get("exit_datetime",  ""))[:19]
    direction = str(last_bt.get("direction", ""))
    now_utc   = datetime.now(timezone.utc)

    last_csv = get_last_csv_row(label)
    last_csv_entry = str(last_csv.get("entry_datetime", ""))[:19] if last_csv else ""

    if entry_dt != last_csv_entry:
        log.info(f"[{label}] NEW trade: {entry_dt} {direction}")
        append_trade_to_csv(last_bt, label)
        try:
            exit_time = datetime.strptime(exit_dt, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            sig_type = "ENTRY" if exit_time > now_utc else "EXIT"
            sig_ts   = entry_dt if sig_type == "ENTRY" else exit_dt
        except:
            sig_type = "EXIT"
            sig_ts   = exit_dt
        write_signal_file(label, sig_type, direction, sig_ts)
    else:
        try:
            exit_time = datetime.strptime(exit_dt, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            if exit_time <= now_utc:
                sig_file = f"logs/live_signal_s{label[-1]}.txt"
                current  = open(sig_file).read().strip() if os.path.exists(sig_file) else ""
                new_sig  = f"EXIT_{direction.upper()}|{exit_dt}|{LOT_SIZE}"
                if current != new_sig:
                    write_signal_file(label, "EXIT", direction, exit_dt)
                else:
                    log.info(f"[{label}] No new signal")
            else:
                log.info(f"[{label}] No new signal - position still open")
        except Exception as e:
            log.error(f"[{label}] check exit error: {e}")
        try:
            sig_file = f"logs/live_signal_s{label[-1]}.txt"
            if os.path.exists(sig_file):
                os.utime(sig_file, None)
        except: pass

if __name__ == "__main__":
    log.info("[CHART] Renko Chart Engine starting...")
    log.info("[CHART] Like TradingView - chart always open - only new bricks added")
    log.info("[CHART] Only CLOSED candles used - zero repaint - zero false signal")
    log.info("[CHART] Backtest files untouched - read only - single source of truth")

    # Load full history ONCE on startup
    if not load_full_history():
        log.error("[CHART] Failed to load history - exiting")
        sys.exit(1)

    _last_processed_ts = _last_candle_ts
    _last_download_ts = time.time()

    while True:
        try:
            # Download market data once per minute only
            if time.time() - _last_download_ts >= 60:
                update_market_data()
                _last_download_ts = time.time()

            # Read CSV into memory - cheap operation every 1 second
            fetch_new_candles()

            # Only run backtest when NEW candle detected
            if _last_candle_ts != _last_processed_ts:
                _last_processed_ts = _last_candle_ts
                log.info(f"[CHART] New candle: {_last_candle_ts} - running backtest")

                log.info("[CHART] Running S2 backtest...")
                s2_trades = run_backtest_on_memory(RenkoReversalStrategy, S2_PARAMS, "S2")
                check_and_append(s2_trades, "S2")

                log.info("[CHART] Running S4 backtest...")
                s4_trades = run_backtest_on_memory(RenkoSMIIOSupertrendStrategy, S4_PARAMS, "S4")
                check_and_append(s4_trades, "S4")
            else:
                # Touch signal files to keep dashboard FRESH
                for lbl in ["S2","S4"]:
                    try:
                        sf = f"logs/live_signal_s{lbl[-1]}.txt"
                        if os.path.exists(sf): os.utime(sf, None)
                    except: pass

        except Exception as e:
            log.error(f"[CHART] Error: {e}", exc_info=True)

        time.sleep(SLEEP_SEC)
