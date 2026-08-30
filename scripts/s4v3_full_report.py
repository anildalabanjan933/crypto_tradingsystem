import pandas as pd, io

top5_csv = """Rank,TF,Short,Long,Sig,PnL (INR),Trades,Win%,Sharpe,DD%,DD (Rs)
1,10m,5,10,3,19590544,15815,52.75,6.82,-0.16,19495
2,5m,5,10,3,19494769,24043,46.16,5.69,-0.25,52831
3,15m,5,10,3,18649952,12153,56.56,7.45,-0.18,15030
4,20m,5,10,3,18314555,9716,60.07,7.90,-0.12,14108
5,10m,5,20,3,17520980,15316,49.43,6.30,-0.18,21369
Daily,Daily,5,10,3,4529559,224,96.43,14.99,-0.02,2913
"""

yearly_csv = """Year,PnL (INR),PnL %,Return on Capital (3x DD)
2024,7176048.60,85.43,12270.02
2025,11079964.56,131.90,18945.16
2026 (partial),3990122.64,47.50,6822.54
"""

compare_csv = """Row,TF,ATR/Factor/SMIIO,PnL (INR),Trades,Win%,Sharpe,DD%,DD (Rs)
CURRENT LIVE S4,2h,atr5/f2.0/10-3,20370186,4459,74.81,10.42,-0.08,18593
CURRENT LIVE S4V2,30m,atr5/f1.5/10-3,26630802,13627,58.72,7.67,-0.18,20611
S4V3 #1,10m,N/A - 5/10/3,19590544,15815,52.75,6.82,-0.16,19495
S4V3 #2,5m,N/A - 5/10/3,19494769,24043,46.16,5.69,-0.25,52831
S4V3 #3,15m,N/A - 5/10/3,18649952,12153,56.56,7.45,-0.18,15030
S4V3 #4,20m,N/A - 5/10/3,18314555,9716,60.07,7.90,-0.12,14108
S4V3 #5,10m,N/A - 5/20/3,17520980,15316,49.43,6.30,-0.18,21369
S4V3 DAILY,Daily,N/A - 5/10/3,4529559,224,96.43,14.99,-0.02,2913
"""

df_top5 = pd.read_csv(io.StringIO(top5_csv))
df_yearly = pd.read_csv(io.StringIO(yearly_csv))
df_compare = pd.read_csv(io.StringIO(compare_csv))

# ---- CSV OUTPUT (all sections stacked with headers) ----
with open("output/s4v3_full_report.csv", "w") as f:
    f.write("S4V3 Optimization (RenkoSMIIOCrossV3Strategy) - TOP 5 + DAILY VARIANT\n")
    f.write("FILE: output/optimization_results_RenkoSMIIOCrossV3Strategy_BTCUSD_20260827_040950.csv\n")
    f.write("SETTINGS: Symbol=BTCUSD | Date Range=2024-01-10 to 2026-08-26 | Lot Size=100 | Slippage=$5.0/side | Charges=Included | Capital=Rs84,00,000\n")
    f.write("PARAMS: renko_timeframe, smiio_shortlen, smiio_longlen, smiio_siglen (no ATR/Factor in V3)\n\n")
    df_top5.to_csv(f, index=False)
    f.write("\nYEARLY BREAKDOWN (Best Combo #1: 10m/5/10/3)\n")
    df_yearly.to_csv(f, index=False)
    f.write("\nRISK/CAPITAL METRICS (Best Combo #1)\n")
    f.write("Recommended Capital,58484.42\n")
    f.write("Avg Monthly ROC %,1188.68\n")
    f.write("Best Month ROC %,2434.26\n")
    f.write("Return/Max DD Ratio,1004.91\n")
    f.write("Max DD Duration,N/A\n\n")
    f.write("CURRENT LIVE (S4 + S4V2) vs S4V3 CANDIDATES - COMPARE TABLE\n")
    df_compare.to_csv(f, index=False)

