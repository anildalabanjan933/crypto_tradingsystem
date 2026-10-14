import pandas as pd, io
csv_data = """Row,TF,ATR/Factor/SMIIO,PnL (INR),Trades,Win%,Sharpe,DD%,DD (Rs)
CURRENT LIVE S4,2h,atr5/f2.0/10-3,20370186,4459,74.81,10.42,-0.08,18593
CURRENT LIVE S4V2,30m,atr5/f1.5/10-3,26630802,13627,58.72,7.67,-0.18,20611
S4V3 #1,10m,N/A - 5/10/3,19590544,15815,52.75,6.82,-0.16,19495
S4V3 #2,5m,N/A - 5/10/3,19494769,24043,46.16,5.69,-0.25,52831
S4V3 #3,15m,N/A - 5/10/3,18649952,12153,56.56,7.45,-0.18,15030
S4V3 #4,20m,N/A - 5/10/3,18314555,9716,60.07,7.90,-0.12,14108
S4V3 #5,10m,N/A - 5/20/3,17520980,15316,49.43,6.30,-0.18,21369
S4V3 DAILY,Daily,N/A - 5/10/3,4529559,224,96.43,14.99,-0.02,2913
"""
df = pd.read_csv(io.StringIO(csv_data))
df.to_csv("output/s4v3_comparison_table.csv", index=False)
rows_html = ""
for _, r in df.iterrows():
    hl = "background-color:#e0f0ff;" if "CURRENT LIVE" in r["Row"] else ""
    rows_html += "<tr style='" + hl + "'><td>" + str(r["Row"]) + "</td><td>" + str(r["TF"]) + "</td><td>" + str(r["ATR/Factor/SMIIO"]) + "</td><td>Rs" + format(r["PnL (INR)"], ",.0f") + "</td><td>" + format(r["Trades"], ",.0f") + "</td><td>" + format(r["Win%"], ".2f") + "%</td><td>" + format(r["Sharpe"], ".2f") + "</td><td>" + format(r["DD%"], ".2f") + "%</td><td>Rs" + format(r["DD (Rs)"], ",.0f") + "</td></tr>\n"
html = "<html><head><title>S4V3 Comparison</title><style>table{border-collapse:collapse;width:100%;font-family:Arial;font-size:13px;}th,td{border:1px solid #999;padding:6px 8px;text-align:center;}th{background-color:#2c3e50;color:white;}tr:nth-child(even){background-color:#f2f2f2;}</style></head><body>"
html += "<h2>S4 vs S4V2 vs S4V3 Candidates - Comparison Table</h2>"
html += "<table><tr><th>Row</th><th>TF</th><th>ATR/Factor/SMIIO</th><th>PnL (INR)</th><th>Trades</th><th>Win%</th><th>Sharpe</th><th>DD%</th><th>DD (Rs)</th></tr>"
html += rows_html + "</table></body></html>"
open("output/s4v3_comparison_report.html", "w").write(html)
print("DONE")
