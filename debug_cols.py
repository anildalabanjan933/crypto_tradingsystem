import sys
sys.path.insert(0, '.')

from data.data_loader import DataLoader
from data.data_aggregator import DataAggregator
from indicators.pnf import PnFChartBuilder

DATE_FROM = '2025-06-11'
DATE_TO   = '2026-06-11'

loader = DataLoader('data/btc_1m_delta.csv')
loader.load_data()
loader.filter_by_date_range(DATE_FROM, DATE_TO)
data_1m = loader.data

aggregator = DataAggregator(data_1m)
data_1h = aggregator.get_1h_data()

builder = PnFChartBuilder(box_size_percent=0.15, reverse_boxes=3)
cols = builder.build_pnf_chart(data_1h)

print(f"Total columns: {len(cols)}")

def get_box_size(level):
    return level * 0.0015

# Relax ALL rules — just find O-X-O triplets and print what we see
print("\n=== All O-X-O triplets (no filters) ===")
count = 0
for idx2 in range(2, len(cols)):
    o2  = cols[idx2]
    mid = cols[idx2 - 1]
    o1  = cols[idx2 - 2]

    if o2['type'] != 'O' or mid['type'] != 'X' or o1['type'] != 'O':
        continue

    o1_bottom = o1['end_level']
    o2_bottom = o2['end_level']
    box       = get_box_size(o1_bottom)
    diff      = abs(o1_bottom - o2_bottom)
    diff_boxes = diff / box

    support   = o1_bottom
    crosses   = o2['start_level'] > support and o2['end_level'] < support
    starts_above = o2['start_level'] > support
    ends_below   = o2['end_level'] < support

    expected_break = support - box
    break_diff     = o2['end_level'] - expected_break  # negative = went further

    count += 1
    print(f"col {idx2:4d} | O1_bot={o1_bottom:.1f} O2_bot={o2_bottom:.1f} "
          f"| diff={diff_boxes:.3f}boxes | starts_above={starts_above} ends_below={ends_below} "
          f"| crosses={crosses} | break_diff={break_diff:.1f} (expected={expected_break:.1f})")

print(f"\nTotal O-X-O triplets: {count}")
