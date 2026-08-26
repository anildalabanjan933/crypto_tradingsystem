import pandas as pd
import glob
from datetime import datetime, timedelta

CUTOFF = datetime(2026, 6, 25)

print("Loading 1-min data...")
df1m = pd.read_csv("data/btc_1m_delta.csv")
df1m["dt"] = pd.to_datetime(df1m["Date"] + " " + df1m["Time"])
df1m = df1m.sort_values("dt").reset_index(drop=True)
df1m_idx = df1m.set_index("dt")

def analyze(strategy_glob, label):
    files = sorted(glob.glob(strategy_glob))
    f = files[-1]
    print(f"\n=== {label} ({f}) ===")
    tl = pd.read_csv(f)
    tl["entry_datetime"] = pd.to_datetime(tl["entry_datetime"])
    tl["exit_datetime"] = pd.to_datetime(tl["exit_datetime"])
    tl = tl[tl["entry_datetime"] >= CUTOFF].reset_index(drop=True)
    print(f"Trades in last 2 months: {len(tl)}")

    mae_list = []
    speed_list = []
    for _, row in tl.iterrows():
        seg = df1m_idx.loc[row["entry_datetime"]:row["exit_datetime"]]
        if seg.empty:
            continue
        entry_p = row["entry_price"]
        if row["direction"] == "long":
            worst = seg["Low"].min()
            mae_pct = (entry_p - worst) / entry_p * 100
        else:
            worst = seg["High"].max()
            mae_pct = (worst - entry_p) / entry_p * 100
        mae_list.append(max(mae_pct, 0))

        px = seg["Close"].values
        if len(px) > 1:
            pct_moves = abs((px[1:] - px[:-1]) / px[:-1] * 100)
            speed_list.append(pct_moves.max())

    mae_s = pd.Series(mae_list)
    speed_s = pd.Series(speed_list)

    print(f"MAE%% stats: max={mae_s.max():.3f} p99={mae_s.quantile(0.99):.3f} p95={mae_s.quantile(0.95):.3f} mean={mae_s.mean():.3f}")
    print(f"Max 1-min move%% stats: max={speed_s.max():.3f} p99={speed_s.quantile(0.99):.3f} p95={speed_s.quantile(0.95):.3f} mean={speed_s.mean():.3f}")

    print("\nSL width -> %% of trades that would be stopped early (false positive rate):")
    for width in [0.75, 3, 5, 8, 10, 12, 15, 20]:
        pct_stopped = (mae_s >= width).mean() * 100
        print(f"  {width}%%: {pct_stopped:.1f}%% of trades stopped")

    print("\n1-min speed threshold -> %% of trades that would trigger Tier1 filter:")
    for width in [1, 2, 3, 4, 5, 7, 10]:
        pct_trig = (speed_s >= width).mean() * 100
        print(f"  {width}%%/min: {pct_trig:.1f}%% of trades trigger")

analyze("output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv", "S4")
analyze("output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv", "S4V2")
