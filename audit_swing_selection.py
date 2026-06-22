# audit_swing_selection.py
# Tests multiple swing-low and swing-high selection methods on Nov 4-7 data
# Prints: selected column, reason, trigger level for each method
# No code changes to indicators/pnf.py — audit only

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.data_loader import DataLoader
from data.data_aggregator import DataAggregator
from indicators.pnf import PnFChartBuilder

# ── Config ────────────────────────────────────────────────────────────────────
CSV_PATH      = "data/btc_1m_delta.csv"
START_DATE    = "2025-06-11"
END_DATE      = "2026-06-11"
BOX_PCT       = 0.15        # percentage (not decimal)
REVERSAL      = 3

# Focus window for audit
AUDIT_START_IDX = 459
AUDIT_END_IDX   = 483

# Active columns being tested
TARGET_O_COL    = 482   # Nov 7 05:00 breakdown column
TARGET_X_COL    = 483   # Nov 7 12:00 rally column

# ── Load data ─────────────────────────────────────────────────────────────────
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

# ── Build PnF columns ─────────────────────────────────────────────────────────
builder = PnFChartBuilder(box_size_percent=BOX_PCT, reverse_boxes=REVERSAL)
raw_cols = builder.build_pnf_chart(data_1h)

# Normalise into a flat list of dicts with consistent field names
columns = []
for i, c in enumerate(raw_cols):
    columns.append({
        'index'    : i,
        'type'     : c['type'],
        'start'    : c.get('start_level', 0),
        'end'      : c.get('end_level',   0),
        'start_ts' : c.get('start_timestamp', ''),
        'end_ts'   : c.get('end_timestamp',   ''),
    })

print(f"\n  Total PnF columns: {len(columns)}")

# ── Extract audit window ──────────────────────────────────────────────────────
window  = [c for c in columns if AUDIT_START_IDX <= c['index'] <= AUDIT_END_IDX]
o_cols  = [c for c in window if c['type'] == 'O']
x_cols  = [c for c in window if c['type'] == 'X']

prior_o = [c for c in o_cols if c['index'] < TARGET_O_COL]
prior_x = [c for c in x_cols if c['index'] < TARGET_X_COL]

# ── Print raw column data ─────────────────────────────────────────────────────
print("\n" + "="*80)
print("RAW COLUMN DATA (Nov 4-7 window)")
print("="*80)
print(f"  {'idx':>4}  {'type':>4}  {'start':>12}  {'end':>12}  {'start_ts'}")
print("-"*80)
for c in window:
    print(f"  {c['index']:>4}  {c['type']:>4}  {c['start']:>12.2f}  {c['end']:>12.2f}  {c['start_ts']}")

# ── Helpers ───────────────────────────────────────────────────────────────────
def box_size(price):
    return price * (BOX_PCT / 100.0)

def print_selection(label, selected_col, trigger, signal_type, reason):
    if selected_col is None:
        print(f"\n  [{label}]")
        print(f"    Selected col : None")
        print(f"    Reason       : {reason}")
        return
    ref_price = selected_col['end']
    bx        = box_size(ref_price)
    print(f"\n  [{label}]")
    print(f"    Selected col : {selected_col['index']}  ({selected_col['start_ts']})")
    print(f"    Reference px : {ref_price:.2f}")
    print(f"    Box size     : {bx:.2f} pts")
    print(f"    Reason       : {reason}")
    print(f"    Trigger level: {trigger:.2f}  ({signal_type})")

# ══════════════════════════════════════════════════════════════════════════════
# ENTRY SWING LOW SELECTION — 4 methods
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*80)
print(f"ENTRY SWING LOW SELECTION  (active O col = {TARGET_O_COL})")
print("="*80)

# Method 1 — immediately prior O column
m1 = prior_o[-1] if prior_o else None
if m1:
    ref  = m1['end']
    trig = ref - box_size(ref)
    print_selection("Method 1 — Immediately prior O column", m1, trig,
                    "entry (short)",
                    f"Last completed O col before col {TARGET_O_COL}")

# Method 2 — lowest bottom among all prior O columns
m2 = min(prior_o, key=lambda c: c['end']) if prior_o else None
if m2:
    ref  = m2['end']
    trig = ref - box_size(ref)
    print_selection("Method 2 — Lowest bottom among all prior O cols", m2, trig,
                    "entry (short)",
                    f"Absolute lowest O bottom in window before col {TARGET_O_COL}")

# Method 3 — most recent local trough O column
m3 = None
for i in range(len(prior_o) - 1, 0, -1):
    prev_b = prior_o[i-1]['end']
    curr_b = prior_o[i]['end']
    if i + 1 < len(prior_o):
        next_b = prior_o[i+1]['end']
        if curr_b < prev_b and curr_b < next_b:
            m3 = prior_o[i]
            break
    else:
        if curr_b < prev_b:
            m3 = prior_o[i]
            break

if m3:
    ref  = m3['end']
    trig = ref - box_size(ref)
    print_selection("Method 3 — Most recent local trough O column", m3, trig,
                    "entry (short)",
                    "Most recent O col lower than both its neighbours in prior_o")
else:
    print("\n  [Method 3 — Most recent local trough O column]")
    print("    Selected col : None — no local trough found in prior O cols")

