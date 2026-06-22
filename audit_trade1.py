# pattern_audit_v1.py
# Audits all Double Bottom detections.
# For each: prev O bottom, curr O bottom, diff in points and boxes.
# Produces histogram to separate genuine support retests from continuation breakdowns.

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

# ── Collect all Double Bottom detections ───────────────────────────────────────
entries = []

for idx in range(len(cols)):
    if cols[idx]['type'] != 'O':
        continue
    o_cols = [(i, cols[i]) for i in range(idx + 1) if cols[i]['type'] == 'O']
    if len(o_cols) < 2:
        continue

    prev_o_idx, prev_o = o_cols[-2]
    curr_o_idx, curr_o = o_cols[-1]

    if curr_o['end_level'] < prev_o['end_level']:
        # Box size is percentage-based — compute at prev O bottom level
        box_size_pts = prev_o['end_level'] * (BOX_SIZE_PERCENT / 100.0)
        diff_pts     = prev_o['end_level'] - curr_o['end_level']
        diff_boxes   = diff_pts / box_size_pts

        entries.append({
            'prev_o_idx'  : prev_o_idx,
            'curr_o_idx'  : curr_o_idx,
            'timestamp'   : curr_o['end_timestamp'],
            'prev_o_bot'  : prev_o['end_level'],
            'curr_o_bot'  : curr_o['end_level'],
            'diff_pts'    : round(diff_pts, 2),
            'diff_boxes'  : round(diff_boxes, 2),
            'box_size_pts': round(box_size_pts, 2),
        })

# ── Print first 20 ─────────────────────────────────────────────────────────────
print("=" * 90)
print(f"DOUBLE BOTTOM AUDIT — first 20 of {len(entries)} total detections")
print("=" * 90)
print(f"  {'#':>3}  {'prev_col':>8}  {'curr_col':>8}  {'timestamp':<22}"
      f"  {'prev_O_bot':>12}  {'curr_O_bot':>12}  {'diff_pts':>10}  {'diff_boxes':>10}")
print("-" * 90)

for i, e in enumerate(entries[:20]):
    print(f"  {i+1:>3}  {e['prev_o_idx']:>8}  {e['curr_o_idx']:>8}  {str(e['timestamp']):<22}"
          f"  {e['prev_o_bot']:>12.2f}  {e['curr_o_bot']:>12.2f}"
          f"  {e['diff_pts']:>10.2f}  {e['diff_boxes']:>10.2f}")

# ── Histogram ──────────────────────────────────────────────────────────────────
total = len(entries)

buckets = [
    ('diff <= 1 box ',  lambda d: d <= 1.0),
    ('diff <= 2 boxes', lambda d: d <= 2.0),
    ('diff <= 3 boxes', lambda d: d <= 3.0),
    ('diff <= 5 boxes', lambda d: d <= 5.0),
    ('diff <= 10 boxes',lambda d: d <= 10.0),
    ('diff >  10 boxes',lambda d: d >  10.0),
]

print()
print("=" * 60)
print(f"HISTOGRAM — breakdown gap distribution ({total} total entries)")
print("=" * 60)
print(f"  {'Bucket':<20}  {'Count':>6}  {'Pct':>7}  {'Bar'}")
print("-" * 60)

for label, condition in buckets:
    count = sum(1 for e in entries if condition(e['diff_boxes']))
    pct   = (count / total * 100) if total > 0 else 0
    bar   = '#' * int(pct / 2)
    print(f"  {label:<20}  {count:>6}  {pct:>6.1f}%  {bar}")

print()
print(f"  Min diff  : {min(e['diff_boxes'] for e in entries):.2f} boxes")
print(f"  Max diff  : {max(e['diff_boxes'] for e in entries):.2f} boxes")
print(f"  Mean diff : {sum(e['diff_boxes'] for e in entries) / total:.2f} boxes")
print(f"  Median    : {sorted(e['diff_boxes'] for e in entries)[total // 2]:.2f} boxes")
