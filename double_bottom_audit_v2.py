# double_bottom_audit_v2.py
# Scans all PnF columns for true Double Bottom Breakdown structures.
# Definition:
#   - O1 bottom establishes support
#   - O2 bottom tests same support (within 1 box tolerance)
#   - O3 bottom breaks below that support level
# No strategy logic. No filters. No backtest.

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
print(f"Total PnF columns : {len(cols)}")
print()

# ── Extract all O columns with index ──────────────────────────────────────────
o_cols = [(i, cols[i]) for i in range(len(cols)) if cols[i]['type'] == 'O']

# ── Scan for Double Bottom Breakdown: O1 ~ O2 support, O3 breaks below ────────
results = []

for k in range(2, len(o_cols)):
    idx1, o1 = o_cols[k - 2]
    idx2, o2 = o_cols[k - 1]
    idx3, o3 = o_cols[k]

    bot1 = o1['end_level']
    bot2 = o2['end_level']
    bot3 = o3['end_level']

    # Box size computed at O1 bottom level
    box_size_pts = bot1 * (BOX_SIZE_PERCENT / 100.0)

    # O1 and O2 must share support: within 1 box of each other
    support_diff_boxes = abs(bot1 - bot2) / box_size_pts
    if support_diff_boxes > 1.0:
        continue

    # O3 must break below the lower of O1/O2 bottoms
    support_level = min(bot1, bot2)
    breakdown_pts = support_level - bot3
    breakdown_boxes = breakdown_pts / box_size_pts

    if breakdown_boxes <= 0:
        continue  # O3 did not break below support

    results.append({
        'idx1'              : idx1,
        'idx2'              : idx2,
        'idx3'              : idx3,
        'bot1'              : bot1,
        'bot2'              : bot2,
        'bot3'              : bot3,
        'support_level'     : support_level,
        'support_diff_boxes': round(support_diff_boxes, 2),
        'breakdown_boxes'   : round(breakdown_boxes, 2),
        'ts1'               : o1['end_timestamp'],
        'ts2'               : o2['end_timestamp'],
        'ts3'               : o3['end_timestamp'],
    })

# ── Print results ──────────────────────────────────────────────────────────────
print("=" * 110)
print(f"TRUE DOUBLE BOTTOM BREAKDOWN — {len(results)} found")
print("Definition: O1 bottom ~ O2 bottom (within 1 box), O3 breaks below support")
print("=" * 110)
print(f"  {'#':>3}  {'O1_idx':>6}  {'O2_idx':>6}  {'O3_idx':>6}"
      f"  {'O1_bot':>12}  {'O2_bot':>12}  {'O3_bot':>12}"
      f"  {'support':>12}  {'O1~O2 boxes':>11}  {'breakdown':>10}  {'O3 timestamp'}")
print("-" * 110)

for i, r in enumerate(results):
    print(f"  {i+1:>3}  {r['idx1']:>6}  {r['idx2']:>6}  {r['idx3']:>6}"
          f"  {r['bot1']:>12.2f}  {r['bot2']:>12.2f}  {r['bot3']:>12.2f}"
          f"  {r['support_level']:>12.2f}  {r['support_diff_boxes']:>11.2f}  {r['breakdown_boxes']:>10.2f}"
          f"  {r['ts3']}")

print()
print("=" * 60)
print("HISTOGRAM — breakdown distance below support (O3 vs support)")
print("=" * 60)

buckets = [
    ("breakdown <= 1 box",   lambda b: b <= 1.0),
    ("breakdown <= 2 boxes", lambda b: b <= 2.0),
    ("breakdown <= 3 boxes", lambda b: b <= 3.0),
    ("breakdown <= 5 boxes", lambda b: b <= 5.0),
    ("breakdown <= 10 boxes",lambda b: b <= 10.0),
    ("breakdown >  10 boxes",lambda b: b >  10.0),
]

total = len(results)
print(f"  {'Bucket':<25}  {'Count':>6}  {'Pct':>6}  Bar")
print("-" * 60)
for label, fn in buckets:
    count = sum(1 for r in results if fn(r['breakdown_boxes']))
    pct   = (count / total * 100) if total > 0 else 0
    bar   = '#' * int(pct / 2)
    print(f"  {label:<25}  {count:>6}  {pct:>5.1f}%  {bar}")

print()
print(f"  Total found : {total}")
if results:
    vals = [r['breakdown_boxes'] for r in results]
    print(f"  Min breakdown : {min(vals):.2f} boxes")
    print(f"  Max breakdown : {max(vals):.2f} boxes")
    mean = sum(vals) / len(vals)
    sorted_vals = sorted(vals)
    mid = len(sorted_vals) // 2
    median = sorted_vals[mid] if len(sorted_vals) % 2 != 0 else (sorted_vals[mid-1] + sorted_vals[mid]) / 2
    print(f"  Mean          : {mean:.2f} boxes")
    print(f"  Median        : {median:.2f} boxes")
