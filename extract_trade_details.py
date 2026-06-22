import pandas as pd
import glob
import sys
sys.path.insert(0, '.')

from indicators.pnf import PnFChartBuilder

# ── Config ─────────────────────────────────────────────────────────
BOX_SIZE_PCT = 0.15
REVERSAL     = 3

# Trades to extract: 3 winners + 3 losers
# Winners: 45 (Nov), 71 (Feb03), 72 (Feb04)
# Losers:  43 (Nov07), 62 (Jan21), 34 (Oct30)
TARGET_TRADES = [45, 71, 72, 43, 62, 34]

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
print("Building PnF columns...")
builder = PnFChartBuilder(box_size_percent=BOX_SIZE_PCT, reverse_boxes=REVERSAL)
columns = builder.build_pnf_chart(df_1h)
print(f"Total PnF columns: {len(columns)}")

# ── Compute indicators ─────────────────────────────────────────────
sma10 = builder.calculate_sma(10)
sma20 = builder.calculate_sma(20)
adx   = builder.calculate_adx(14)

# ── Load trade log (Test version with 126 trades) ──────────────────
files = glob.glob('output/trade_log_*Test*.csv')
if not files:
    files = glob.glob('output/trade_log_*.csv')
trade_file = sorted(files)[-1]
trades = pd.read_csv(trade_file)
trades['entry_datetime'] = pd.to_datetime(trades['entry_datetime'])
print(f"Trade log: {trade_file}")
print(f"Total trades in log: {len(trades)}\n")

# ── Find PnF column index for a given timestamp ────────────────────
def find_col_idx(entry_ts):
    best = None
    for i, col in enumerate(columns):
        if col['end_timestamp'] <= entry_ts:
            best = i
    return best

# ── Extract and print ──────────────────────────────────────────────
subset = trades[trades['trade_number'].isin(TARGET_TRADES)].copy()

if subset.empty:
    print("ERROR: No matching trades found. Check TARGET_TRADES list.")
    print("Available trade numbers:", trades['trade_number'].tolist())
    sys.exit(1)

print("=" * 100)
print(f"{'Trade':>6} | {'Entry Time':>20} | {'Entry':>10} | {'Exit':>10} | {'Exit Type':>22} | {'SMA10':>9} | {'SMA20':>9} | {'ADX':>7} | {'PnL INR':>12}")
print("-" * 100)

for _, row in subset.iterrows():
    idx = find_col_idx(row['entry_datetime'])

    s10 = None
    s20 = None
    ax  = None

    if idx is not None:
        if idx < len(sma10) and sma10[idx]:
            s10 = round(sma10[idx], 1)
        if idx < len(sma20) and sma20[idx]:
            s20 = round(sma20[idx], 1)
        if idx < len(adx) and adx[idx]:
            ax  = round(adx[idx], 2)

    print(
        f"{row['trade_number']:>6} | "
        f"{str(row['entry_datetime']):>20} | "
        f"{row['entry_price']:>10.1f} | "
        f"{row['exit_price']:>10.1f} | "
        f"{row['exit_type']:>22} | "
        f"{str(s10) if s10 else 'N/A':>9} | "
        f"{str(s20) if s20 else 'N/A':>9} | "
        f"{str(ax)  if ax  else 'N/A':>7} | "
        f"{row['net_pnl_inr']:>12.2f}"
    )

print("=" * 100)
