# pattern_validation_v4.py
# Pure standard PnF pattern validation.
# Entry  = current O bottom < previous O bottom (any amount)
# Exit   = current X top    > previous X top    (any amount)
# No other filters. No SMA. No ADX. No proximity. No ascending O.
# Prints first 20 Double Bottom entries and first 20 Double Top exits.
# Compare timestamps and levels against TradingView PnF chart manually.

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

# ── Double Bottom entries ──────────────────────────────────────────────────────
db_entries = []

for idx in range(len(cols)):
    if cols[idx]['type'] != 'O':
        continue
    o_cols = [(i, cols[i]) for i in range(idx + 1) if cols[i]['type'] == 'O']
    if len(o_cols) < 2:
        continue
    prev_o_idx, prev_o = o_cols[-2]
    curr_o_idx, curr_o = o_cols[-1]
    if curr_o['end_level'] < prev_o['end_level']:
        db_entries.append({
            'col_idx'      : idx,
            'timestamp'    : curr_o['end_timestamp'],
            'prev_o_idx'   : prev_o_idx,
            'prev_o_bot'   : prev_o['end_level'],
            'curr_o_bot'   : curr_o['end_level'],
            'diff'         : round(prev_o['end_level'] - curr_o['end_level'], 2),
        })

# ── Double Top exits ───────────────────────────────────────────────────────────
dt_exits = []

for idx in range(len(cols)):
    if cols[idx]['type'] != 'X':
        continue
    x_cols = [(i, cols[i]) for i in range(idx + 1) if cols[i]['type'] == 'X']
    if len(x_cols) < 2:
        continue
    prev_x_idx, prev_x = x_cols[-2]
    curr_x_idx, curr_x = x_cols[-1]
    if curr_x['end_level'] > prev_x['end_level']:
        dt_exits.append({
            'col_idx'      : idx,
            'timestamp'    : curr_x['end_timestamp'],
            'prev_x_idx'   : prev_x_idx,
            'prev_x_top'   : prev_x['end_level'],
            'curr_x_top'   : curr_x['end_level'],
            'diff'         : round(curr_x['end_level'] - prev_x['end_level'], 2),
        })

# ── Print Double Bottom entries ────────────────────────────────────────────────
print(f"Total Double Bottom entries detected : {len(db_entries)}")
print(f"Total Double Top    exits   detected : {len(dt_exits)}")
print()

print("=" * 75)
print("DOUBLE BOTTOM ENTRIES — first 20")
print("Entry fires when current O bottom < previous O bottom")
print("=" * 75)
print(f"  {'#':>2}  {'col':>4}  {'timestamp':<20}  {'prev_O_bot':>12}  {'curr_O_bot':>12}  {'diff':>8}")
print("  " + "-" * 68)
for n, e in enumerate(db_entries[:20], 1):
    print(
        f"  {n:>2}  {e['col_idx']:>4}  {str(e['timestamp']):<20}  "
        f"{e['prev_o_bot']:>12.2f}  {e['curr_o_bot']:>12.2f}  {e['diff']:>8.2f}"
    )

print()
print("=" * 75)
print("DOUBLE TOP EXITS — first 20")
print("Exit fires when current X top > previous X top")
print("=" * 75)
print(f"  {'#':>2}  {'col':>4}  {'timestamp':<20}  {'prev_X_top':>12}  {'curr_X_top':>12}  {'diff':>8}")
print("  " + "-" * 68)
for n, e in enumerate(dt_exits[:20], 1):
    print(
        f"  {n:>2}  {e['col_idx']:>4}  {str(e['timestamp']):<20}  "
        f"{e['prev_x_top']:>12.2f}  {e['curr_x_top']:>12.2f}  {e['diff']:>8.2f}"
    )

print()
print("Next step: compare each timestamp and level against TradingView PnF chart.")
print("Confirm YES or NO for each entry and exit before any filters are added.")
