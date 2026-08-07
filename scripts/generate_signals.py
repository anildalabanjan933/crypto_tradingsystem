#!/usr/bin/env python3
"""
generate_signals.py
Runs backtest for S4V2 and S4, exports signal CSVs to logs/
Run daily at 3AM UTC via systemd or manually.
Usage: .venv/bin/python3 scripts/generate_signals.py
"""
import sys, os, warnings, io, contextlib, csv
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

from datetime import datetime, timezone, timedelta
from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
from strategies.backtest.renko_smiio_supertrend_v2_strategy import RenkoSMIIOSupertrendV2Strategy
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
    # Detect trailing open ENTRY (dropped by TradeBuilder) - build PENDING row for signal CSV only
    # Does NOT touch trades list (PnL/dashboard) - only affects signal file bots read
    pending_row = None
    try:
        raw_signals = sorted(result.get("signals", []), key=lambda x: x.get("timestamp",""))
        _open = None
        for _s in raw_signals:
            _t = _s.get("signal_type","").upper()
            if _t == "ENTRY":
                _open = _s
            elif _t == "EXIT":
                _open = None
        if _open is not None:
            pending_row = {
                "entry_datetime": _open.get("timestamp",""),
                "exit_datetime":  "PENDING",
                "direction":      _open.get("direction",""),
                "entry_price":    _open.get("price",""),
                "exit_price":     ""
            }
            log.info(f"[GENERATE] {label}: trailing open trade found at {_open.get('timestamp')} - added as PENDING to signal CSV only")
    except Exception as _pe:
        log.warning(f"[GENERATE] {label}: pending row detection failed: {_pe}")
    # Capture exact reference price used for box_size - freeze for live engine
    # Only update on REAL signal generation runs (3AM daily), never on dashboard-refresh-only runs
    if "--skip-live-signals" not in sys.argv:
        try:
            tf = params.get("renko_timeframe")
            tf_df = engine.data_dict.get(tf)
            if tf_df is not None and len(tf_df) > 0:
                ref_price = float(tf_df["close"].iloc[0])
                sig_num = {"S4": "4", "S4V2": "4v2"}.get(label, "4")
                with open(f"logs/box_ref_price_s{sig_num}.txt", "w") as _bf:
                    _bf.write(str(ref_price))
                log.info(f"[GENERATE] {label}: box reference_price={ref_price} saved")
        except Exception as _e:
            log.warning(f"[GENERATE] {label}: box reference_price capture failed: {_e}")
    else:
        log.info(f"[GENERATE] {label}: box reference_price capture skipped (dashboard-refresh-only mode)")
    return trades, pending_row

def write_trade_log_csv(trades, label):
    import glob as _gl, pandas as _pd
    from datetime import datetime as _dt
    os.makedirs("output", exist_ok=True)
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    if label == "S4V2":
        out = f"output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_{ts}.csv"
        pattern = "output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv"
    else:
        out = f"output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_{ts}.csv"
        pattern = "output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv"
    for old_f in _gl.glob(pattern):
        os.remove(old_f)
    df = _pd.DataFrame(trades)
    df.to_csv(out, index=False)
    log.info(f"[GENERATE] Trade log saved: {out} ({len(trades)} rows)")

def merge_signal_csv(new_trades, csv_path):
    import csv as _csv
    merged = {}
    if os.path.exists(csv_path):
        with open(csv_path, "r") as f:
            for row in _csv.reader(f):
                if len(row) >= 3 and row[0]:
                    merged[row[0]] = {
                        "entry_datetime": row[0],
                        "exit_datetime": row[1] if len(row) > 1 else "",
                        "direction": row[2] if len(row) > 2 else "",
                        "entry_price": row[4] if len(row) > 4 else "",
                        "exit_price": row[5] if len(row) > 5 else "",
                    }
    for t in new_trades:
        key = str(t.get("entry_datetime",""))
        if key:
            merged[key] = t
    return [merged[k] for k in sorted(merged.keys())]

def write_signal_csv(trades, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        # NO header row - signal_replay bots read as headerless CSV
        for t in trades:
            entry = str(t.get("entry_datetime", ""))
            exit_ = str(t.get("exit_datetime",  ""))
            dirn  = str(t.get("direction",       ""))
            entry_price = t.get("entry_price", "")
            exit_price  = t.get("exit_price", "")
            writer.writerow([entry, exit_, dirn, LOT_SIZE, entry_price, exit_price])
    log.info(f"[GENERATE] Written: {out_path} ({len(trades)} rows)")

if __name__ == "__main__":
    _skip_live = "--skip-live-signals" in sys.argv
    update_csv()

    # S4V2 (replaces S2)
    s4v2_params = dict(renko_box_pct=0.001, renko_timeframe="30m", st_atr_length=5, st_factor=1.5,
                       smiio_shortlen=10, smiio_longlen=20, smiio_siglen=3)
    s4v2_trades, s4v2_pending = run_backtest(RenkoSMIIOSupertrendV2Strategy, s4v2_params, "S4V2")
    s4v2_trades = [t for t in s4v2_trades if "entry_datetime" in t]
    if not _skip_live:
        _s4v2_all = merge_signal_csv(s4v2_trades + ([s4v2_pending] if s4v2_pending else []), "logs/signals_s4v2.csv")
        write_signal_csv(_s4v2_all, "logs/signals_s4v2.csv")
    else:
        log.info("[GENERATE] Skipped logs/signals_s4v2.csv (dashboard-refresh-only mode)")
    write_trade_log_csv(s4v2_trades, "S4V2")

    # S4
    s4_params = dict(renko_box_pct=0.001, renko_timeframe="2h", st_atr_length=5, st_factor=2.0,
                     smiio_shortlen=10, smiio_longlen=10, smiio_siglen=3)
    s4_trades, s4_pending = run_backtest(RenkoSMIIOSupertrendStrategy, s4_params, "S4")
    s4_trades = [t for t in s4_trades if "entry_datetime" in t]
    if not _skip_live:
        _s4_all = merge_signal_csv(s4_trades + ([s4_pending] if s4_pending else []), "logs/signals_s4.csv")
        write_signal_csv(_s4_all, "logs/signals_s4.csv")
    else:
        log.info("[GENERATE] Skipped logs/signals_s4.csv (dashboard-refresh-only mode)")
    write_trade_log_csv(s4_trades, "S4")

    log.info("[GENERATE] All signal CSVs ready.")