# ---- HTML OUTPUT ----
def rows_html(df, money_cols=(), pct_cols=(), int_cols=(), highlight_col=None, highlight_kw=None):
    out = ""
    for _, r in df.iterrows():
        hl = ""
        if highlight_col and highlight_kw and highlight_kw in str(r[highlight_col]):
            hl = "background-color:#e0f0ff;"
        out += "<tr style='" + hl + "'>"
        for c in df.columns:
            v = r[c]
            if c in money_cols:
                out += "<td>Rs" + format(v, ",.2f") + "</td>"
            elif c in pct_cols:
                out += "<td>" + format(v, ".2f") + "%</td>"
            elif c in int_cols:
                out += "<td>" + format(v, ",.0f") + "</td>"
            else:
                out += "<td>" + str(v) + "</td>"
        out += "</tr>\n"
    return out

html = """<!DOCTYPE html><html><head><title>S4V3 Full Report</title><style>
table{border-collapse:collapse;width:100%;font-family:Arial;font-size:13px;margin-bottom:30px;}
th,td{border:1px solid #999;padding:6px 8px;text-align:center;}
th{background-color:#2c3e50;color:white;}
tr:nth-child(even){background-color:#f2f2f2;}
body{font-family:Arial;}
pre{background:#f7f7f7;padding:10px;border:1px solid #ccc;font-size:12px;}
</style></head><body>

<h2>S4V3 Optimization (RenkoSMIIOCrossV3Strategy) - TOP 5 + DAILY VARIANT</h2>
<pre>FILE: output/optimization_results_RenkoSMIIOCrossV3Strategy_BTCUSD_20260827_040950.csv
SETTINGS: Symbol=BTCUSD | Date Range=2024-01-10 to 2026-08-26 | Lot Size=100 | Slippage=$5.0/side | Charges=Included | Capital=Rs84,00,000
PARAMS: renko_timeframe, smiio_shortlen, smiio_longlen, smiio_siglen (no ATR/Factor in V3)</pre>

<table><tr><th>Rank</th><th>TF</th><th>Short</th><th>Long</th><th>Sig</th><th>PnL (INR)</th><th>Trades</th><th>Win%</th><th>Sharpe</th><th>DD%</th><th>DD (Rs)</th></tr>
""" + rows_html(df_top5, money_cols=["PnL (INR)","DD (Rs)"], pct_cols=["Win%","DD%"], int_cols=["Trades"], highlight_col="Rank", highlight_kw="Daily") + """</table>

<p><i>NOTE: Figures already include $5/side slippage + full charges. No existing live S4V3 baseline exists.
#4 (20m) has best win rate/Sharpe/DD among 5m-20m range. Daily variant has fewest trades and lowest DD but far lower PnL - reference only.
#1 (10m) has highest PnL but 15,815 trades = higher slippage exposure in live.</i></p>

<h3>Yearly Breakdown (Best Combo #1: 10m/5/10/3)</h3>
<table><tr><th>Year</th><th>PnL (INR)</th><th>PnL %</th><th>Return on Capital (3x DD)</th></tr>
""" + rows_html(df_yearly, money_cols=["PnL (INR)"], pct_cols=["PnL %","Return on Capital (3x DD)"]) + """</table>

<h3>Risk/Capital Metrics (Best Combo #1)</h3>
<table><tr><th>Metric</th><th>Value</th></tr>
<tr><td>Recommended Capital</td><td>Rs58,484.42</td></tr>
<tr><td>Avg Monthly ROC</td><td>1188.68%</td></tr>
<tr><td>Best Month ROC</td><td>2434.26%</td></tr>
<tr><td>Return/Max DD Ratio</td><td>1,004.91</td></tr>
<tr><td>Max DD Duration</td><td>N/A</td></tr>
</table>

<h3>Current Live (S4 + S4V2) vs S4V3 Candidates - Compare Table</h3>
<table><tr><th>Row</th><th>TF</th><th>ATR/Factor/SMIIO</th><th>PnL (INR)</th><th>Trades</th><th>Win%</th><th>Sharpe</th><th>DD%</th><th>DD (Rs)</th></tr>
""" + rows_html(df_compare, money_cols=["PnL (INR)","DD (Rs)"], pct_cols=["Win%","DD%"], int_cols=["Trades"], highlight_col="Row", highlight_kw="CURRENT LIVE") + """</table>

</body></html>
"""

open("output/s4v3_full_report.html", "w").write(html)
print("DONE")
