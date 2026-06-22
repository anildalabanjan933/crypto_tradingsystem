# pattern_validation_v2_debug.py
# Diagnostic version — counts how many candidates pass each rule individually
# and in combination, to identify which rule is eliminating all results.

import pandas as pd
from data.data_loader import DataLoader
from data.data_aggregator import DataAggregator
from indicators.pnf import PnFChartBuilder

# ── Config ─────────────────────────────────────────────────────────────────────
CSV_PATH         = 'data/btc_1m_delta.csv'
START_DATE       = '2025-06-11'
END_DATE         = '2026-06-11'
BOX_SIZE_PERCENT = 0.15
REVERSE_BOXES    = 3
N_VALUES         = [1, 2, 3, 5, 10]  # wider range to find where results appear

# ── Load data ──────────────────────────────────────────────────────────────────
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

# ── Build PnF columns ──────────────────────────────────────────────────────────
builder = PnFChartBuilder(box_size_percent=BOX_SIZE_PERCENT, reverse_boxes=REVERSE_BOXES)
cols    = builder.build_pnf_chart(data_1h)
print(f"Total PnF columns: {len(cols)}")
print()

def get_typed_cols(columns, up_to_idx, col_type):
    return [(i, columns[i]) for i in range(up_to_idx + 1)
            if columns[i]['type'] == col_type]

# ── Full diagnostic pass ───────────────────────────────────────────────────────
# Collect all candidates with individual rule results, independent of N
candidates = []

for idx in range(len(cols)):
    col = cols[idx]
    if col['type'] != 'O':
        continue

    o_cols = get_typed_cols(cols, idx, 'O')
    x_cols = get_typed_cols(cols, idx, 'X')

    if len(o_cols) < 4 or len(x_cols) < 2:
        continue

    o2_idx,      o2      = o_cols[-1]
    o1_idx,      o1      = o_cols[-2]
    o_prev1_idx, o_prev1 = o_cols[-3]
    o_prev2_idx, o_prev2 = o_cols[-4]

    x_between_idx, x_between = x_cols[-1]
    x_before_idx,  x_before  = x_cols[-2]

    # Sanity checks
    if not (o1_idx < x_between_idx < o2_idx):
        continue
    if not (x_before_idx < o1_idx):
        continue

    rule1_step1 = o_prev1['end_level'] > o_prev2['end_level']
    rule1_step2 = o1['end_level']      > o_prev1['end_level']
    rule1_pass  = rule1_step1 and rule1_step2

    rule2_pass  = x_between['end_level'] < x_before['end_level']

    rule4_pass  = o2['end_level'] < o1['end_level']

    box_size    = o1['end_level'] * (BOX_SIZE_PERCENT / 100.0)

    # O2 high distance above O1 bottom in boxes
    o2_high_gap_boxes = (o2['high'] - o1['end_level']) / box_size

    candidates.append({
        'col_idx'           : idx,
        'timestamp'         : col['end_timestamp'],
        'o_prev2_idx'       : o_prev2_idx,
        'o_prev2_bot'       : o_prev2['end_level'],
        'o_prev1_idx'       : o_prev1_idx,
        'o_prev1_bot'       : o_prev1['end_level'],
        'o1_idx'            : o1_idx,
        'o1_bot'            : o1['end_level'],
        'x_before_idx'      : x_before_idx,
        'x_before_top'      : x_before['end_level'],
        'x_between_idx'     : x_between_idx,
        'x_between_top'     : x_between['end_level'],
        'o2_idx'            : o2_idx,
        'o2_high'           : o2['high'],
        'o2_bot'            : o2['end_level'],
        'box_size'          : round(box_size, 2),
        'o2_high_gap_boxes' : round(o2_high_gap_boxes, 2),
        'rule1'             : rule1_pass,
        'rule2'             : rule2_pass,
        'rule4'             : rule4_pass,
    })

print(f"Total candidates (passed sanity + have 4 O cols + 2 X cols): {len(candidates)}")
print()

# ── Rule-by-rule counts ────────────────────────────────────────────────────────
r1      = [c for c in candidates if c['rule1']]
r2      = [c for c in candidates if c['rule2']]
r4      = [c for c in candidates if c['rule4']]
r1r2    = [c for c in candidates if c['rule1'] and c['rule2']]
r1r4    = [c for c in candidates if c['rule1'] and c['rule4']]
r2r4    = [c for c in candidates if c['rule2'] and c['rule4']]
r1r2r4  = [c for c in candidates if c['rule1'] and c['rule2'] and c['rule4']]

print("Rule pass counts (Rule 3 / proximity excluded here):")
print(f"  Rule 1 only  (ascending O)    : {len(r1)}")
print(f"  Rule 2 only  (lower X high)   : {len(r2)}")
print(f"  Rule 4 only  (breakdown)      : {len(r4)}")
print(f"  Rule 1 + 2                    : {len(r1r2)}")
print(f"  Rule 1 + 4                    : {len(r1r4)}")
print(f"  Rule 2 + 4                    : {len(r2r4)}")
print(f"  Rule 1 + 2 + 4 (no proximity) : {len(r1r2r4)}")
print()

