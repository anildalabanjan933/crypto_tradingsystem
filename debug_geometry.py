import pandas as pd
import sys
sys.path.insert(0, '.')

from indicators.pnf import PnFChartBuilder

# ── Config ─────────────────────────────────────────────────────────
BOX_SIZE_PCT  = 0.15
REVERSAL      = 3
CSV_PATH      = 'data/btc_1m_delta.csv'
TRADE_LOG     = 'output/trade_log_PnFBearishVariant4BTest_BTCUSD_20260610_212559.csv'

# ── Load and aggregate to 1H ───────────────────────────────────────
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
builder = PnFChartBuilder(box_size_percent=BOX_SIZE_PCT, reverse_boxes=REVERSAL)
columns = builder.build_pnf_chart(df_1h)
print(f"Total PnF columns: {len(columns)}")

# ── Load trade log ─────────────────────────────────────────────────
trades = pd.read_csv(TRADE_LOG)
trades['entry_datetime'] = pd.to_datetime(trades['entry_datetime'])
print(f"Total trades: {len(trades)}")

# ── Geometry functions ─────────────────────────────────────────────
def get_rising_anchors(columns, entry_col_idx):
    o_cols_before = [
        (i, columns[i]) for i in range(entry_col_idx)
        if columns[i]['type'] == 'O'
    ]
    if not o_cols_before:
        return []
    rising = []
    for i, col in reversed(o_cols_before):
        bottom = col['end_level']
        if not rising:
            rising.insert(0, (i, col, bottom))
        else:
            next_bottom = rising[0][2]
            if bottom < next_bottom:
                rising.insert(0, (i, col, bottom))
            else:
                break
    return rising


def project_trendline(anchors, entry_col_idx):
    if len(anchors) < 2:
        return None
    x1, _, y1 = anchors[0]
    x2, _, y2 = anchors[-1]
    if x2 == x1:
        return y2
    slope = (y2 - y1) / (x2 - x1)
    return y1 + slope * (entry_col_idx - x1)


def find_entry_col(entry_ts, columns):
    # Exact match on end_timestamp
    for i, col in enumerate(columns):
        if col['type'] == 'O':
            if pd.Timestamp(col['end_timestamp']) == entry_ts:
                return i
    # Fallback: O column that contains entry_ts
    for i, col in enumerate(columns):
        if col['type'] == 'O':
            if pd.Timestamp(col['start_timestamp']) <= entry_ts <= pd.Timestamp(col['end_timestamp']):
                return i
    return None


def check_geometry(entry_ts, columns):
    idx = find_entry_col(entry_ts, columns)
    if idx is None:
        return None, None, None

    entry_bottom = columns[idx]['end_level']
    anchors = get_rising_anchors(columns, idx)
    anchor_count = len(anchors)

    if anchor_count >= 3:
        projected = project_trendline(anchors, idx)
        trendline_break = entry_bottom < projected
    else:
        projected = None
        trendline_break = False

    return anchor_count, trendline_break, projected


# ── Process all 126 trades ─────────────────────────────────────────
print("\nProcessing all trades...\n")

results = []
for _, row in trades.iterrows():
    trade_num   = row['trade_number']
    entry_ts    = row['entry_datetime']
    net_pnl     = row['net_pnl']
    is_winner   = net_pnl > 0

    anchor_count, trendline_break, projected = check_geometry(entry_ts, columns)

    results.append({
        'trade_number'    : trade_num,
        'entry_datetime'  : entry_ts,
        'net_pnl'         : net_pnl,
        'is_winner'       : is_winner,
        'anchor_count'    : anchor_count,
        'trendline_break' : trendline_break,
        'projected'       : projected,
    })

df_results = pd.DataFrame(results)

# ── Statistics ─────────────────────────────────────────────────────
winners = df_results[df_results['is_winner'] == True]
losers  = df_results[df_results['is_winner'] == False]

w_3plus  = winners[winners['anchor_count'] >= 3]
w_less3  = winners[winners['anchor_count'] < 3]
l_3plus  = losers[losers['anchor_count'] >= 3]
l_less3  = losers[losers['anchor_count'] < 3]

w_3plus_break = w_3plus[w_3plus['trendline_break'] == True]
w_3plus_nobrk = w_3plus[w_3plus['trendline_break'] == False]
l_3plus_break = l_3plus[l_3plus['trendline_break'] == True]
l_3plus_nobrk = l_3plus[l_3plus['trendline_break'] == False]

print("=" * 60)
print("GEOMETRY STATISTICS — ALL 126 TRADES")
print("=" * 60)
print(f"\nTotal trades  : {len(df_results)}")
print(f"Winners       : {len(winners)}")
print(f"Losers        : {len(losers)}")

print(f"\n--- WINNERS ({len(winners)} total) ---")
print(f"  3+ anchors              : {len(w_3plus)}")
print(f"    of which trendline BREAK : {len(w_3plus_break)}")
print(f"    of which NO break        : {len(w_3plus_nobrk)}")
print(f"  < 3 anchors             : {len(w_less3)}")

print(f"\n--- LOSERS ({len(losers)} total) ---")
print(f"  3+ anchors              : {len(l_3plus)}")
print(f"    of which trendline BREAK : {len(l_3plus_break)}")
print(f"    of which NO break        : {len(l_3plus_nobrk)}")
print(f"  < 3 anchors             : {len(l_less3)}")

print(f"\n--- TRENDLINE BREAK FILTER IMPACT ---")
would_pass  = df_results[
    (df_results['anchor_count'] >= 3) & (df_results['trendline_break'] == True)
]
would_block = df_results[
    ~((df_results['anchor_count'] >= 3) & (df_results['trendline_break'] == True))
]
wp_winners = would_pass[would_pass['is_winner'] == True]
wp_losers  = would_pass[would_pass['is_winner'] == False]
wb_winners = would_block[would_block['is_winner'] == True]
wb_losers  = would_block[would_block['is_winner'] == False]

print(f"  Trades that PASS filter : {len(would_pass)}")
print(f"    Winners               : {len(wp_winners)}")
print(f"    Losers                : {len(wp_losers)}")
if len(would_pass) > 0:
    print(f"    Win rate              : {len(wp_winners)/len(would_pass)*100:.1f}%")

print(f"  Trades BLOCKED by filter: {len(would_block)}")
print(f"    Winners blocked       : {len(wb_winners)}  <-- false negatives")
print(f"    Losers blocked        : {len(wb_losers)}  <-- correct blocks")

print("\n" + "=" * 60)
print("DETAIL — Winners with < 3 anchors (would be blocked):")
print("=" * 60)
for _, r in w_less3.iterrows():
    print(f"  Trade {int(r['trade_number']):3d} | {r['entry_datetime']} | "
          f"anchors={r['anchor_count']} | pnl={r['net_pnl']:.2f}")

print("\n" + "=" * 60)
print("DETAIL — Losers with 3+ anchors AND trendline break (would still pass):")
print("=" * 60)
for _, r in l_3plus_break.iterrows():
    print(f"  Trade {int(r['trade_number']):3d} | {r['entry_datetime']} | "
          f"anchors={r['anchor_count']} | projected={r['projected']:.2f} | pnl={r['net_pnl']:.2f}")

print("\nDone.")
