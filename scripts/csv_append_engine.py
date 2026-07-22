#!/usr/bin/env python3
"""
csv_append_engine.py
====================
Single Source of Truth Engine.
Runs full backtest every 60s.
Appends new trade to CSV directly when signal found.
Bot watches CSV last row = 100% real copy trading.
Same CSV = Section 13/14 = Manual backtest = Bot signal = always identical.
"""
import os, sys, time, logging, glob, shutil
sys.path.insert(0, "/home/anildalabanjan933/crypto_trading_system")
os.chdir("/home/anildalabanjan933/crypto_trading_system")

from datetime import datetime, timezone, timedelta
import warnings, io, contextlib, pandas as pd
warnings.filterwarnings("ignore")

from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
from engine.backtest_engine import BacktestEngine
from data.download_market_data import download_or_update

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("logs/csv_append_engine.log", mode="a"),
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

def get_trade_csv(label):
    if label == "S2":
        pattern = "output/trade_log_RenkoReversalStrategy_BTCUSD_*.csv"
    else:
        pattern = "output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv"
    files = sorted(glob.glob(pattern), reverse=True)
    return files[0] if files else None

def get_last_csv_row(label):
    """Get last trade row from existing CSV."""
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
    """Append single new trade row to existing CSV. Atomic write."""
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
    """Also write signal file for bot compatibility."""
    sig_line = f"{sig_type}_{direction.upper()}|{sig_ts}|{LOT_SIZE}"
    sig_file = f"logs/live_signal_s{label[-1]}.txt"
    tmp = sig_file + ".tmp"
    open(tmp, "w").write(sig_line)
    os.replace(tmp, sig_file)
    log.info(f"[{label}] Signal file written: {sig_line}")

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

def update_market_data():
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            download_or_update("BTC")
        log.info("[ENGINE] Market data updated")
    except Exception as e:
        log.error(f"[ENGINE] Market data update failed: {e}")

def check_and_append(trades, label):
    """
    Compare backtest last trade vs CSV last row.
    If new trade found = append to CSV + write signal file.
    """
    if not trades:
        log.info(f"[{label}] No trades from backtest")
        return

    last_bt = trades[-1]
    entry_dt = str(last_bt.get("entry_datetime", ""))[:19]
    exit_dt  = str(last_bt.get("exit_datetime",  ""))[:19]
    direction = str(last_bt.get("direction", ""))
    now_utc  = datetime.now(timezone.utc)

    # Get last row from CSV
    last_csv = get_last_csv_row(label)
    last_csv_entry = str(last_csv.get("entry_datetime", ""))[:19] if last_csv else ""

    # Check if this is a new trade not yet in CSV
    if entry_dt != last_csv_entry:
        log.info(f"[{label}] NEW trade detected: {entry_dt} {direction}")
        # Append to CSV
        append_trade_to_csv(last_bt, label)
        # Determine signal type for bot
        try:
            exit_time = datetime.strptime(exit_dt, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            sig_type = "ENTRY" if exit_time > now_utc else "EXIT"
            sig_ts   = entry_dt if sig_type == "ENTRY" else exit_dt
        except:
            sig_type = "EXIT"
            sig_ts   = exit_dt
        write_signal_file(label, sig_type, direction, sig_ts)
    else:
        # Same trade - check if exit signal needed
        try:
            exit_time = datetime.strptime(exit_dt, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            if exit_time <= now_utc:
                sig_type = "EXIT"
                sig_ts   = exit_dt
                # Write exit signal if not already written
                sig_file = f"logs/live_signal_s{label[-1]}.txt"
                current = open(sig_file).read().strip() if os.path.exists(sig_file) else ""
                new_sig  = f"EXIT_{direction.upper()}|{sig_ts}|{LOT_SIZE}"
                if current != new_sig:
                    write_signal_file(label, sig_type, direction, sig_ts)
                    log.info(f"[{label}] EXIT signal updated")
                else:
                    log.info(f"[{label}] No new signal")
            else:
                log.info(f"[{label}] No new signal - position still open")
        except Exception as e:
            log.error(f"[{label}] check exit error: {e}")

if __name__ == "__main__":
    log.info("[ENGINE] CSV Append Engine starting...")
    log.info("[ENGINE] Single source of truth: backtest CSV")
    log.info("[ENGINE] Bot reads CSV last row = 100% copy trading")
    while True:
        try:
            log.info("[ENGINE] Updating market data...")
            update_market_data()

            log.info("[ENGINE] Running S2 backtest...")
            s2_trades = run_backtest(RenkoReversalStrategy, S2_PARAMS, "S2")
            check_and_append(s2_trades, "S2")

            log.info("[ENGINE] Running S4 backtest...")
            s4_trades = run_backtest(RenkoSMIIOSupertrendStrategy, S4_PARAMS, "S4")
            check_and_append(s4_trades, "S4")

        except Exception as e:
            log.error(f"[ENGINE] Error: {e}", exc_info=True)

        log.info(f"[ENGINE] Sleeping {SLEEP_SEC} seconds...")
        time.sleep(SLEEP_SEC)
