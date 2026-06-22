"""
Analyze Higher High and Lower Low for all 126 trades.
No strategy changes. Statistics only.
"""

import pandas as pd
import glob
import sys
sys.path.insert(0, '.')

from indicators.pnf import PnFChartBuilder
from indicators.pnf_indicators import PnFIndicators

# ── Config ─────────────────────────────────────────────────────────
BOX_SIZE_PCT = 0.15
REVERSAL     = 3
CSV_PATH     = 'data/btc_1m_delta.csv'

# ── Find trade log ─────────────────────────────────────────────────
files = glob.glob('output/trade_log_*Test*.csv')
if not files:
    files = glob.glob('output/trade_log_*.csv')
TRADE_LOG = sorted(files)[-1]
print(f"Using trade log: {TRADE_LOG}")

# ── Load 1M data and aggregate to 1H ──────────────────────────────
print("Loading data...")
df = pd.read_csv(CSV_PATH)
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
df = df.set_index('timestamp').sort_index()
df = df[df.index >= '2025-06-10']
df_1h = df['close'].resample('1h').ohlc()
df_1h.columns = ['open', 'high', 'low', 'close']
df_1h = df_1h.dropna()
print(f"1H candles: {len(df_1h)}")

# ── Build PnF columns ──────────────────────────────────────────────
print("Building PnF columns...")
builder    = PnFChartBuilder(box_size_percent=BOX_SIZE_PCT, reverse_boxes=REVERSAL)
columns    = builder.build_pnf_chart(df_1h)
indicators = PnFIndicators(box_size_percent=BOX_SIZE_PCT)
print(f"Total PnF columns: {len(columns)}")

# ── Load trade log ─────────────────────────────────────────────────
trades = pd.read_csv(TRADE_LOG)
trades['entry_datetime'] = pd.to_datetime(trades['entry_datetime'])
print(f"Total trades: {len(trades)}\n")

# ── Find entry column index for a given timestamp ──────────────────
def find_entry_col(entry_ts, columns):
    # Exact match on end_timestamp
    for i, col in enumerate(columns):
        if col['type'] == 'O':
            if pd.Timestamp(col['end_timestamp']) == entry_ts:
                return i
    # Fallback: O column that contains entry_ts
    for i, col in enumerate(columns):
        if col['type'] == 'O':
            if pd.Timestamp(col['start_timestamp']) <= entry_ts <= pd.Timestamp(col['end_timestamp']):
                return i
    return None

# ── Analyze each trade ─────────────────────────────────────────────
results = []

for _, row in trades.iterrows():
    entry_ts    = row['entry_datetime']
    exit_type   = row['exit_type']
    trade_num   = row.get('trade_num', row.name + 1)
    pnl         = row.get('net_pnl_inr', row.get('pnl', 0))
    is_winner   = (exit_type == 'DOUBLE_TOP')

    col_idx = find_entry_col(entry_ts, columns)

    if col_idx is None:
        results.append({
            'trade_num'    : trade_num,
            'entry_ts'     : entry_ts,
            'is_winner'    : is_winner,
            'exit_type'    : exit_type,
            'pnl'          : pnl,
            'higher_high'  : None,
            'lower_low'    : None,
            'note'         : 'COLUMN_NOT_FOUND'
        })
        continue

    # Slice columns UP TO AND INCLUDING entry column
    cols_slice = columns[:col_idx + 1]

    hh = indicators.detect_higher_high(cols_slice)
    ll = indicators.detect_lower_low(cols_slice)

    results.append({
        'trade_num'   : trade_num,
        'entry_ts'    : entry_ts,
        'is_winner'   : is_winner,
        'exit_type'   : exit_type,
        'pnl'         : pnl,
        'higher_high' : hh,
        'lower_low'   : ll,
        'note'        : ''
    })

df_res = pd.DataFrame(results)