# Method 4 — most recent O column lower than its immediate predecessor
m4 = None
for i in range(len(prior_o) - 1, 0, -1):
    if prior_o[i]['end'] < prior_o[i-1]['end']:
        m4 = prior_o[i]
        break

if m4:
    ref  = m4['end']
    trig = ref - box_size(ref)
    print_selection("Method 4 — Most recent O col lower than its predecessor", m4, trig,
                    "entry (short)",
                    f"Scanning back from col {TARGET_O_COL - 1}, first O col where bottom < prev O bottom")
else:
    print("\n  [Method 4 — Most recent O col lower than its predecessor]")
    print("    Selected col : None")

# ══════════════════════════════════════════════════════════════════════════════
# EXIT SWING HIGH SELECTION — 4 methods
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*80)
print(f"EXIT SWING HIGH SELECTION  (active X col = {TARGET_X_COL})")
print("="*80)

# Method 1 — immediately prior X column
n1 = prior_x[-1] if prior_x else None
if n1:
    ref  = n1['end']
    trig = ref + box_size(ref)
    print_selection("Method 1 — Immediately prior X column", n1, trig,
                    "exit (cover short)",
                    f"Last completed X col before col {TARGET_X_COL}")

# Method 2 — highest top among all prior X columns
n2 = max(prior_x, key=lambda c: c['end']) if prior_x else None
if n2:
    ref  = n2['end']
    trig = ref + box_size(ref)
    print_selection("Method 2 — Highest top among all prior X cols", n2, trig,
                    "exit (cover short)",
                    f"Absolute highest X top in window before col {TARGET_X_COL}")

# Method 3 — most recent local peak X column
n3 = None
for i in range(len(prior_x) - 1, 0, -1):
    prev_t = prior_x[i-1]['end']
    curr_t = prior_x[i]['end']
    if i + 1 < len(prior_x):
        next_t = prior_x[i+1]['end']
        if curr_t > prev_t and curr_t > next_t:
            n3 = prior_x[i]
            break
    else:
        if curr_t > prev_t:
            n3 = prior_x[i]
            break

if n3:
    ref  = n3['end']
    trig = ref + box_size(ref)
    print_selection("Method 3 — Most recent local peak X column", n3, trig,
                    "exit (cover short)",
                    "Most recent X col higher than both its neighbours in prior_x")
else:
    print("\n  [Method 3 — Most recent local peak X column]")
    print("    Selected col : None — no local peak found in prior X cols")

# Method 4 — most recent X column higher than its immediate predecessor
n4 = None
for i in range(len(prior_x) - 1, 0, -1):
    if prior_x[i]['end'] > prior_x[i-1]['end']:
        n4 = prior_x[i]
        break

if n4:
    ref  = n4['end']
    trig = ref + box_size(ref)
    print_selection("Method 4 — Most recent X col higher than its predecessor", n4, trig,
                    "exit (cover short)",
                    f"Scanning back from col {TARGET_X_COL - 1}, first X col where top > prev X top")
else:
    print("\n  [Method 4 — Most recent X col higher than its predecessor]")
    print("    Selected col : None")

# ── Summary table ─────────────────────────────────────────────────────────────
print("\n" + "="*80)
print("SUMMARY")
print("="*80)

target_o = next((c for c in o_cols if c['index'] == TARGET_O_COL), None)
target_x = next((c for c in x_cols if c['index'] == TARGET_X_COL), None)

if target_o:
    print(f"\n  Active O col {TARGET_O_COL} bottom : {target_o['end']:.2f}")
if target_x:
    print(f"  Active X col {TARGET_X_COL} top    : {target_x['end']:.2f}")

print(f"\n  {'Method':<50}  {'Support col':>11}  {'Support px':>11}  {'Entry trigger':>14}")
print(f"  {'-'*50}  {'-'*11}  {'-'*11}  {'-'*14}")
for label, col in [
    ("M1 — Immediately prior O col",          m1),
    ("M2 — Lowest O bottom in window",         m2),
    ("M3 — Most recent local trough O col",    m3),
    ("M4 — Most recent O col < predecessor",   m4),
]:
    if col:
        ref  = col['end']
        trig = ref - box_size(ref)
        print(f"  {label:<50}  col {col['index']:>6}  {ref:>11.2f}  {trig:>14.2f}")
    else:
        print(f"  {label:<50}  {'None':>11}  {'—':>11}  {'—':>14}")

print(f"\n  {'Method':<50}  {'Resist col':>10}  {'Resist px':>10}  {'Exit trigger':>13}")
print(f"  {'-'*50}  {'-'*10}  {'-'*10}  {'-'*13}")
for label, col in [
    ("M1 — Immediately prior X col",           n1),
    ("M2 — Highest X top in window",            n2),
    ("M3 — Most recent local peak X col",       n3),
    ("M4 — Most recent X col > predecessor",    n4),
]:
    if col:
        ref  = col['end']
        trig = ref + box_size(ref)
        print(f"  {label:<50}  col {col['index']:>5}  {ref:>10.2f}  {trig:>13.2f}")
    else:
        print(f"  {label:<50}  {'None':>10}  {'—':>10}  {'—':>13}")

print("\nDone.")
