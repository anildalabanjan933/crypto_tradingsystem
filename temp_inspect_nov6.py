# temp_inspect_nov6.py
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

# Print all columns between Nov 4 and Nov 7
print(f"{'idx':>5}  {'type':>4}  {'start':>12}  {'end':>12}  {'start_ts'}  ->  {'end_ts'}")
print("-" * 90)
for i, c in enumerate(cols):
    ts = str(c.get('end_timestamp', ''))
    if '2025-11-04' <= ts[:10] <= '2025-11-07':
        print(f"{i:>5}  {c['type']:>4}  {c.get('start_level',0):>12.2f}  {c.get('end_level',0):>12.2f}  {c.get('start_timestamp','')}  ->  {c.get('end_timestamp','')}")
