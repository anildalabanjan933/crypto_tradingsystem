import pandas as pd
import numpy as np

print("Loading 1-min data...")
df = pd.read_csv("data/btc_1m_delta.csv")
df['dt'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])
df = df.sort_values('dt').reset_index(drop=True)
df['month'] = df['dt'].dt.strftime('%Y-%m')

# 1-min speed = % move within that single candle (High-Low)/Open
df['move_1m'] = (df['High'] - df['Low'])
df['speed_1m_pct'] = (df['High'] - df['Low']) / df['Open'] * 100

# Resample to 2h and 30m for S4/S4V2 candle-level max move
df_idx = df.set_index('dt')
agg = {'Open':'first','High':'max','Low':'min','Close':'last'}
r2h = df_idx.resample('2h').agg(agg).dropna()
r2h['move'] = r2h['High'] - r2h['Low']
r2h['speed_pct'] = r2h['move'] / r2h['Open'] * 100
r2h['month'] = r2h.index.strftime('%Y-%m')

r30 = df_idx.resample('30min').agg(agg).dropna()
r30['move'] = r30['High'] - r30['Low']
r30['speed_pct'] = r30['move'] / r30['Open'] * 100
r30['month'] = r30.index.strftime('%Y-%m')

# Trade counts from BT csv
def load_trades(path):
    t = pd.read_csv(path)
    tcol = 'entry_datetime' if 'entry_datetime' in t.columns else t.columns[0]
    t['dt'] = pd.to_datetime(t[tcol], errors='coerce')
    t['month'] = t['dt'].dt.strftime('%Y-%m')
    return t.groupby('month').size()

import glob
s4_file = sorted(glob.glob("output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv"))[-1]
s4v2_file = sorted(glob.glob("output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv"))[-1]
print(f"Using S4 file: {s4_file}")
print(f"Using S4V2 file: {s4v2_file}")
s4_trades = load_trades(s4_file)
s4v2_trades = load_trades(s4v2_file)

def load_pnl(path):
    t = pd.read_csv(path)
    tcol = 'entry_datetime' if 'entry_datetime' in t.columns else t.columns[0]
    t['dt'] = pd.to_datetime(t[tcol], errors='coerce')
    t['month'] = t['dt'].dt.strftime('%Y-%m')
    return t.groupby('month')['net_pnl_inr'].sum()

s4_pnl = load_pnl(s4_file)
s4v2_pnl = load_pnl(s4v2_file)

