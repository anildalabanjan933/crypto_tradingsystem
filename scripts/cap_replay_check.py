#!/usr/bin/env python3
"""
READ-ONLY. Does a trailing-N-bar window fire the same signal as full history
at each real TF boundary?  Writes nothing, touches no live file.

Run (from repo root):
  .venv/bin/python3 scripts/cap_replay_check.py --bot s4   --days 30 --caps 800,1600,3200
  .venv/bin/python3 scripts/cap_replay_check.py --bot s4v2 --days 30 --caps 800,1600,3200
  .venv/bin/python3 scripts/cap_replay_check.py --bot s4v3 --days 30 --caps 800,1600,3200
"""
import sys, os, io, time, argparse, warnings, contextlib
sys.path.insert(0, os.getcwd())
import pandas as pd
warnings.filterwarnings("ignore")
from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
from strategies.backtest.renko_smiio_supertrend_v2_strategy import RenkoSMIIOSupertrendV2Strategy
from strategies.backtest.renko_smiio_cross_v3_strategy import RenkoSMIIOCrossV3Strategy

LOT = 100
CFG = {
    "s4": (RenkoSMIIOSupertrendStrategy,
           dict(renko_box_pct=0.001, renko_timeframe="2h", st_atr_length=5, st_factor=2.0,
                smiio_shortlen=10, smiio_longlen=10, smiio_siglen=3), 120),
    "s4v2": (RenkoSMIIOSupertrendV2Strategy,
             dict(renko_box_pct=0.001, renko_timeframe="30m", st_atr_length=5, st_factor=1.5,
                  smiio_shortlen=10, smiio_longlen=20, smiio_siglen=3), 30),
    "s4v3": (RenkoSMIIOCrossV3Strategy,
             dict(renko_box_pct=0.001, renko_timeframe="4h",
                  smiio_shortlen=5, smiio_longlen=10, smiio_siglen=3), None),
}

def resample_to_tf(df_1m, tf):
    # identical to renko_state_engine.resample_to_tf
    rule = tf.replace("H", "h").replace("T", "min").replace("m", "min")
    df = df_1m.copy().set_index("timestamp")
    df_tf = df.resample(rule).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
    df_tf.columns = ["open", "high", "low", "close"]
    return df_tf.dropna().reset_index()

def run(df_tf, cls, params, ref):
    d = df_tf.set_index("timestamp")
    kw = dict(params)
    if ref is not None:
        kw["reference_price"] = ref
    strat = cls({params["renko_timeframe"]: d}, LOT, **kw)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with contextlib.redirect_stdout(io.StringIO()):
            return strat.generate_signals() or []

def by_ts(sigs):
    out = {}
    for s in sigs:
        ts = pd.Timestamp(s.get("timestamp"))
        out.setdefault(ts, set()).add((s.get("signal_type"), s.get("direction")))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", choices=list(CFG), required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--caps", default="800,1600,3200")
    a = ap.parse_args()
    cls, params, tfm = CFG[a.bot]
    tf = params["renko_timeframe"]

    df = pd.read_csv("data/btc_1m_delta.csv")
    df["timestamp"] = pd.to_datetime(df["Date"] + " " + df["Time"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    df_tf = resample_to_tf(df, tf).iloc[:-1].reset_index(drop=True)  # drop last (possibly partial) bar
    ref = float(df_tf["close"].iloc[0]) if tfm is not None else None
    print(f"[{a.bot}] bars={len(df_tf)} ref_price={ref} tf={tf}")

    t0 = time.time()
    full = by_ts(run(df_tf, cls, params, ref))
    print(f"[{a.bot}] full-history reference built in {time.time()-t0:.1f}s")

    # tfm here is being reused as minutes-per-bar for s4/s4v2; for s4v3 we stored None
    # so compute minutes-per-bar from tf string directly for n_eval calculation
    tf_minutes = {"30m": 30, "2h": 120, "4h": 240}.get(tf, 60)
    n_eval = int(a.days * 24 * 60 / tf_minutes)
    labels = list(df_tf["timestamp"].iloc[-n_eval:])  # bar-open label of each just-closed candle

    for cap in [int(c) for c in a.caps.split(",")]:
        mism, t0 = [], time.time()
        for L in labels:
            win = df_tf[df_tf["timestamp"] <= L].tail(cap)
            got = by_ts(run(win, cls, params, ref)).get(L, set())
            exp = full.get(L, set())
            if got != exp:
                mism.append((L, sorted(exp - got), sorted(got - exp)))
        print(f"\n[{a.bot}] cap={cap}: checked={len(labels)} mismatches={len(mism)} "
              f"({time.time()-t0:.0f}s)  [missing=in full not in capped, extra=in capped not in full]")
        for L, miss, extra in mism[:15]:
            print(f"   {L}  missing={miss}  extra={extra}")
        if len(mism) > 15:
            print(f"   ... {len(mism)-15} more")

if __name__ == "__main__":
    main()
