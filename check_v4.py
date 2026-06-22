import pandas as pd

v4 = pd.read_csv('output/trade_log_PnFBearishVariant4BV4_BTCUSD_20260611_022825.csv')
wins = v4[v4['net_pnl'] > 0]
losses = v4[v4['net_pnl'] <= 0]
gross_win = wins['net_pnl_inr'].sum()
gross_loss = abs(losses['net_pnl_inr'].sum())
pf = gross_win / gross_loss if gross_loss > 0 else float('inf')
net = v4['net_pnl_inr'].sum()
avg = v4['net_pnl_inr'].mean()
wr = len(wins)/len(v4)*100
exp = (len(wins)/len(v4) * wins['net_pnl_inr'].mean()) - (len(losses)/len(v4) * abs(losses['net_pnl_inr'].mean()))
print('V4 Total trades  :', len(v4))
print('V4 Winners       :', len(wins))
print('V4 Losers        :', len(losses))
print('V4 Win rate      :', round(wr, 1))
print('V4 Profit factor :', round(pf, 2))
print('V4 Net PnL INR   :', round(net, 0))
print('V4 Avg trade INR :', round(avg, 0))
print('V4 Expectancy    :', round(exp, 0))
ts = 'entry_datetime'
print('W2 2025-11-13    :', any(str(t).startswith('2025-11-13') for t in v4[ts]))
print('L1 2025-10-30    :', any(str(t).startswith('2025-10-30') for t in v4[ts]))
print('L2 2025-11-07    :', any(str(t).startswith('2025-11-07') for t in v4[ts]))
print('L3 2026-01-21    :', any(str(t).startswith('2026-01-21') for t in v4[ts]))
print()
print('--- First 10 entries ---')
entries = v4[['entry_datetime','entry_price','exit_datetime','exit_price','exit_type','net_pnl_inr']].head(10)
print(entries.to_string(index=False))
