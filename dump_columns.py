# dump_columns.py
import pandas as pd
from data.data_loader import DataLoader
from data.data_aggregator import DataAggregator
from indicators.pnf import PnFChartBuilder

loader  = DataLoader('data/btc_1m_delta.csv')
data_1m = loader.load_data()
loader.validate_format()
data_1m = loader.filter_by_date_range('2025-06-11', '2026-06-11')
loader.validate_data_continuity()

agg     = DataAggregator(data_1m)
data_1h = agg.get_1h_data().copy()
data_1h.columns = data_1h.columns.str.lower()
if data_1h.index.tz is not None:
    data_1h.index = data_1h.index.tz_localize(None)

builder = PnFChartBuilder(box_size_percent=0.15, reverse_boxes=3)
cols    = builder.build_pnf_chart(data_1h)

print(f'Total columns: {len(cols)}')
print()
print('First 40 columns:')
for i, c in enumerate(cols[:40]):
    print(
        f'  [{i:3d}] {c["type"]}  '
        f'end={c["end_level"]:10.2f}  '
        f'high={c["high"]:10.2f}  '
        f'low={c["low"]:10.2f}  '
        f'end_ts={c["end_timestamp"]}'
    )
