import sys, json, os, warnings
sys.path.insert(0, ".")
import pandas as pd
from strategies.backtest.renko_smiio_cross_v3_strategy import RenkoSMIIOCrossV3Strategy as S
from engine.telegram_alert import send_alert

BASE = "logs/s4v3_phase_canary.json"
df = pd.read_csv("data/btc_1m_delta.csv")
first_row = f"{df.iloc[0]['Date']} {df.iloc[0]['Time']} {df.iloc[0]['Close']}"
df["timestamp"] = pd.to_datetime(df["Date"] + " " + df["Time"], format="mixed")
df = df.set_index("timestamp"); df.columns = [c.lower() for c in df.columns]
d4 = df.resample("4h").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
d4.index.name = "timestamp"
ref = float(open("logs/box_ref_price_s4v3.txt").read().strip())
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    sigs = S({"4h": d4}, 100, renko_box_pct=0.001, renko_timeframe="4h",
             smiio_shortlen=5, smiio_longlen=10, smiio_siglen=3, reference_price=ref).generate_signals()
first_dir = next((s["direction"] for s in sigs if s["signal_type"] == "ENTRY"), None)
cur = {"first_row": first_row, "first_entry_dir": first_dir, "ref": ref}

if not os.path.exists(BASE):
    json.dump(cur, open(BASE, "w")); print("BASELINE SAVED", cur)
elif json.load(open(BASE)) != cur:
    msg = f"CTS S4V3 PHASE CANARY DRIFT: baseline={json.load(open(BASE))} now={cur}"
    print(msg); send_alert(msg); sys.exit(1)
else:
    print("OK", cur)
