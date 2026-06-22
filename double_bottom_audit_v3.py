# double_bottom_audit_v3.py
# Stricter Double Bottom Breakdown audit.
# Requirements:
#   1. O1 and O2 bottoms within 0.5 box of each other (shared support)
#   2. At least one X column exists between O1 and O2
#   3. O3 breaks below support by 0.5 to 3 boxes only
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

# ── Extract all O columns with their position in the full column list ──────────
o_cols = [(i, cols[i]) for i in range(len(cols)) if cols[i]['type'] == 'O']

# ── Scan for strict Double Bottom Breakdown ────────────────────────────────────
results = []

for k in range(2, len(o_cols)):
    idx1, o1 = o_cols[k - 2]
    idx2, o2 = o_cols[k - 1]
    idx3, o3 = o_cols[k]

    bot1 = o1['end_level']
    bot2 = o2['end_level']
    bot3 = o3['end_level']

    # Box size at O1 bottom level
    box_size_pts = bot1 * (BOX_SIZE_PERCENT / 100.0)

    # ── Rule 1: O1 and O2 bottoms within 0.5 box ──────────────────────────────
    support_diff_boxes = abs(bot1 - bot2) / box_size_pts
    if support_diff_boxes > 0.5:
        continue

    # ── Rule 2: At least one X column between O1 and O2 ───────────────────────
    # O columns are every other column, so there is always exactly one X between
    # consecutive O columns. Verify by checking col indexes are not adjacent
    # (idx2 must be idx1 + 2 minimum, meaning one X sits at idx1 + 1)
    cols_between = idx2 - idx1
    if cols_between < 2:
        continue  # no X column between them — should not happen but guard anyway

    # Count X columns between idx1 and idx2 explicitly
    x_between = [i for i in range(idx1 + 1, idx2) if cols[i]['type'] == 'X']
    if len(x_between) < 1:
        continue

    # ── Rule 3: O3 breaks below support by 0.5 to 3 boxes ────────────────────
    support_level  = min(bot1, bot2)
    breakdown_pts  = support_level - bot3
    breakdown_boxes = breakdown_pts / box_size_pts

    if breakdown_boxes < 0.5 or breakdown_boxes > 3.0:
        continue

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
        'x_cols_between'    : len(x_between),
        'ts1'               : o1['end_timestamp'],
        'ts2'               : o2['end_timestamp'],
        'ts3'               : o3['end_timestamp'],
    })

# ── Print first 20 ─────────────────────────────────────────────────────────────
print("=" * 120)
print(f"STRICT DOUBLE BOTTOM BREAKDOWN — {len(results)} total found")
print("Rules: O1~O2 within 0.5 box | X between O1 and O2 | O3 breaks 0.5-3 boxes below support")
print("=" * 120)
print(f"  {'#':>3}  {'O1_idx':>6}  {'O2_idx':>6}  {'O3_idx':>6}"
      f"  {'O1_bot':>12}  {'O2_bot':>12}  {'O3_bot':>12}"
      f"  {'support':>12}  {'O1~O2':>7}  {'breakdown':>10}"
      f"  {'X_between':>9}  O3_timestamp")
print("-" * 120)

for i, r in enumerate(results[:20]):
    print(f"  {i+1:>3}  {r['idx1']:>6}  {r['idx2']:>6}  {r['idx3']:>6}"
          f"  {r['bot1']:>12.2f}  {r['bot2']:>12.2f}  {r['bot3']:>12.2f}"
          f"  {r['support_level']:>12.2f}  {r['support_diff_boxes']:>7.2f}  {r['breakdown_boxes']:>10.2f}"
          f"  {r['x_cols_between']:>9}  {r['ts3']}")

if len(results) > 20:
    print(f"\n  ... and {len(results) - 20} more (showing first 20 only)")

print()
print("=" * 60)
print(f"SUMMARY")
print("=" * 60)
print(f"  Total strict matches : {len(results)}")
if results:
    vals = [r['breakdown_boxes'] for r in results]
    print(f"  Min breakdown        : {min(vals):.2f} boxes")
    print(f"  Max breakdown        : {max(vals):.2f} boxes")
    mean = sum(vals) / len(vals)
    sorted_vals = sorted(vals)
    mid = len(sorted_vals) // 2
    median = (sorted_vals[mid] if len(sorted_vals) % 2 != 0
              else (sorted_vals[mid - 1] + sorted_vals[mid]) / 2)
    print(f"  Mean breakdown       : {mean:.2f} boxes")
    print(f"  Median breakdown     : {median:.2f} boxes")
