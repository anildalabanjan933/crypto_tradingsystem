import pandas as pd

v2 = pd.read_csv('output/trade_log_PnFBearishVariant4BV2_BTCUSD_20260611_012441.csv')
wins = v2[v2['net_pnl'] > 0]
losses = v2[v2['net_pnl'] <= 0]
gross_win = wins['net_pnl_inr'].sum()
gross_loss = abs(losses['net_pnl_inr'].sum())
pf = gross_win / gross_loss if gross_loss > 0 else float('inf')
net = v2['net_pnl_inr'].sum()
avg = v2['net_pnl_inr'].mean()
wr = len(wins)/len(v2)*100
exp = (len(wins)/len(v2) * wins['net_pnl_inr'].mean()) - (len(losses)/len(v2) * abs(losses['net_pnl_inr'].mean()))
print('V2 Total trades  :', len(v2))
print('V2 Winners       :', len(wins))
print('V2 Losers        :', len(losses))
print('V2 Win rate      :', round(wr, 1))
print('V2 Profit factor :', round(pf, 2))
print('V2 Net PnL INR   :', round(net, 0))
print('V2 Avg trade INR :', round(avg, 0))
print('V2 Expectancy    :', round(exp, 0))
ts = 'entry_datetime'
print('W2 2025-11-13    :', any(str(t).startswith('2025-11-13') for t in v2[ts]))
print('L2 2025-11-07    :', any(str(t).startswith('2025-11-07') for t in v2[ts]))
print('L3 2026-01-21    :', any(str(t).startswith('2026-01-21') for t in v2[ts]))
print('L1 2025-10-30    :', any(str(t).startswith('2025-10-30') for t in v2[ts]))