months = sorted(df['month'].unique())
rows = []
for m in months:
    md = df[df['month']==m]
    m2h = r2h[r2h['month']==m]
    m30 = r30[r30['month']==m]

    max_1m_move = md['move_1m'].max()
    max_1m_speed = md['speed_1m_pct'].max()
    s4_move = m2h['move'].max() if len(m2h) else np.nan
    s4_speed = m2h['speed_pct'].max() if len(m2h) else np.nan
    s4v2_move = m30['move'].max() if len(m30) else np.nan
    s4v2_speed = m30['speed_pct'].max() if len(m30) else np.nan

    tier0_hits = (md['speed_1m_pct'] >= 10).sum()  # cumulative within candle unlikely, proxy count
    tier1_hits = (md['speed_1m_pct'] >= 5).sum()
    # Tier2 proxy: at 4x leverage, ~25% move to liquidation, 7% distance ~ 18% move threshold
    tier2_hits = (md['speed_1m_pct'] >= 18).sum()
    entry_band_hits = (md['move_1m'] >= 250).sum()
    exit_band_hits = (md['move_1m'] >= 150).sum()

    # Realistic INR impact per protection level - 100 lots BTC = 0.1 BTC, USD/INR = 88
    tier0_rows = md[md['speed_1m_pct'] >= 10]
    tier0_loss_inr = (tier0_rows['move_1m'] * 0.1).sum() * 88

    tier1_rows = md[md['speed_1m_pct'] >= 5]
    tier1_loss_inr = (tier1_rows['move_1m'] * 0.1).sum() * 88

    tier2_rows = md[md['speed_1m_pct'] >= 18]
    tier2_loss_inr = (tier2_rows['move_1m'] * 0.1).sum() * 88

    entry_band_rows = md[md['move_1m'] >= 250]
    entry_band_notional_inr = (entry_band_rows['move_1m'] * 0.1).sum() * 88

    exit_band_rows = md[md['move_1m'] >= 150]
    exit_band_notional_inr = (exit_band_rows['move_1m'] * 0.1).sum() * 88

    if tier0_hits > 0 or tier2_hits > 0:
        verdict = "REQUIRED CHANGE - Tier0/Tier2 fired, review threshold"
    elif tier1_hits > 0:
        verdict = "NO CHANGE - Tier1 fired (genuine volatility event, backstop working)"
    else:
        verdict = "NO CHANGE - no triggers this month"

    month_pnl_inr = float(s4_pnl.get(m, 0)) + float(s4v2_pnl.get(m, 0))

    rows.append({
        'Month': m,
        'S4 Trades': int(s4_trades.get(m,0)),
        'S4 (2h) Max Move': f"{s4_move:.0f}" if pd.notna(s4_move) else "-",
        'S4 (2h) Max Speed': f"{s4_speed:.2f}%" if pd.notna(s4_speed) else "-",
        'S4V2 Trades': int(s4v2_trades.get(m,0)),
        'S4V2 (30m) Max Move': f"{s4v2_move:.0f}" if pd.notna(s4v2_move) else "-",
        'S4V2 (30m) Max Speed': f"{s4v2_speed:.2f}%" if pd.notna(s4v2_speed) else "-",
        'Max Price Move (1min)': f"{max_1m_move:.0f}",
        'Max Speed (%/min)': f"{max_1m_speed:.2f}%",
        'Tier 0 Hit (10%)': int(tier0_hits),
        'Tier 1 Hit (5%/min)': int(tier1_hits),
        'Tier 2 Hit (~18% est)': int(tier2_hits),
        'Entry Band Hit ($250)': int(entry_band_hits),
        'Exit Band Hit ($150)': int(exit_band_hits),
        'Monthly Net PnL (INR)': f"{month_pnl_inr:,.0f}",
        'Verdict': verdict,
        'Tier0 Realistic Loss (INR)': f"{tier0_loss_inr:,.0f}",
        'Tier1 Realistic Loss (INR)': f"{tier1_loss_inr:,.0f}",
        'Tier2 Realistic Loss (INR)': f"{tier2_loss_inr:,.0f}",
        'Entry Band Realistic Loss (INR)': f"{entry_band_notional_inr:,.0f}",
        'Exit Band Realistic Loss (INR)': f"{exit_band_notional_inr:,.0f}",
    })

res = pd.DataFrame(rows)
res.to_csv("output/sl_monthly_analysis.csv", index=False)

html_rows = ""
for _, r in res.iterrows():
    html_rows += "<tr>" + "".join(f"<td>{v}</td>" for v in r) + "</tr>\n"

html = f"""<!DOCTYPE html>
<html><head><title>SL Protection Monthly Check</title>
<style>
table {{ border-collapse: collapse; width: 100%; font-family: Arial; font-size: 12px; }}
th, td {{ border: 1px solid #999; padding: 5px 6px; text-align: center; }}
th {{ background-color: #2c3e50; color: white; }}
tr:nth-child(even) {{ background-color: #f2f2f2; }}
</style></head><body>
<h2>SL Protection Monthly Check Table (Jan-2024 to Aug-2026)</h2>
<p><i>Tier 2 is an estimated proxy (~18% move at 4x leverage = ~7% distance to liquidation), not exact position-level backtest.</i></p>
<table>
<tr>{"".join(f"<th>{c}</th>" for c in res.columns)}</tr>
{html_rows}
</table>
</body></html>"""

with open("output/sl_monthly_analysis.html","w") as f:
    f.write(html)

print("DONE - saved output/sl_monthly_analysis.csv + .html")
print(res.to_string(index=False))
