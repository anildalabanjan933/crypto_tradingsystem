import sys, os, requests, time, glob, pandas as pd
from datetime import datetime, timezone
sys.path.insert(0, '/home/anildalabanjan933/crypto_trading_system')

from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from engine.backtest_engine import BacktestEngine
from backtest_analyzer import BacktestReportGenerator

BASE     = 'https://cdn-ind.testnet.deltaex.org'
CSV_PATH = 'data/btc_1m_delta.csv'

# Auto-read VALID_FROM from last_known_ts files (updates after every restart)
def get_valid_from():
    ts_s2, ts_s4 = None, None
    if os.path.exists('logs/last_known_ts_s2.txt'):
        ts_s2 = open('logs/last_known_ts_s2.txt').read().strip()
    if os.path.exists('logs/last_known_ts_s4.txt'):
        ts_s4 = open('logs/last_known_ts_s4.txt').read().strip()
    # Use the LATER of the two (both bots must be past this point)
    if ts_s2 and ts_s4:
        return max(ts_s2, ts_s4)
    elif ts_s2:
        return ts_s2
    elif ts_s4:
        return ts_s4
    else:
        return '2026-07-12T11:00:00'  # fallback

VALID_FROM = get_valid_from()
TODAY      = datetime.now(timezone.utc).strftime('%Y-%m-%d')

def update_csv():
    df = pd.read_csv(CSV_PATH)
    last_ts = pd.Timestamp(df.iloc[-1]['Date'] + ' ' + df.iloc[-1]['Time'])
    start_ts = int(last_ts.timestamp())
    end_ts   = int(time.time())
    r = requests.get(f'{BASE}/v2/history/candles',
                     params={'symbol':'BTCUSD','resolution':'1m',
                             'start':start_ts,'end':end_ts}, timeout=10)
    candles = r.json().get('result', [])
    if candles:
        new_rows = []
        for c in candles:
            ts = pd.Timestamp(c['time'], unit='s')
            new_rows.append({'Date':ts.strftime('%Y-%m-%d'),
                             'Time':ts.strftime('%H:%M:%S'),
                             'Open':c['open'],'High':c['high'],
                             'Low':c['low'],'Close':c['close'],
                             'Volume':c['volume']})
        df2 = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        df2.drop_duplicates(subset=['Date','Time'], keep='last', inplace=True)
        df2.sort_values(['Date','Time'], inplace=True)
        df2.to_csv(CSV_PATH, index=False)
        print(f"CSV updated to {df2.iloc[-1]['Date']} {df2.iloc[-1]['Time']} ({len(candles)} new candles)")
    else:
        print(f"CSV already up to date: {last_ts}")

def get_backtest_signals(strategy_class, name, params):
    engine = BacktestEngine(
        strategy_class=strategy_class, symbol='BTCUSD',
        lot_size=100, start_date='2024-01-10', end_date=TODAY,
        csv_path=CSV_PATH, strategy_params=params, slippage=5.0
    )
    results = engine.run()
    gen = BacktestReportGenerator(
        trades=results['trades'], metrics=results['metrics'],
        strategy_name=name, symbol='BTCUSD',
        start_date='2024-01-10', end_date=TODAY,
        slippage=5.0, lot_size=100, include_charges=True
    )
    csv_path = gen.generate_csv_trade_log()
    rows = open(csv_path).readlines()
    trades = [r.strip().split(',') for r in rows[1:] if r.strip()]
    return [t for t in trades if t[3] >= VALID_FROM]

def get_live_orders(log_file):
    orders = []
    if not os.path.exists(log_file):
        return orders
    for line in open(log_file):
        if '[ORDER]' in line and ('ENTRY' in line or 'EXIT' in line):
            # Extract timestamp from log line and compare
            try:
                log_ts = line.split(' INFO')[0].strip()
                log_dt = pd.Timestamp(log_ts)
                valid_dt = pd.Timestamp(VALID_FROM)
                if log_dt >= valid_dt:
                    orders.append(line.strip())
            except:
                pass
    return orders

# ── Step 1: Update CSV ──────────────────────────────────────
print("=" * 60)
print(f"VERIFY MATCH REPORT")
print(f"Valid from : {VALID_FROM}  (auto from last_known_ts files)")
print(f"Run time   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
print("=" * 60)
print("\nSTEP 1: Updating CSV...")
update_csv()

# ── Step 2: Run backtests silently ──────────────────────────
print("\nSTEP 2: Running backtests (silent)...")
import io
from contextlib import redirect_stdout, redirect_stderr
with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
    s2_signals = get_backtest_signals(
        RenkoReversalStrategy, 'RenkoReversalStrategy',
        {'renko_timeframe':'1h','renko_box_pct':0.001,
         'st_atr_length':5,'st_factor':1.5})
    s4_signals = get_backtest_signals(
        RenkoSMIIOSupertrendStrategy, 'RenkoSMIIOSupertrendStrategy',
        {'renko_timeframe':'2h','renko_box_pct':0.001,'st_atr_length':10,
         'st_factor':2.0,'smiio_shortlen':20,'smiio_siglen':7})
print("Done.")

# ── Step 3: Get live orders ─────────────────────────────────
print("\nSTEP 3: Reading live bot orders...")
s2_orders = get_live_orders('logs/live_trading_s2.log')
s4_orders = get_live_orders('logs/live_trading_s4.log')

# ── Step 4: Compare ─────────────────────────────────────────
print("\n" + "=" * 60)
print("COMPARISON RESULT")
print("=" * 60)

all_match = True

for label, signals, orders in [("S2 RenkoReversal", s2_signals, s2_orders),
                                ("S4 RenkoSMIIO",   s4_signals, s4_orders)]:
    print(f"\n--- {label} ---")
    print(f"Backtest signals after {VALID_FROM}: {len(signals)}")
    for s in signals:
        print(f"  BT: Dir={s[5]:6s} Entry={s[3]} Exit={s[4]}")
    print(f"Live orders after {VALID_FROM}: {len(orders)}")
    for o in orders:
        print(f"  LV: {o}")

    if len(signals) == 0 and len(orders) == 0:
        print(f"  STATUS: BOTH FLAT - NO SIGNAL YET - MATCH OK")
    elif len(signals) > 0 and len(orders) == 0:
        print(f"  STATUS: MISMATCH - Backtest={len(signals)} signal(s), Live=0 orders")
        all_match = False
    elif len(signals) == 0 and len(orders) > 0:
        print(f"  STATUS: MISMATCH - Live={len(orders)} order(s), Backtest=0 signals")
        all_match = False
    else:
        if len(signals) == len(orders):
            print(f"  STATUS: TRADE COUNT MATCH - {len(signals)} trades each")
        else:
            print(f"  STATUS: COUNT MISMATCH - Backtest={len(signals)} Live={len(orders)}")
            all_match = False

print("\n" + "=" * 60)
if all_match:
    print("OVERALL: MATCH OK - system working correctly")
else:
    print("OVERALL: MISMATCH FOUND - paste this output in chat for fix")
print("=" * 60)
