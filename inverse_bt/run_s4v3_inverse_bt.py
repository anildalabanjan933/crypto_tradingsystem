# Backtest-only: original S4V3 vs inverse (side flipped). Run from project root.
# Usage: python3 inverse_bt/run_s4v3_inverse_bt.py [CUTOFF_YYYY-MM-DD]
import sys, os, io, contextlib, warnings
from datetime import datetime, timezone, timedelta
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

from engine.backtest_engine import BacktestEngine
from strategies.backtest.renko_smiio_cross_v3_strategy import RenkoSMIIOCrossV3Strategy
from inverse_bt.s4v3_inverse_strategy import RenkoSMIIOCrossV3InverseStrategy

CSV_PATH = "data/btc_1m_delta.csv"
START_DATE = "2024-01-10"
LOT_SIZE = 100
PARAMS = dict(renko_box_pct=0.001, renko_timeframe="4h",
              smiio_shortlen=5, smiio_longlen=10, smiio_siglen=3)
CUTOFF = sys.argv[1] if len(sys.argv) > 1 else None


def norm(s):
    return str(s).strip()[:19].replace(" ", "T")


def run(cls):
    end = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        engine = BacktestEngine(strategy_class=cls, symbol="BTCUSD", lot_size=LOT_SIZE,
                                start_date=START_DATE, end_date=end, csv_path=CSV_PATH,
                                strategy_params=dict(PARAMS), slippage=5.0)
        result = engine.run()
    return result


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def summarize(name, trades):
    pts = 0.0
    n = 0
    sums = {}
    for t in trades:
        e, x = fnum(t.get("entry_price")), fnum(t.get("exit_price"))
        if e is None or x is None:
            continue
        n += 1
        pts += (x - e) if str(t.get("direction", "")).lower() == "long" else (e - x)
        for k, v in t.items():
            if any(w in k.lower() for w in ("pnl", "fee", "charge", "commission")):
                fv = fnum(v)
                if fv is not None:
                    sums[k] = sums.get(k, 0.0) + fv
    print(f"{name}: closed trades={n} | gross points (entry/exit prices, per unit)={pts:.2f}")
    for k, v in sums.items():
        print(f"    sum[{k}] = {v:.4f}")
    return pts


def main():
    if not os.path.exists(CSV_PATH):
        sys.exit(f"ABORT: {CSV_PATH} not found. Nothing was run.")
    res = {}
    for name, cls in (("ORIGINAL", RenkoSMIIOCrossV3Strategy),
                      ("INVERSE", RenkoSMIIOCrossV3InverseStrategy)):
        r = run(cls)
        trades = [t for t in r.get("trades", []) if "entry_datetime" in t]
        res[name] = trades
        print(f"{name}: result keys={list(r.keys())}")
        if trades:
            print(f"{name}: first trade keys={list(trades[0].keys())}")

    print("\n=== FULL PERIOD ===")
    summarize("ORIGINAL", res["ORIGINAL"])
    summarize("INVERSE ", res["INVERSE"])

    o = {norm(t["entry_datetime"]): t for t in res["ORIGINAL"]}
    i = {norm(t["entry_datetime"]): t for t in res["INVERSE"]}
    missing = [k for k in o if k not in i]
    extra = [k for k in i if k not in o]
    side_bad = [k for k in o if k in i and
                str(o[k].get("direction", "")).lower() == str(i[k].get("direction", "")).lower()]
    exit_bad = [k for k in o if k in i and
                norm(o[k].get("exit_datetime", "")) != norm(i[k].get("exit_datetime", ""))]
    print(f"\nMIRROR CHECK: orig={len(o)} inv={len(i)} missing_in_inv={len(missing)} "
          f"extra_in_inv={len(extra)} same_side={len(side_bad)} exit_time_diff={len(exit_bad)}")

    if CUTOFF:
        print(f"\n=== ENTRIES FROM {CUTOFF} ONWARD ===")
        summarize("ORIGINAL", [t for t in res["ORIGINAL"] if norm(t["entry_datetime"]) >= CUTOFF])
        summarize("INVERSE ", [t for t in res["INVERSE"] if norm(t["entry_datetime"]) >= CUTOFF])


main()
