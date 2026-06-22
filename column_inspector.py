# column_inspector.py
# Prints the last 10 O columns and last 10 X columns up to a target column index.
# No strategy logic. No filters. No backtest.
# Purpose: reconstruct exact column structure for manual TradingView comparison.

from data.data_loader import DataLoader
from data.data_aggregator import DataAggregator
from indicators.pnf import PnFChartBuilder

CSV_PATH         = 'data/btc_1m_delta.csv'
START_DATE       = '2025-06-11'
END_DATE         = '2026-06-11'
BOX_SIZE_PERCENT = 0.15
REVERSE_BOXES    = 3

TARGET_COL = 32   # <-- change this to inspect any column

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
print(f"Total PnF columns : {len(cols)}")
print(f"Inspecting up to  : col {TARGET_COL}")
print()

# ── Collect all O and X columns up to TARGET_COL ──────────────────────────────
o_cols = [(i, cols[i]) for i in range(TARGET_COL + 1) if cols[i]['type'] == 'O']
x_cols = [(i, cols[i]) for i in range(TARGET_COL + 1) if cols[i]['type'] == 'X']

# ── Print last 10 O columns ───────────────────────────────────────────────────
print("=" * 75)
print(f"LAST 10 O COLUMNS (up to col {TARGET_COL})")
print("=" * 75)
print(f"  {'col_idx':>7}  {'top':>12}  {'bottom':>12}  {'timestamp'}")
print("-" * 75)
for idx, col in o_cols[-10:]:
    print(f"  {idx:>7}  {col['start_level']:>12.2f}  {col['end_level']:>12.2f}  {col['end_timestamp']}")

# ── Print last 10 X columns ───────────────────────────────────────────────────
print()
print("=" * 75)
print(f"LAST 10 X COLUMNS (up to col {TARGET_COL})")
print("=" * 75)
print(f"  {'col_idx':>7}  {'top':>12}  {'bottom':>12}  {'timestamp'}")
print("-" * 75)
for idx, col in x_cols[-10:]:
    print(f"  {idx:>7}  {col['end_level']:>12.2f}  {col['start_level']:>12.2f}  {col['end_timestamp']}")

# ── Print full sequence around target ─────────────────────────────────────────
start_display = max(0, TARGET_COL - 10)
print()
print("=" * 75)
print(f"FULL COLUMN SEQUENCE  col {start_display} to col {TARGET_COL}")
print("=" * 75)
print(f"  {'col_idx':>7}  {'type':>5}  {'top':>12}  {'bottom':>12}  {'timestamp'}")
print("-" * 75)
for i in range(start_display, TARGET_COL + 1):
    col = cols[i]
    if col['type'] == 'X':
        top    = col['end_level']
        bottom = col['start_level']
    else:
        top    = col['start_level']
        bottom = col['end_level']
    print(f"  {i:>7}  {col['type']:>5}  {top:>12.2f}  {bottom:>12.2f}  {col['end_timestamp']}")
