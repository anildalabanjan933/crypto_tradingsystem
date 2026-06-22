# diagnose_w2.py
# Read-only diagnostic for Trade 45 (W2) - 2025-11-13 20:00 @ 98,136

import sys
sys.path.insert(0, '.')
import pandas as pd
from indicators.pnf import PnFChartBuilder

# ── Load and prepare data ──────────────────────────────────────────
df = pd.read_csv('data/btc_1m_delta.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
df = df.set_index('timestamp').sort_index()
df = df[df.index >= '2025-06-10']

df_1h = df['close'].resample('1h').ohlc()
df_1h.columns = ['open', 'high', 'low', 'close']
df_1h = df_1h.dropna()

# ── Build PnF chart ────────────────────────────────────────────────
builder = PnFChartBuilder(box_size_percent=0.15, reverse_boxes=3)
columns = builder.build_pnf_chart(df_1h)

# ── Find entry column: first O column whose end_timestamp >= 2025-11-13 20:00 ──
entry_time = pd.Timestamp('2025-11-13 20:00:00')

entry_col_idx = None
for i, col in enumerate(columns):
    if col['type'] == 'O' and pd.Timestamp(col['end_timestamp']) >= entry_time:
        entry_col_idx = i
        break

if entry_col_idx is None:
    print("ERROR: Could not find entry column near 2025-11-13 20:00")
    sys.exit(1)

entry_col = columns[entry_col_idx]
print(f"\n=== W2 ENTRY COLUMN ===")
print(f"Column index : {entry_col_idx}")
print(f"Type         : {entry_col['type']}")
print(f"start_level  : {entry_col['start_level']}")
print(f"end_level    : {entry_col['end_level']}")
print(f"start_time   : {entry_col['start_timestamp']}")
print(f"end_time     : {entry_col['end_timestamp']}")

# ── Collect all O columns before entry column ─────────────────────
o_cols_before = [(i, c) for i, c in enumerate(columns)
                 if c['type'] == 'O' and i < entry_col_idx]

print(f"\n=== ALL O COLUMNS BEFORE ENTRY (last 10) ===")
print(f"{'Idx':>5}  {'end_level':>12}  {'end_time'}")
for i, c in o_cols_before[-10:]:
    print(f"{i:>5}  {c['end_level']:>12.1f}  {c['end_timestamp']}")

# ── Trace rising anchor sequence ending at entry column ───────────
# Same logic as V2 strategy: walk backwards, collect strictly rising O bottoms
lookback = 10  # check last 10 O columns for context
recent_o = o_cols_before[-lookback:]

print(f"\n=== RISING ANCHOR TRACE (last {lookback} O columns) ===")
print(f"Looking for strictly rising sequence (each O bottom > previous)")
print()

anchors = []
for i, c in recent_o:
    level = c['end_level']
    if len(anchors) == 0:
        anchors.append((i, level))
        print(f"  Col {i:>4} | end_level={level:>10.1f} | START anchor")
    elif level > anchors[-1][1]:
        anchors.append((i, level))
        print(f"  Col {i:>4} | end_level={level:>10.1f} | RISING (+{level - anchors[-2][1]:.1f}) -> anchor added")
    else:
        print(f"  Col {i:>4} | end_level={level:>10.1f} | NOT rising (prev={anchors[-1][1]:.1f}) -> RESET")
        anchors = [(i, level)]

print(f"\n=== ANCHOR RESULT ===")
print(f"Final anchor count : {len(anchors)}")
print(f"Anchor values      : {[round(a[1],1) for a in anchors]}")
print(f"3-anchor rule pass : {len(anchors) >= 3}")
print(f"2-anchor rule pass : {len(anchors) >= 2}")

if len(anchors) >= 2:
    first_idx, first_val = anchors[0]
    last_idx,  last_val  = anchors[-1]
    entry_bottom = entry_col['end_level']
    slope = (last_val - first_val) / (last_idx - first_idx) if last_idx != first_idx else 0
    projected = last_val + slope * (entry_col_idx - last_idx)
    print(f"\n=== TRENDLINE PROJECTION (2-anchor) ===")
    print(f"Anchor 1 : col {first_idx} @ {first_val:.1f}")
    print(f"Anchor 2 : col {last_idx} @ {last_val:.1f}")
    print(f"Slope    : {slope:.4f} per column")
    print(f"Projected value at entry col {entry_col_idx} : {projected:.1f}")
    print(f"Entry O bottom                               : {entry_bottom:.1f}")
    print(f"Trendline break (entry < projected)          : {entry_bottom < projected}")
