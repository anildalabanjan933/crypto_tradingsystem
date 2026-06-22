from data.data_loader import DataLoader
from data.data_aggregator import DataAggregator
from indicators.pnf import PnFChartBuilder
import pandas as pd

loader = DataLoader('data/btc_1m_delta.csv')
data_1m = loader.load_data()
data_1m = loader.filter_by_date_range('2025-06-11', '2026-06-11')
agg = DataAggregator(data_1m)
data_1h = agg.get_1h_data().copy()
data_1h.columns = data_1h.columns.str.lower()
if data_1h.index.tz is not None:
    data_1h.index = data_1h.index.tz_localize(None)

builder = PnFChartBuilder(box_size_percent=0.15, reverse_boxes=3)
cols = builder.build_pnf_chart(data_1h)

# Print ALL fields for cols 488-510 including start_level
print('--- TRADE 221 cols 488-510 (ALL FIELDS) ---')
for i in range(488, 511):
    c = cols[i]
    print(f"col{i:>4} {c['type']}  start={c['start_timestamp']}  end={c['end_timestamp']}  "
          f"start_level={c['start_level']:>12.2f}  end_level={c['end_level']:>12.2f}")

print()

# Also print ALL fields for Trade 357 cols 814-820
print('--- TRADE 357 cols 814-820 (ALL FIELDS) ---')
for i in range(814, 821):
    c = cols[i]
    print(f"col{i:>4} {c['type']}  start={c['start_timestamp']}  end={c['end_timestamp']}  "
          f"start_level={c['start_level']:>12.2f}  end_level={c['end_level']:>12.2f}")
