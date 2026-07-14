#!/usr/bin/env python3
"""
generate_signals.py
Runs backtest for S2 and S4, exports signal CSVs to logs/
Run daily at 3AM UTC via systemd or manually.
Usage: .venv/bin/python3 scripts/generate_signals.py
"""
import sys, os, warnings, io, contextlib, csv
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

from datetime import datetime, timezone, timedelta
from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
from engine.backtest_engine import BacktestEngine
import subprocess, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

CSV_PATH   = "data/btc_1m_delta.csv"
START_DATE = "2024-01-10"
LOT_SIZE   = 100

def update_csv():
    log.info("[GENERATE] Updating market data CSV...")
    subprocess.run(
        [sys.executable, "data/download_market_data.py"],
        timeout=120, check=False
    )
    log.info("[GENERATE] CSV update done.")

def run_backtest(strategy_class, params, label):
    end = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        engine = BacktestEngine(
            strategy_class=strategy_class,
            symbol="BTCUSD",
            lot_size=LOT_SIZE,
            start_date=START_DATE,
            end_date=end,
            csv_path=CSV_PATH,
            strategy_params=params,
            slippage=5.0
        )
        result = engine.run()
    trades = result.get("trades", [])
    log.info(f"[GENERATE] {label}: {len(trades)} trades generated")
    return trades

def write_signal_csv(trades, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["entry_time", "exit_time", "direction", "lots"])
        for t in trades:
            entry = str(t.get("entry_datetime", ""))
            exit_ = str(t.get("exit_datetime",  ""))
            dirn  = str(t.get("direction",       ""))
            writer.writerow([entry, exit_, dirn, LOT_SIZE])
    log.info(f"[GENERATE] Written: {out_path} ({len(trades)} rows)")

if __name__ == "__main__":
    update_csv()

    # S2
    s2_params = dict(renko_box_pct=0.001, renko_timeframe="1h", st_atr_length=5, st_factor=1.5)
    s2_trades = run_backtest(RenkoReversalStrategy, s2_params, "S2")
    write_signal_csv(s2_trades, "logs/signals_s2.csv")

    # S4
    s4_params = dict(renko_box_pct=0.001, renko_timeframe="2h", st_atr_length=10, st_factor=2.0,
                     smiio_shortlen=20, smiio_siglen=7)
    s4_trades = run_backtest(RenkoSMIIOSupertrendStrategy, s4_params, "S4")
    write_signal_csv(s4_trades, "logs/signals_s4.csv")

    log.info("[GENERATE] All signal CSVs ready.")