# ── Proximity distribution for Rule 1+2+4 passing candidates ──────────────────
if r1r2r4:
    gaps = sorted([c['o2_high_gap_boxes'] for c in r1r2r4])
    print(f"O2 high gap above O1 bottom (in boxes) — for {len(r1r2r4)} candidates passing R1+R2+R4:")
    print(f"  Min  : {min(gaps):.2f} boxes")
    print(f"  Max  : {max(gaps):.2f} boxes")
    print(f"  Mean : {sum(gaps)/len(gaps):.2f} boxes")
    print()
    print("  Distribution:")
    for threshold in [0, 1, 2, 3, 5, 10, 20, 50]:
        count = sum(1 for g in gaps if g <= threshold)
        print(f"    gap <= {threshold:>3} boxes : {count:>4} candidates")
    print()

    print("  First 20 candidates passing R1+R2+R4 (sorted by col_idx):")
    print()
    header = (
        f"  {'#':>3}  {'col':>4}  {'timestamp':<20}  "
        f"{'O_p2_bot':>10}  {'O_p1_bot':>10}  {'O1_bot':>10}  "
        f"{'Xbef_top':>10}  {'Xbet_top':>10}  "
        f"{'O2_high':>10}  {'gap_boxes':>9}  {'O2_bot':>10}"
    )
    print(header)
    print("  " + "-" * 105)
    for n, c in enumerate(r1r2r4[:20], 1):
        row = (
            f"  {n:>3}  {c['col_idx']:>4}  {str(c['timestamp']):<20}  "
            f"{c['o_prev2_bot']:>10.2f}  {c['o_prev1_bot']:>10.2f}  {c['o1_bot']:>10.2f}  "
            f"{c['x_before_top']:>10.2f}  {c['x_between_top']:>10.2f}  "
            f"{c['o2_high']:>10.2f}  {c['o2_high_gap_boxes']:>9.2f}  {c['o2_bot']:>10.2f}"
        )
        print(row)
    print()
else:
    print("Zero candidates pass Rule 1 + 2 + 4 combined.")
    print()
    print("Showing first 20 candidates passing Rule 1 only:")
    print()
    for n, c in enumerate(r1[:20], 1):
        print(
            f"  {n:>3}  col={c['col_idx']:>4}  {str(c['timestamp']):<20}  "
            f"O_p2={c['o_prev2_bot']:>10.2f}  O_p1={c['o_prev1_bot']:>10.2f}  "
            f"O1={c['o1_bot']:>10.2f}  "
            f"R1={'Y' if c['rule1'] else 'N'}  R2={'Y' if c['rule2'] else 'N'}  R4={'Y' if c['rule4'] else 'N'}"
        )
    print()
    print("Showing first 20 candidates passing Rule 2 only:")
    print()
    for n, c in enumerate(r2[:20], 1):
        print(
            f"  {n:>3}  col={c['col_idx']:>4}  {str(c['timestamp']):<20}  "
            f"Xbef={c['x_before_top']:>10.2f}  Xbet={c['x_between_top']:>10.2f}  "
            f"R1={'Y' if c['rule1'] else 'N'}  R2={'Y' if c['rule2'] else 'N'}  R4={'Y' if c['rule4'] else 'N'}"
        )

# ── Trade #1 specific audit ────────────────────────────────────────────────────
print()
print("=" * 60)
print("TRADE #1 AUDIT — col 18 (2025-06-17 16:00)")
print("=" * 60)
t1 = [c for c in candidates if c['col_idx'] == 18]
if t1:
    c = t1[0]
    print(f"  O_prev2 bot  : {c['o_prev2_bot']:.2f}  (col {c['o_prev2_idx']})")
    print(f"  O_prev1 bot  : {c['o_prev1_bot']:.2f}  (col {c['o_prev1_idx']})")
    print(f"  O1 bot       : {c['o1_bot']:.2f}  (col {c['o1_idx']})")
    print(f"  X_before top : {c['x_before_top']:.2f}  (col {c['x_before_idx']})")
    print(f"  X_between top: {c['x_between_top']:.2f}  (col {c['x_between_idx']})")
    print(f"  O2 high      : {c['o2_high']:.2f}  (col {c['o2_idx']})")
    print(f"  O2 bot       : {c['o2_bot']:.2f}")
    print(f"  Box size     : {c['box_size']:.2f}")
    print(f"  O2 high gap  : {c['o2_high_gap_boxes']:.2f} boxes above O1 bottom")
    print(f"  Rule 1       : {'PASS' if c['rule1'] else 'FAIL'}")
    print(f"  Rule 2       : {'PASS' if c['rule2'] else 'FAIL'}")
    print(f"  Rule 4       : {'PASS' if c['rule4'] else 'FAIL'}")
else:
    print("  col 18 not in candidate list — eliminated by sanity checks")
    print("  Checking why...")
    # Manual check for col 18
    o_cols_18 = get_typed_cols(cols, 18, 'O')
    x_cols_18 = get_typed_cols(cols, 18, 'X')
    print(f"  O columns up to col 18: {len(o_cols_18)}")
    print(f"  X columns up to col 18: {len(x_cols_18)}")
    if len(o_cols_18) >= 2 and len(x_cols_18) >= 1:
        o2i, o2c = o_cols_18[-1]
        o1i, o1c = o_cols_18[-2]
        xbi, xbc = x_cols_18[-1]
        print(f"  O2 (col {o2i}): high={o2c['high']:.2f}  end={o2c['end_level']:.2f}")
        print(f"  O1 (col {o1i}): end={o1c['end_level']:.2f}")
        print(f"  X_between (col {xbi}): end={xbc['end_level']:.2f}")
        print(f"  X_between between O1 and O2? {o1i < xbi < o2i}")

print()
print("Done.")
