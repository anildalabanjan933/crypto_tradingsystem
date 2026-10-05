import pandas as pd

orig = pd.read_csv("output/s4_ORIGINAL_SAFE.csv")
cap800 = pd.read_csv("output/s4_800CAP_SAFE.csv")

def metrics(df, label):
    total_pnl = df["net_pnl"].sum()
    trade_count = len(df)
    wins = df[df["net_pnl"] > 0]["net_pnl"]
    losses = df[df["net_pnl"] < 0]["net_pnl"]
    profit_factor = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf")
    max_dd = (df["cumulative_pnl"].cummax() - df["cumulative_pnl"]).max()
    max_win = df["net_pnl"].max()
    max_loss = df["net_pnl"].min()

    print(f"\n=== {label} ===")
    print(f"Trade count     : {trade_count}")
    print(f"Total Net PnL   : {total_pnl:.2f}")
    print(f"Profit Factor   : {profit_factor:.2f}")
    print(f"Max Drawdown    : {max_dd:.2f}")
    print(f"Max Single Win  : {max_win:.2f}")
    print(f"Max Single Loss : {max_loss:.2f}")

    df["month"] = pd.to_datetime(df["entry_datetime"]).dt.to_period("M")
    monthly = df.groupby("month")["net_pnl"].sum()
    print(f"\nMonth-wise Net PnL ({label}):")
    print(monthly.to_string())

metrics(orig, "ORIGINAL (Full History)")
metrics(cap800, "800-CAP TEST")
