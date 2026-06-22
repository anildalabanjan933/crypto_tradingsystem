# pattern_validation_v3.py
# Core pattern only — Rule 1, Rule 2, Rule 4.
# No proximity filter.
# Prints first 10 candidates for manual visual verification.

from data.data_loader import DataLoader
from data.data_aggregator import DataAggregator
from indicators.pnf import PnFChartBuilder

CSV_PATH         = 'data/btc_1m_delta.csv'
START_DATE       = '2025-06-11'
END_DATE         = '2026-06-11'
BOX_SIZE_PERCENT = 0.15
REVERSE_BOXES    = 3

loader  = DataLoader(CSV_PATH)
data_1m = loader.load_data()
loader.validate_format()
data_1m = loader.filter_by_date_range(START_DATE, END_DATE)
loader.validate_data_continuity()

agg     = DataAggregator(data_1m)
data_1h = agg.get_1h_data().copy()
data_1h.columns = data_1h.columns.str.lower()
if data_1h.index.tz is not None:
    data_1h.index = data_1h.index.tz_localize(None)

builder = PnFChartBuilder(box_size_percent=BOX_SIZE_PERCENT, reverse_boxes=REVERSE_BOXES)
cols    = builder.build_pnf_chart(data_1h)
print(f"Total PnF columns: {len(cols)}")
print()

def get_typed_cols(columns, up_to_idx, col_type):
    return [(i, columns[i]) for i in range(up_to_idx + 1)
            if columns[i]['type'] == col_type]

results = []

for idx in range(len(cols)):
    if cols[idx]['type'] != 'O':
        continue

    o_cols = get_typed_cols(cols, idx, 'O')
    x_cols = get_typed_cols(cols, idx, 'X')

    if len(o_cols) < 4 or len(x_cols) < 2:
        continue

    o2_idx,      o2      = o_cols[-1]
    o1_idx,      o1      = o_cols[-2]
    o_prev1_idx, o_prev1 = o_cols[-3]
    o_prev2_idx, o_prev2 = o_cols[-4]

    x_between_idx, x_between = x_cols[-1]
    x_before_idx,  x_before  = x_cols[-2]

    if not (o1_idx < x_between_idx < o2_idx):
        continue
    if not (x_before_idx < o1_idx):
        continue

    # Rule 1: ascending O bottoms
    rule1 = (o_prev1['end_level'] > o_prev2['end_level'] and
             o1['end_level']      > o_prev1['end_level'])

    # Rule 2: lower high X between O1 and O2
    rule2 = x_between['end_level'] < x_before['end_level']

    # Rule 4: O2 breaks below O1
    rule4 = o2['end_level'] < o1['end_level']

    if rule1 and rule2 and rule4:
        results.append({
            'col_idx'       : idx,
            'timestamp'     : cols[idx]['end_timestamp'],
            'o_prev2_idx'   : o_prev2_idx,
            'o_prev2_bot'   : o_prev2['end_level'],
            'o_prev1_idx'   : o_prev1_idx,
            'o_prev1_bot'   : o_prev1['end_level'],
            'o1_idx'        : o1_idx,
            'o1_bot'        : o1['end_level'],
            'x_before_idx'  : x_before_idx,
            'x_before_top'  : x_before['end_level'],
            'x_between_idx' : x_between_idx,
            'x_between_top' : x_between['end_level'],
            'o2_idx'        : o2_idx,
            'o2_bot'        : o2['end_level'],
        })

print(f"Total patterns passing Rule 1 + Rule 2 + Rule 4: {len(results)}")
print()
print("First 10 candidates — verify each one on TradingView PnF chart:")
print()
print(f"  {'#':>2}  {'col':>4}  {'date':<20}  {'O_p2(col)':>12}  {'O_p1(col)':>12}  {'O1(col)':>12}  {'Xbef(col)':>12}  {'Xbet(col)':>12}  {'O2(col)':>12}")
print("  " + "-" * 112)

for n, r in enumerate(results[:10], 1):
    print(
        f"  {n:>2}  {r['col_idx']:>4}  {str(r['timestamp']):<20}  "
        f"{r['o_prev2_bot']:>8.2f}({r['o_prev2_idx']:>3})  "
        f"{r['o_prev1_bot']:>8.2f}({r['o_prev1_idx']:>3})  "
        f"{r['o1_bot']:>8.2f}({r['o1_idx']:>3})  "
        f"{r['x_before_top']:>8.2f}({r['x_before_idx']:>3})  "
        f"{r['x_between_top']:>8.2f}({r['x_between_idx']:>3})  "
        f"{r['o2_bot']:>8.2f}({r['o2_idx']:>3})"
    )

print()
print("For each row, navigate to the date on TradingView and confirm:")
print("  1. O_prev2 -> O_prev1 -> O1 shows rising O bottoms (ascending pullback)")
print("  2. X_between top is lower than X_before top (lower high)")
print("  3. O2 breaks below O1 (breakdown confirmed)")
print("  4. Overall: does this look like your manual bearish pullback setup?")
