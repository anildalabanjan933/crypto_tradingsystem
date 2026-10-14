#!/usr/bin/env python3
"""
ISOLATED SPEED TEST - measures data-processing delay only
Does NOT touch live engine, does NOT place orders, does NOT modify any live files
Simulates one websocket candle arrival and times: append -> resample -> strategy signal check
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import warnings, io, contextlib

from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy

def resample_to_tf(df_1m, tf):
    if df_1m is None or df_1m.empty: return None
    d = df_1m.copy()
    d = d.set_index("timestamp")
    rule_map = {"30m":"30min","1h":"1h","2h":"2h"}
    rule = rule_map.get(tf,"2h")
    o = d["Open"].resample(rule).first()
    h = d["High"].resample(rule).max()
    l = d["Low"].resample(rule).min()
    c = d["Close"].resample(rule).last()
    v = d["Volume"].resample(rule).sum()
    out = pd.DataFrame({"open":o,"high":h,"low":l,"close":c,"volume":v}).dropna().reset_index()
    return out

print("="*60)
print("ISOLATED SPEED TEST - data processing delay only")
print("Loading last 500 rows of real data (read-only, no live impact)...")
print("="*60)

t_load_start = time.time()
with open("data/btc_1m_delta.csv","rb") as f:
    f.seek(0,2); fsize=f.tell()
    f.seek(max(0,fsize-60000),0)
    tail = f.read().decode("utf-8",errors="ignore")
lines = [l for l in tail.split("\n") if l.strip() and not l.startswith("Date")]
rows=[]
for l in lines:
    p=l.split(",")
    if len(p)>=7:
        rows.append({"Date":p[0],"Time":p[1],"Open":float(p[2]),"High":float(p[3]),"Low":float(p[4]),"Close":float(p[5]),"Volume":float(p[6])})
df = pd.DataFrame(rows)
df["timestamp"] = pd.to_datetime(df["Date"]+" "+df["Time"])
t_load_end = time.time()
print(f"Data load time: {t_load_end-t_load_start:.4f} sec ({len(df)} rows)")

# Simulate new websocket candle arrival (fake next-minute candle appended in-memory)
t_sim_start = time.time()
last_row = df.iloc[-1]
new_ts = last_row["timestamp"] + pd.Timedelta(minutes=1)
new_row = pd.DataFrame([{
    "Date": new_ts.strftime("%Y-%m-%d"),
    "Time": new_ts.strftime("%H:%M:%S"),
    "Open": last_row["Close"], "High": last_row["Close"],
    "Low": last_row["Close"], "Close": last_row["Close"],
    "Volume": 1.0, "timestamp": new_ts
}])
df_updated = pd.concat([df, new_row], ignore_index=True)
t_append_end = time.time()
print(f"In-memory append time: {t_append_end-t_sim_start:.4f} sec")

# Resample to 2h timeframe (S4) - same as check_and_fire does
t_resample_start = time.time()
df_tf = resample_to_tf(df_updated, "2h")
t_resample_end = time.time()
print(f"Resample to 2h time: {t_resample_end-t_resample_start:.4f} sec ({len(df_tf)} candles)")

# Run strategy signal generation (same call as check_and_fire, S4 strategy)
t_strategy_start = time.time()
df_tf_indexed = df_tf.set_index("timestamp")
data_dict = {"2h": df_tf_indexed}
try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with contextlib.redirect_stdout(io.StringIO()):
            strategy = RenkoSMIIOSupertrendStrategy(data_dict, 100, renko_box_pct=0.001, renko_timeframe="2h",
                                                       st_atr_length=5, st_factor=2.0, smiio_shortlen=10,
                                                       smiio_longlen=10, smiio_siglen=3,
                                                       reference_price=float(df_tf_indexed["close"].iloc[0]))
            signals = strategy.generate_signals()
except Exception as e:
    signals = None
    print(f"Strategy error (may need more data): {e}")
t_strategy_end = time.time()
print(f"Strategy signal check time: {t_strategy_end-t_strategy_start:.4f} sec")

t_total = t_strategy_end - t_sim_start
print("="*60)
print(f"TOTAL DATA-PROCESSING DELAY (candle arrival -> signal ready): {t_total:.4f} sec")
print("="*60)
print("NOTE: This does NOT include actual order placement time (Delta Exchange API call),")
print("      which typically adds 2-4 sec separately based on past observed logs.")
