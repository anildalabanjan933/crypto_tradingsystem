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

# Replicate Double Bottom detection and print details for entries near Nov 12-16
for idx2 in range(2, len(cols)):
    c2 = cols[idx2]
    if c2['type'] != 'O':
        continue
    idx_x = idx2 - 1
    if cols[idx_x]['type'] != 'X':
        continue
    idx1 = idx2 - 2
    if cols[idx1]['type'] != 'O':
        continue
    c1 = cols[idx1]
    if abs(c1['end_level'] - c2['end_level']) > 0.0:
        continue
    if idx2 + 1 >= len(cols):
        continue

    if pd.Timestamp('2025-11-12') <= c2['end_timestamp'] <= pd.Timestamp('2025-11-16'):
        box_size = c2['end_level'] * 0.0015
        c_next = cols[idx2 + 1]
        print(f"O1=col{idx1} end_level={c1['end_level']} end_ts={c1['end_timestamp']}")
        print(f"X =col{idx_x} end_level={cols[idx_x]['end_level']} end_ts={cols[idx_x]['end_timestamp']}")
        print(f"O2=col{idx2} end_level={c2['end_level']} end_ts={c2['end_timestamp']}")
        print(f"  box_size={box_size:.2f}")
        print(f"  O1==O2 diff={abs(c1['end_level'] - c2['end_level'])}")
        print(f"  col_after=col{idx2+1} type={c_next['type']} start={c_next['start_timestamp']} end={c_next['end_timestamp']} end_level={c_next['end_level']}")
        print()
