import pandas as pd
import glob
import sys

print("Loading 1-min data...")
df1m = pd.read_csv("data/btc_1m_delta.csv")
df1m["dt"] = pd.to_datetime(df1m["Date"] + " " + df1m["Time"])
df1m = df1m.sort_values("dt").reset_index(drop=True)
df1m_idx = df1m.set_index("dt")

def analyze(trade_log_path, label):
    print(f"\n=== {label} ({trade_log_path}) ===")
    tl = pd.read_csv(trade_log_path)
    tl["entry_datetime"] = pd.to_datetime(tl["entry_datetime"])
    tl["exit_datetime"] = pd.to_datetime(tl["exit_datetime"])
    print(f"Total trades: {len(tl)}")

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

    print(f"MAE% stats: max={mae_s.max():.3f} p99={mae_s.quantile(0.99):.3f} p95={mae_s.quantile(0.95):.3f} mean={mae_s.mean():.3f}")
    print(f"Max 1-min move% stats: max={speed_s.max():.3f} p99={speed_s.quantile(0.99):.3f} p95={speed_s.quantile(0.95):.3f} mean={speed_s.mean():.3f}")

    print("\nSL width -> % of trades that would be stopped early (false positive rate):")
    for width in [0.75, 3, 5, 8, 10, 12, 15, 20]:
        pct_stopped = (mae_s >= width).mean() * 100
        n_stopped = (mae_s >= width).sum()
        print(f"  {width}%: {pct_stopped:.2f}% of trades stopped ({n_stopped}/{len(mae_s)})")

    print("\n1-min speed threshold -> % of trades that would trigger Tier1 filter:")
    for width in [1, 2, 3, 4, 5, 7, 10]:
        pct_trig = (speed_s >= width).mean() * 100
        print(f"  {width}%/min: {pct_trig:.2f}% of trades trigger")

if len(sys.argv) > 1:
    path = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else "S4V3 Candidate"
    analyze(path, label)
else:
    print("Usage: python3 tier01_replay_s4v3.py <trade_log_csv_path> <label>")