# ── Print per-trade detail ─────────────────────────────────────────
print(f"{'Trade':>6}  {'Entry Timestamp':>22}  {'W/L':>4}  {'HH':>6}  {'LL':>6}  {'Exit Type':>22}  {'PnL':>10}")
print("-" * 90)
for _, r in df_res.iterrows():
    wl   = "WIN"  if r['is_winner'] else "LOSS"
    hh   = str(r['higher_high']) if r['higher_high'] is not None else "N/A"
    ll   = str(r['lower_low'])   if r['lower_low']   is not None else "N/A"
    note = f"  [{r['note']}]" if r['note'] else ""
    print(f"{int(r['trade_num']):>6}  {str(r['entry_ts']):>22}  {wl:>4}  {hh:>6}  {ll:>6}  {r['exit_type']:>22}  {r['pnl']:>10.2f}{note}")

# ── Summary statistics ─────────────────────────────────────────────
valid = df_res[df_res['note'] == '']
winners = valid[valid['is_winner'] == True]
losers  = valid[valid['is_winner'] == False]

print("\n" + "="*65)
print("SUMMARY STATISTICS")
print("="*65)
print(f"Total trades  : {len(valid)}")
print(f"Winners       : {len(winners)}")
print(f"Losers        : {len(losers)}")

print(f"\n--- HIGHER HIGH ---")
w_hh_t = len(winners[winners['higher_high'] == True])
w_hh_f = len(winners[winners['higher_high'] == False])
l_hh_t = len(losers[losers['higher_high'] == True])
l_hh_f = len(losers[losers['higher_high'] == False])
print(f"Winners  HH=True  : {w_hh_t}")
print(f"Winners  HH=False : {w_hh_f}")
print(f"Losers   HH=True  : {l_hh_t}")
print(f"Losers   HH=False : {l_hh_f}")

print(f"\n--- LOWER LOW ---")
w_ll_t = len(winners[winners['lower_low'] == True])
w_ll_f = len(winners[winners['lower_low'] == False])
l_ll_t = len(losers[losers['lower_low'] == True])
l_ll_f = len(losers[losers['lower_low'] == False])
print(f"Winners  LL=True  : {w_ll_t}")
print(f"Winners  LL=False : {w_ll_f}")
print(f"Losers   LL=True  : {l_ll_t}")
print(f"Losers   LL=False : {l_ll_f}")

print(f"\n--- IF HH=True FILTER APPLIED ---")
hh_pass = valid[valid['higher_high'] == True]
hh_w    = hh_pass[hh_pass['is_winner'] == True]
hh_l    = hh_pass[hh_pass['is_winner'] == False]
print(f"Trades passing HH filter : {len(hh_pass)}")
print(f"  Winners : {len(hh_w)}")
print(f"  Losers  : {len(hh_l)}")
if len(hh_pass) > 0:
    print(f"  Win rate: {100*len(hh_w)/len(hh_pass):.1f}%")

print(f"\n--- IF LL=True FILTER APPLIED ---")
ll_pass = valid[valid['lower_low'] == True]
ll_w    = ll_pass[ll_pass['is_winner'] == True]
ll_l    = ll_pass[ll_pass['is_winner'] == False]
print(f"Trades passing LL filter : {len(ll_pass)}")
print(f"  Winners : {len(ll_w)}")
print(f"  Losers  : {len(ll_l)}")
if len(ll_pass) > 0:
    print(f"  Win rate: {100*len(ll_w)/len(ll_pass):.1f}%")

print(f"\n--- IF HH=True AND LL=True BOTH REQUIRED ---")
both_pass = valid[(valid['higher_high'] == True) & (valid['lower_low'] == True)]
both_w    = both_pass[both_pass['is_winner'] == True]
both_l    = both_pass[both_pass['is_winner'] == False]
print(f"Trades passing BOTH filters : {len(both_pass)}")
print(f"  Winners : {len(both_w)}")
print(f"  Losers  : {len(both_l)}")
if len(both_pass) > 0:
    print(f"  Win rate: {100*len(both_w)/len(both_pass):.1f}%")

print("\nAnalysis complete.")
