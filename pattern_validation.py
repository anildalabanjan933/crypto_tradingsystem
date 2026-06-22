# pattern_validation.py
# Validates Double Bottom and Double Top pattern detection against standard PnF rules.
# Does NOT run a backtest. Does NOT change any strategy or indicator files.
# Prints audit table with >= 20 examples of each pattern.
# Generates a chart image marking DB1, DB2, ENTRY and DT1, DT2, EXIT points.

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from data.data_loader import DataLoader
from data.data_aggregator import DataAggregator
from indicators.pnf import PnFChartBuilder

# ── Config ─────────────────────────────────────────────────────────────────────
CSV_PATH         = 'data/btc_1m_delta.csv'
START_DATE       = '2025-06-11'
END_DATE         = '2026-06-11'
BOX_SIZE_PERCENT = 0.15
REVERSE_BOXES    = 3

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
print(f"Total PnF columns built: {len(cols)}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# CORRECTED PATTERN DETECTION (standard PnF rules, no box_size threshold)
# These are the REFERENCE implementations used for validation only.
# indicators/pnf.py is NOT modified by this script.
# ══════════════════════════════════════════════════════════════════════════════

def find_double_bottoms(columns):
    """
    Standard PnF Double Bottom Breakdown:
      - Find the two most recent O columns up to and including current column.
      - Pattern fires when current O bottom (end_level) < previous O bottom (end_level).
      - Breakout level = current O bottom (the level at which breakdown is confirmed).
    Returns list of dicts with full audit info.
    """
    results = []
    for col_idx in range(len(columns)):
        if columns[col_idx]['type'] != 'O':
            continue
        # Collect all O columns up to and including col_idx
        o_cols = [(i, columns[i]) for i in range(col_idx + 1) if columns[i]['type'] == 'O']
        if len(o_cols) < 2:
            continue
        first_o_idx,  first_o  = o_cols[-2]
        second_o_idx, second_o = o_cols[-1]
        # Standard rule: current O bottom strictly below previous O bottom
        if second_o['end_level'] < first_o['end_level']:
            box_size = second_o['end_level'] * (BOX_SIZE_PERCENT / 100.0)
            results.append({
                'col_idx'         : col_idx,
                'pattern'         : 'DOUBLE_BOTTOM',
                'first_o_idx'     : first_o_idx,
                'first_o_bottom'  : first_o['end_level'],
                'second_o_idx'    : second_o_idx,
                'second_o_bottom' : second_o['end_level'],
                'box_size'        : round(box_size, 2),
                'breakout_level'  : second_o['end_level'],
                'timestamp'       : second_o['end_timestamp'],
            })
    return results


def find_double_tops(columns):
    """
    Standard PnF Double Top Breakout:
      - Find the two most recent X columns up to and including current column.
      - Pattern fires when current X top (end_level) > previous X top (end_level).
      - Breakout level = current X top (the level at which breakout is confirmed).
    Returns list of dicts with full audit info.
    """
    results = []
    for col_idx in range(len(columns)):
        if columns[col_idx]['type'] != 'X':
            continue
        # Collect all X columns up to and including col_idx
        x_cols = [(i, columns[i]) for i in range(col_idx + 1) if columns[i]['type'] == 'X']
        if len(x_cols) < 2:
            continue
        first_x_idx,  first_x  = x_cols[-2]
        second_x_idx, second_x = x_cols[-1]
        # Standard rule: current X top strictly above previous X top
        if second_x['end_level'] > first_x['end_level']:
            box_size = second_x['end_level'] * (BOX_SIZE_PERCENT / 100.0)
            results.append({
                'col_idx'         : col_idx,
                'pattern'         : 'DOUBLE_TOP',
                'first_x_idx'     : first_x_idx,
                'first_x_top'     : first_x['end_level'],
                'second_x_idx'    : second_x_idx,
                'second_x_top'    : second_x['end_level'],
                'box_size'        : round(box_size, 2),
                'breakout_level'  : second_x['end_level'],
                'timestamp'       : second_x['end_timestamp'],
            })
    return results


# ── Detect all patterns ────────────────────────────────────────────────────────
db_patterns = find_double_bottoms(cols)
dt_patterns = find_double_tops(cols)

print(f"Total Double Bottom patterns found : {len(db_patterns)}")
print(f"Total Double Top    patterns found : {len(dt_patterns)}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT TABLE — DOUBLE BOTTOM (first 25)
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 100)
print("DOUBLE BOTTOM BREAKDOWN — AUDIT TABLE (first 25 examples)")
print("=" * 100)
print(f"  {'#':>3}  {'col_idx':>7}  {'first_O_idx':>11}  {'first_O_bot':>11}  "
      f"{'second_O_idx':>12}  {'second_O_bot':>12}  {'box_size':>8}  "
      f"{'breakout_lvl':>12}  timestamp")
print("-" * 100)
for n, p in enumerate(db_patterns[:25], 1):
    print(f"  {n:>3}  {p['col_idx']:>7}  {p['first_o_idx']:>11}  {p['first_o_bottom']:>11.2f}  "
          f"{p['second_o_idx']:>12}  {p['second_o_bottom']:>12.2f}  {p['box_size']:>8.2f}  "
          f"{p['breakout_level']:>12.2f}  {p['timestamp']}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT TABLE — DOUBLE TOP (first 25)
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 100)
print("DOUBLE TOP BREAKOUT — AUDIT TABLE (first 25 examples)")
print("=" * 100)
print(f"  {'#':>3}  {'col_idx':>7}  {'first_X_idx':>11}  {'first_X_top':>11}  "
      f"{'second_X_idx':>12}  {'second_X_top':>12}  {'box_size':>8}  "
      f"{'breakout_lvl':>12}  timestamp")
print("-" * 100)
for n, p in enumerate(dt_patterns[:25], 1):
    print(f"  {n:>3}  {p['col_idx']:>7}  {p['first_x_idx']:>11}  {p['first_x_top']:>11.2f}  "
          f"{p['second_x_idx']:>12}  {p['second_x_top']:>12.2f}  {p['box_size']:>8.2f}  "
          f"{p['breakout_level']:>12.2f}  {p['timestamp']}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# CURRENT CODE COMPARISON — show what indicators/pnf.py currently detects
# vs what the corrected logic detects, for the first 10 DB and 10 DT
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 100)
print("COMPARISON: current code vs corrected logic (first 10 DB patterns)")
print("  current code requires: second_O < first_O - box_size  (1-box threshold)")
print("  corrected logic:       second_O < first_O             (any amount below)")
print("=" * 100)
print(f"  {'#':>3}  {'col_idx':>7}  {'first_O_bot':>11}  {'second_O_bot':>12}  "
      f"{'diff':>10}  {'box_size':>8}  {'current_fires':>13}  {'corrected_fires':>15}")
print("-" * 100)
for n, p in enumerate(db_patterns[:10], 1):
    diff          = p['first_o_bottom'] - p['second_o_bottom']
    box_size      = p['box_size']
    current_fires = diff > box_size
    corr_fires    = diff > 0
    print(f"  {n:>3}  {p['col_idx']:>7}  {p['first_o_bottom']:>11.2f}  "
          f"{p['second_o_bottom']:>12.2f}  {diff:>10.2f}  {box_size:>8.2f}  "
          f"{'YES' if current_fires else 'NO':>13}  {'YES' if corr_fires else 'NO':>15}")
print()

print("=" * 100)
print("COMPARISON: current code vs corrected logic (first 10 DT patterns)")
print("  current code requires: second_X > first_X + box_size  (1-box threshold)")
print("  corrected logic:       second_X > first_X             (any amount above)")
print("=" * 100)
print(f"  {'#':>3}  {'col_idx':>7}  {'first_X_top':>11}  {'second_X_top':>12}  "
      f"{'diff':>10}  {'box_size':>8}  {'current_fires':>13}  {'corrected_fires':>15}")
print("-" * 100)
for n, p in enumerate(dt_patterns[:10], 1):
    diff          = p['second_x_top'] - p['first_x_top']
    box_size      = p['box_size']
    current_fires = diff > box_size
    corr_fires    = diff > 0
    print(f"  {n:>3}  {p['col_idx']:>7}  {p['first_x_top']:>11.2f}  "
          f"{p['second_x_top']:>12.2f}  {diff:>10.2f}  {box_size:>8.2f}  "
          f"{'YES' if current_fires else 'NO':>13}  {'YES' if corr_fires else 'NO':>15}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# CHART — mark first 20 DB and first 20 DT on a price-vs-column-index plot
# ══════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 1, figsize=(22, 14))
fig.suptitle('PnF Pattern Validation — Double Bottom & Double Top\n'
             'Standard PnF Rules: DB = current O < prev O | DT = current X > prev X',
             fontsize=13, fontweight='bold')

for ax_idx, (ax, patterns, col_type, color_prev, color_curr, color_break,
             label_prev, label_curr, title) in enumerate([
    (axes[0], db_patterns[:20], 'O', '#d62728', '#ff7f0e', '#2ca02c',
     'DB1 (prev O bottom)', 'DB2 (curr O bottom)', 'Double Bottom Breakdown — First 20 Examples'),
    (axes[1], dt_patterns[:20], 'X', '#1f77b4', '#9467bd', '#e377c2',
     'DT1 (prev X top)', 'DT2 (curr X top)', 'Double Top Breakout — First 20 Examples'),
]):
    # Plot all column end_levels as a thin grey line for context
    all_x   = list(range(len(cols)))
    all_end = [c['end_level'] for c in cols]
    ax.plot(all_x, all_end, color='#cccccc', linewidth=0.6, zorder=1, label='Column end_level')

    # Mark O columns (end_level) as small blue dots for context
    o_x = [i for i, c in enumerate(cols) if c['type'] == 'O']
    o_y = [cols[i]['end_level'] for i in o_x]
    ax.scatter(o_x, o_y, color='#aec7e8', s=10, zorder=2, label='O column end')

    # Mark X columns (end_level) as small orange dots for context
    x_x = [i for i, c in enumerate(cols) if c['type'] == 'X']
    x_y = [cols[i]['end_level'] for i in x_x]
    ax.scatter(x_x, x_y, color='#ffbb78', s=10, zorder=2, label='X column end')

    prev_plotted  = False
    curr_plotted  = False
    break_plotted = False

    for n, p in enumerate(patterns):
        if col_type == 'O':
            px, py = p['first_o_idx'],  p['first_o_bottom']
            cx, cy = p['second_o_idx'], p['second_o_bottom']
            bx, by = p['second_o_idx'], p['breakout_level']
        else:
            px, py = p['first_x_idx'],  p['first_x_top']
            cx, cy = p['second_x_idx'], p['second_x_top']
            bx, by = p['second_x_idx'], p['breakout_level']

        lbl_p = label_prev  if not prev_plotted  else None
        lbl_c = label_curr  if not curr_plotted  else None
        lbl_b = 'Breakout level' if not break_plotted else None

        ax.scatter(px, py, color=color_prev,  s=60, zorder=5, marker='^', label=lbl_p)
        ax.scatter(cx, cy, color=color_curr,  s=60, zorder=5, marker='v', label=lbl_c)
        ax.scatter(bx, by, color=color_break, s=80, zorder=6, marker='*', label=lbl_b)

        # Annotate every 4th example to avoid clutter
        if n % 4 == 0:
            ax.annotate(f'#{n+1}', xy=(cx, cy),
                        xytext=(0, -12), textcoords='offset points',
                        fontsize=7, ha='center', color=color_curr)

        prev_plotted  = True
        curr_plotted  = True
        break_plotted = True

    ax.set_title(title, fontsize=11)
    ax.set_xlabel('PnF Column Index', fontsize=9)
    ax.set_ylabel('Price Level (USD)', fontsize=9)
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(True, alpha=0.3)

plt.tight_layout()
chart_path = 'pattern_validation_chart.png'
plt.savefig(chart_path, dpi=150, bbox_inches='tight')
plt.close()
print(f"Chart saved to: {chart_path}")
print()
print("NEXT STEP:")
print("  1. Open pattern_validation_chart.png")
print("  2. Compare DB examples against TradingView PnF chart")
print("  3. Compare DT examples against TradingView PnF chart")
print("  4. If patterns match: apply threshold fixes to indicators/pnf.py")
print("  5. If patterns do not match: investigate column building logic")
