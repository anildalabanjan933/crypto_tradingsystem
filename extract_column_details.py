import pandas as pd
import glob
import sys
sys.path.insert(0, '.')

from indicators.pnf import PnFChartBuilder

# ── Config ─────────────────────────────────────────────────────────
BOX_SIZE_PCT       = 0.15
REVERSAL           = 3
TRENDLINE_LOOKBACK = 3   # number of rising O bottoms required

# Target trades: W1=72, W2=45, W3=71, L1=34, L2=43, L3=62
TARGET_TRADES = {
    72: "W1",
    45: "W2",
    71: "W3",
    34: "L1",
    43: "L2",
    62: "L3",
}

# ── Load and aggregate data ────────────────────────────────────────
print("Loading data...")
df = pd.read_csv('data/btc_1m_delta.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
df = df.set_index('timestamp').sort_index()
df = df[df.index >= '2025-06-10']

df_1h = df['close'].resample('1h').ohlc()
df_1h.columns = ['open', 'high', 'low', 'close']
df_1h = df_1h.dropna()
print(f"1H candles: {len(df_1h)}")

# ── Build PnF columns ──────────────────────────────────────────────
builder = PnFChartBuilder(box_size_percent=BOX_SIZE_PCT, reverse_boxes=REVERSAL)
columns = builder.build_pnf_chart(df_1h)
print(f"Total PnF columns: {len(columns)}\n")

# ── Load trade log ─────────────────────────────────────────────────
files = glob.glob('output/trade_log_*Test*.csv')
if not files:
    files = glob.glob('output/trade_log_*.csv')
trade_file = sorted(files)[-1]
trades = pd.read_csv(trade_file)
trades['entry_datetime'] = pd.to_datetime(trades['entry_datetime'])

# ── Find PnF column index at or before entry timestamp ─────────────
def find_col_idx(entry_ts):
    best = None
    for i, col in enumerate(columns):
        if col['end_timestamp'] <= entry_ts:
            best = i
    return best

# ── Collect all O column indices up to (not including) current ─────
def get_o_cols_before(col_idx):
    return [(i, columns[i]) for i in range(col_idx) if columns[i]['type'] == 'O']

# ── Build strict rising O anchor sequence ending before col_idx ────
# Scans backward from col_idx-1, collects O bottoms that are
# strictly ascending (each earlier O must be lower than the next).
# Returns the longest valid rising sequence found.
def get_rising_anchors(col_idx):
    o_cols = get_o_cols_before(col_idx)
    if len(o_cols) < 2:
        return []

    # Walk backward: find the most recent sequence of rising O bottoms
    # A rising sequence means: o[n-1].bottom < o[n].bottom < o[n+1].bottom
    # We scan right-to-left and collect while each prior O is lower
    sequence = []
    for i, col in reversed(o_cols):
        level = col['end_level']
        if not sequence:
            sequence.append((i, level, col['end_timestamp']))
        else:
            if level < sequence[-1][1]:
                sequence.append((i, level, col['end_timestamp']))
            else:
                # Rising sequence broken — stop here
                break

    sequence.reverse()  # now chronological order: oldest first
    return sequence

# ── Project trendline value at a given column index ───────────────
def project_trendline(anchors, target_col_idx):
    if len(anchors) < 2:
        return None
    x1, y1, _ = anchors[0]
    x2, y2, _ = anchors[-1]
    if x2 == x1:
        return None
    slope = (y2 - y1) / (x2 - x1)
    return round(y1 + slope * (target_col_idx - x1), 2)

# ── Find Double Bottom: previous O bottom before col_idx ──────────
def find_double_bottom(col_idx):
    current_col = columns[col_idx]
    if current_col['type'] != 'O':
        return None, None

    current_bottom = current_col['end_level']
    box_size       = current_bottom * (BOX_SIZE_PCT / 100.0)

    # Find the most recent prior O column
    prev_o = None
    for i in range(col_idx - 1, -1, -1):
        if columns[i]['type'] == 'O':
            prev_o = (i, columns[i])
            break

    if prev_o is None:
        return None, None

    prev_idx, prev_col = prev_o
    prev_bottom = prev_col['end_level']

    # Double Bottom fires when current bottom <= prev bottom - 1 box
    db_triggered = current_bottom <= (prev_bottom - box_size)

    return {
        'prev_o_idx'    : prev_idx,
        'prev_o_bottom' : round(prev_bottom, 2),
        'prev_o_time'   : prev_col['end_timestamp'],
        'curr_o_bottom' : round(current_bottom, 2),
        'box_size'      : round(box_size, 2),
        'threshold'     : round(prev_bottom - box_size, 2),
        'db_triggered'  : db_triggered,
    }, prev_idx

# ── Main trace loop ────────────────────────────────────────────────
subset = trades[trades['trade_number'].isin(TARGET_TRADES.keys())].copy()

for _, row in subset.iterrows():
    trade_num  = row['trade_number']
    label      = TARGET_TRADES[trade_num]
    entry_ts   = row['entry_datetime']
    entry_px   = row['entry_price']
    exit_px    = row['exit_price']
    exit_type  = row['exit_type']

    col_idx = find_col_idx(entry_ts)
    if col_idx is None:
        print(f"[{label} Trade {trade_num}] ERROR: no column found before {entry_ts}")
        continue

    entry_col = columns[col_idx]

    print("=" * 70)
    print(f"  {label} | Trade {trade_num} | Entry {entry_ts} @ {entry_px} | Exit {exit_px} ({exit_type})")
    print("=" * 70)

    # ── Entry column ──────────────────────────────────────────────
    print(f"\n  ENTRY COLUMN (col_idx={col_idx})")
    print(f"    type       : {entry_col['type']}")
    print(f"    start_level: {round(entry_col['start_level'], 2)}")
    print(f"    end_level  : {round(entry_col['end_level'], 2)}")
    print(f"    start_time : {entry_col['start_timestamp']}")
    print(f"    end_time   : {entry_col['end_timestamp']}")

    # ── Rising O anchors ──────────────────────────────────────────
    anchors = get_rising_anchors(col_idx)
    print(f"\n  RISING O ANCHORS (found {len(anchors)})")
    if anchors:
        for rank, (ai, alevel, ats) in enumerate(anchors):
            print(f"    anchor[{rank}]: col_idx={ai:4d} | bottom={round(alevel,2):>10.2f} | time={ats}")
    else:
        print("    NONE — no rising O sequence found before entry column")

    # ── Trendline projection ──────────────────────────────────────
    projected = None
    if len(anchors) >= 2:
        projected = project_trendline(anchors, col_idx)
        tl_break  = (entry_col['type'] == 'O') and (entry_col['end_level'] < projected)
        print(f"\n  TRENDLINE PROJECTION (first anchor → last anchor → entry col)")
        print(f"    anchor_first : col_idx={anchors[0][0]} | bottom={round(anchors[0][1],2)}")
        print(f"    anchor_last  : col_idx={anchors[-1][0]} | bottom={round(anchors[-1][1],2)}")
        print(f"    projected_at_entry_col : {projected}")
        print(f"    entry_col end_level    : {round(entry_col['end_level'],2)}")
        print(f"    TRENDLINE BREAK        : {tl_break}")
    else:
        print(f"\n  TRENDLINE PROJECTION: SKIPPED (fewer than 2 anchors)")

    # ── Double Bottom ─────────────────────────────────────────────
    db_info, _ = find_double_bottom(col_idx)
    print(f"\n  DOUBLE BOTTOM CHECK")
    if db_info:
        print(f"    prev O col_idx : {db_info['prev_o_idx']}")
        print(f"    prev O bottom  : {db_info['prev_o_bottom']}")
        print(f"    prev O time    : {db_info['prev_o_time']}")
        print(f"    curr O bottom  : {db_info['curr_o_bottom']}")
        print(f"    box_size       : {db_info['box_size']}")
        print(f"    threshold      : {db_info['threshold']}  (prev_bottom - 1 box)")
        print(f"    DB TRIGGERED   : {db_info['db_triggered']}")
    else:
        print("    NONE — entry column is not an O column or no prior O found")

    # ── All O columns in lookback window (last 10 before entry) ───
    o_cols_before = get_o_cols_before(col_idx)
    recent_o = o_cols_before[-10:] if len(o_cols_before) >= 10 else o_cols_before
    print(f"\n  LAST {len(recent_o)} O COLUMNS BEFORE ENTRY (chronological)")
    print(f"    {'col_idx':>8} | {'bottom (end_level)':>20} | {'end_time'}")
    print(f"    {'-'*8}-+-{'-'*20}-+-{'-'*25}")
    for oi, ocol in recent_o:
        print(f"    {oi:>8} | {round(ocol['end_level'],2):>20.2f} | {ocol['end_timestamp']}")

    print()
