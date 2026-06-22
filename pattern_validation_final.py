import sys
sys.path.insert(0, '.')

from data.data_loader import DataLoader
from data.data_aggregator import DataAggregator
from indicators.pnf import PnFChartBuilder

DATE_FROM = '2025-06-11'
DATE_TO   = '2026-06-11'

# ── Data pipeline ──────────────────────────────────────────────────────────────
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

# ── Double Bottom detection (Entry) ───────────────────────────────────────────
# Structure: O1 ... X ... O2
# Rules:
#   1. O-X-O column sequence
#   2. O2 crosses through O1's bottom: O2 start > O1 bottom AND O2 end < O1 bottom
#   3. O2 end <= O1 bottom - 1 box (breaks by at least 1 full box)
#   4. Timestamp = cols[idx2+4]['end_timestamp']

entry_signals = []

for idx2 in range(2, len(cols) - 4):
    o2  = cols[idx2]
    mid = cols[idx2 - 1]
    o1  = cols[idx2 - 2]

    if o2['type'] != 'O' or mid['type'] != 'X' or o1['type'] != 'O':
        continue

    o1_bottom = o1['end_level']
    box       = get_box_size(o1_bottom)

    # Rule 2: O2 crosses through O1's bottom
    if not (o2['start_level'] > o1_bottom and o2['end_level'] < o1_bottom):
        continue

    # Rule 3: O2 breaks at least 1 full box below O1 bottom
    if o2['end_level'] > o1_bottom - box:
        continue

    entry_ts    = cols[idx2 + 4]['end_timestamp']
    entry_price = o2['end_level']

    entry_signals.append({
        'idx2'       : idx2,
        'entry_ts'   : entry_ts,
        'entry_price': entry_price,
        'o1_bottom'  : o1_bottom,
    })

# ── Double Top detection (Exit) ────────────────────────────────────────────────
# Structure: X1 ... O ... X2
# Rules:
#   1. X-O-X column sequence
#   2. X2 crosses through X1's top: X2 start < X1 top AND X2 end > X1 top
#   3. X2 end >= X1 top + 1 box (breaks by at least 1 full box)
#   4. Timestamp = cols[idx2+4]['end_timestamp']

exit_signals = []

for idx2 in range(2, len(cols) - 4):
    x2  = cols[idx2]
    mid = cols[idx2 - 1]
    x1  = cols[idx2 - 2]

    if x2['type'] != 'X' or mid['type'] != 'O' or x1['type'] != 'X':
        continue

    x1_top = x1['end_level']
    box    = get_box_size(x1_top)

    # Rule 2: X2 crosses through X1's top
    if not (x2['start_level'] < x1_top and x2['end_level'] > x1_top):
        continue

    # Rule 3: X2 breaks at least 1 full box above X1 top
    if x2['end_level'] < x1_top + box:
        continue

    exit_ts    = cols[idx2 + 4]['end_timestamp']
    exit_price = x2['end_level']

    exit_signals.append({
        'idx2'      : idx2,
        'exit_ts'   : exit_ts,
        'exit_price': exit_price,
        'x1_top'    : x1_top,
    })

# ── Print signals ──────────────────────────────────────────────────────────────
print(f"\nEntry signals (Double Bottom): {len(entry_signals)}")
for e in entry_signals:
    print(f"  col {e['idx2']:4d} | {e['entry_ts']} | price={e['entry_price']:.1f} | O1_bot={e['o1_bottom']:.1f}")

print(f"\nExit signals (Double Top): {len(exit_signals)}")
for x in exit_signals:
    print(f"  col {x['idx2']:4d} | {x['exit_ts']} | price={x['exit_price']:.1f} | X1_top={x['x1_top']:.1f}")

# ── Pair trades ────────────────────────────────────────────────────────────────
print(f"\n{'='*90}")
print(f"{'#':<5} {'Entry Time':<25} {'Entry Price':>12} {'Exit Time':<25} {'Exit Price':>12} {'PnL':>10}")
print(f"{'='*90}")

trade_num = 0
for e in entry_signals:
    matched_exit = None
    for x in exit_signals:
        if x['exit_ts'] > e['entry_ts']:
            matched_exit = x
            break
    if matched_exit:
        trade_num += 1
        pnl = e['entry_price'] - matched_exit['exit_price']
        print(f"{trade_num:<5} {str(e['entry_ts']):<25} {e['entry_price']:>12.1f} "
              f"{str(matched_exit['exit_ts']):<25} {matched_exit['exit_price']:>12.1f} {pnl:>10.1f}")

print(f"{'='*90}")
print(f"Total paired trades: {trade_num}")
