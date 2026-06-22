"""
Filter funnel statistics — no strategy changes.
Shows how many trades each filter removes in sequence:
1. Trendline Break (O bottoms, ascending, geometric projection)
2. + Near SMA10 OR SMA20 (3% proximity)
3. + ADX > 20
4. + Double Bottom
5. Final entries
"""

import pandas as pd
import numpy as np
import glob
import sys
sys.path.insert(0, '.')

from indicators.pnf import PnFChartBuilder
from indicators.pnf_indicators import PnFIndicators

# ── Config ─────────────────────────────────────────────────────────
BOX_SIZE_PCT       = 0.15
REVERSAL           = 3
ADX_THRESHOLD      = 20.0
SMA_PCT            = 0.03
TRENDLINE_LOOKBACK = 3
CSV_PATH           = 'data/btc_1m_delta.csv'

# ── Find trade log ─────────────────────────────────────────────────
files = glob.glob('output/trade_log_*Test*.csv')
if not files:
    files = glob.glob('output/trade_log_*.csv')
TRADE_LOG = sorted(files)[-1]
print(f"Using trade log: {TRADE_LOG}")

# ── Load 1M data and aggregate to 1H ──────────────────────────────
print("Loading data...")
df = pd.read_csv(CSV_PATH)
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
df = df.set_index('timestamp').sort_index()
df = df[df.index >= '2025-06-10']
df_1h = df['close'].resample('1h').ohlc()
df_1h.columns = ['open', 'high', 'low', 'close']
df_1h = df_1h.dropna()
print(f"1H candles: {len(df_1h)}")

# ── Build PnF columns ──────────────────────────────────────────────
print("Building PnF columns...")
builder    = PnFChartBuilder(box_size_percent=BOX_SIZE_PCT, reverse_boxes=REVERSAL)
columns    = builder.build_pnf_chart(df_1h)
indicators = PnFIndicators(box_size_percent=BOX_SIZE_PCT)
print(f"Total PnF columns: {len(columns)}")

# ── Load trade log ─────────────────────────────────────────────────
trades = pd.read_csv(TRADE_LOG)
trades['entry_datetime'] = pd.to_datetime(trades['entry_datetime'])
print(f"Total trades in log: {len(trades)}\n")

# ── Pre-compute indicators on all columns ──────────────────────────
sma10_list = builder.calculate_sma(10)
sma20_list = builder.calculate_sma(20)
adx_list   = builder.calculate_adx(14)

# ── Trendline helpers ──────────────────────────────────────────────
def get_rising_o_anchors(columns, col_idx, lookback=3):
    """
    Walk backwards from col_idx-1.
    Collect O column end_levels in a strictly rising sequence
    (each earlier O bottom must be lower than the next).
    Stop when sequence breaks.
    Return list of (col_idx, end_level) tuples, oldest first.
    Minimum required: lookback anchors.
    """
    o_cols_before = [
        (i, columns[i]) for i in range(col_idx)
        if columns[i]['type'] == 'O'
    ]
    if len(o_cols_before) < lookback:
        return []

    rising = []
    for i, c in reversed(o_cols_before):
        bottom = c['end_level']
        if len(rising) == 0:
            rising.insert(0, (i, bottom))
        elif bottom < rising[0][1]:
            rising.insert(0, (i, bottom))
        else:
            break

    if len(rising) < lookback:
        return []
    return rising


def project_trendline(anchors, target_col_idx):
    """
    Two-point line from first anchor to last anchor.
    Project to target_col_idx.
    """
    x1, y1 = anchors[0][0],  anchors[0][1]
    x2, y2 = anchors[-1][0], anchors[-1][1]
    if x2 == x1:
        return None
    slope = (y2 - y1) / (x2 - x1)
    return y1 + slope * (target_col_idx - x1)


def check_trendline_break(columns, col_idx, lookback=3):
    """
    Returns True if current O column end_level < projected trendline value.
    Requires minimum lookback rising O bottoms before this column.
    """
    anchors = get_rising_o_anchors(columns, col_idx, lookback)
    if not anchors:
        return False
    projected = project_trendline(anchors, col_idx)
    if projected is None:
        return False
    entry_bottom = columns[col_idx]['end_level']
    return entry_bottom < projected


# ── Scan all O columns — count at each filter stage ───────────────
total_o_cols       = 0
pass_trendline     = 0
pass_sma           = 0
pass_adx           = 0
pass_double_bottom = 0

for col_idx in range(len(columns)):
    col   = columns[col_idx]
    sma10 = sma10_list[col_idx]
    sma20 = sma20_list[col_idx]
    adx   = adx_list[col_idx]

    if col['type'] != 'O':
        continue
    if sma10 is None or sma20 is None or adx is None:
        continue

    total_o_cols += 1
    price = col['end_level']

    # ── Filter 1: Trendline Break ──────────────────────────────────
    if not check_trendline_break(columns, col_idx, TRENDLINE_LOOKBACK):
        continue
    pass_trendline += 1

    # ── Filter 2: Near SMA10 OR SMA20 ─────────────────────────────
    near_sma10 = abs(price - sma10) / sma10 <= SMA_PCT
    near_sma20 = abs(price - sma20) / sma20 <= SMA_PCT
    if not (near_sma10 or near_sma20):
        continue
    pass_sma += 1

    # ── Filter 3: ADX > 20 ────────────────────────────────────────
    if adx <= ADX_THRESHOLD:
        continue
    pass_adx += 1

    # ── Filter 4: Double Bottom ────────────────────────────────────
    cols_slice = columns[:col_idx + 1]
    db_found, _ = builder.detect_double_bottom(cols_slice)
    if not db_found:
        continue
    pass_double_bottom += 1

# ── Print results ──────────────────────────────────────────────────
print("=" * 58)
print("FILTER FUNNEL — ALL O COLUMNS (1-YEAR BACKTEST)")
print("=" * 58)
print(f"{'Stage':<46} {'Count':>6}  {'Removed':>8}")
print("-" * 58)

removed_1 = total_o_cols - pass_trendline
removed_2 = pass_trendline - pass_sma
removed_3 = pass_sma - pass_adx
removed_4 = pass_adx - pass_double_bottom

print(f"{'1. Total O columns scanned':<46} {total_o_cols:>6}  {'—':>8}")
print(f"{'2. Pass Trendline Break':<46} {pass_trendline:>6}  {removed_1:>8}")
print(f"{'3. Pass Trendline + Near SMA':<46} {pass_sma:>6}  {removed_2:>8}")
print(f"{'4. Pass Trendline + Near SMA + ADX>20':<46} {pass_adx:>6}  {removed_3:>8}")
print(f"{'5. Pass all 4 (+ Double Bottom)':<46} {pass_double_bottom:>6}  {removed_4:>8}")
print("-" * 58)
print(f"{'Actual entries in trade log':<46} {len(trades):>6}  {'—':>8}")
print("=" * 58)
print()
print("Note: Actual entries may differ from pass_double_bottom")
print("due to cycle state (FIRST_ENTRY / RE_ENTRY) and")
print("Supertrend entry filter (disabled in Test version).")
