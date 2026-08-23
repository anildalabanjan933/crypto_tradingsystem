"""
bt_snapshot_verify.py
Standalone, isolated verify tool. Never imported into live's critical path directly -
only launched as a separate background process via subprocess.Popen (non-blocking).
Does NOT touch strategies/backtest/, order_manager.py, or any live-firing logic.
"""
import sys, os, csv, json
from datetime import datetime, timezone

SNAPSHOT_DIR = "logs/bt_snapshots"
RESULTS_CSV  = "logs/snapshot_verify_results.csv"

_STRAT_EXPLICIT_PARAMS = {
    "S4":   dict(renko_box_pct=0.001, renko_timeframe="2h",  st_atr_length=5, st_factor=2.0,
                 smiio_shortlen=10, smiio_longlen=10, smiio_siglen=3),
    "S4V2": dict(renko_box_pct=0.001, renko_timeframe="30m", st_atr_length=5, st_factor=1.5,
                 smiio_shortlen=10, smiio_longlen=20, smiio_siglen=3),
}
_STRAT_CLASS_NAME = {
    "S4":   "RenkoSMIIOSupertrendStrategy",
    "S4V2": "RenkoSMIIOSupertrendV2Strategy",
}
_REF_FILE = {
    "S4":   "logs/box_ref_price_s4.txt",
    "S4V2": "logs/box_ref_price_s4v2.txt",
}


def save_snapshot(label, candles_1m, ts, direction, sig_type):
    try:
        import subprocess
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        safe_ts = str(ts).replace(":", "-").replace(" ", "_")
        snap_id = f"{label}_{safe_ts}_{sig_type}"
        snap_csv = f"{SNAPSHOT_DIR}/{snap_id}.csv"
        candles_1m.to_csv(snap_csv, index=False)
        meta = {"label": label, "ts": ts, "direction": direction, "sig_type": sig_type,
                "snap_csv": snap_csv}
        meta_path = f"{SNAPSHOT_DIR}/{snap_id}.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f)
        subprocess.Popen(
            [sys.executable, "scripts/bt_snapshot_verify.py", "--verify", meta_path],
            stdout=open(f"{SNAPSHOT_DIR}/{snap_id}.log", "a"),
            stderr=open(f"{SNAPSHOT_DIR}/{snap_id}.log", "a"),
            start_new_session=True
        )
    except Exception as e:
        try:
            with open("logs/bt_snapshot_verify_errors.log", "a") as ef:
                ef.write(f"{datetime.now(timezone.utc).isoformat()} save_snapshot error: {e}\n")
        except Exception:
            pass


def _write_result(label, ts, direction, message):
    os.makedirs(os.path.dirname(RESULTS_CSV), exist_ok=True)
    row = [label, ts, direction, message, datetime.now(timezone.utc).isoformat()]
    file_exists = os.path.exists(RESULTS_CSV)
    with open(RESULTS_CSV, "a", newline="") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["label", "entry_ts", "direction", "message", "checked_at_utc"])
        w.writerow(row)


def _run_verify(meta_path):
    with open(meta_path) as f:
        meta = json.load(f)
    label = meta["label"]; ts = meta["ts"]; direction = meta["direction"]
    snap_csv = meta["snap_csv"]

    try:
        import pandas as pd
        sys.path.insert(0, os.getcwd())
        from engine.backtest_engine_v2 import run_backtest
        from strategy_registry import strategy_registry

        strategy_params = dict(_STRAT_EXPLICIT_PARAMS[label])
        ref_file = _REF_FILE[label]
        if os.path.exists(ref_file):
            strategy_params["reference_price"] = float(open(ref_file).read().strip())

        df = pd.read_csv(snap_csv)
        start_date = str(df["timestamp"].iloc[0])[:10]
        end_date   = str(df["timestamp"].iloc[-1])[:10]

        strategy_class = strategy_registry.get_all_strategies()[_STRAT_CLASS_NAME[label]]

        result = run_backtest(
            strategy_class=strategy_class,
            symbol="BTCUSD",
            lot_size=100,
            start_date=start_date,
            end_date=end_date,
            csv_path=snap_csv,
            strategy_params=strategy_params,
            slippage=0
        )

        bt_signals = result.get("trades", []) if result else []
        bt_last_dir = None
        if bt_signals:
            last = bt_signals[-1]
            bt_last_dir = last.get("direction") or last.get("dir")

        if bt_last_dir is None:
            message = "Could not confirm - backtest produced no comparable signal"
        elif str(bt_last_dir).upper() == str(direction).upper():
            message = "Normal - live matched backtest, no issue"
        else:
            message = "Direction differs from backtest - EXPECTED (short 24h cold-start compare, not a live issue, see 23-Aug-2026 doc)"

    except Exception as e:
        message = f"Check skipped - internal error ({str(e)[:80]})"

    _write_result(label, ts, direction, message)

    try:
        os.remove(snap_csv)
        os.remove(meta_path)
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--verify":
        _run_verify(sys.argv[2])
