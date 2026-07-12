import sys, os, requests, time, pandas as pd, re
from datetime import datetime, timezone
sys.path.insert(0, '/home/anildalabanjan933/crypto_trading_system')

from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from engine.backtest_engine import BacktestEngine
from backtest_analyzer import BacktestReportGenerator

BASE     = 'https://cdn-ind.testnet.deltaex.org'
CSV_PATH = 'data/btc_1m_delta.csv'

def get_valid_from():
    ts_s2, ts_s4 = None, None
    if os.path.exists('logs/last_known_ts_s2.txt'):
        ts_s2 = open('logs/last_known_ts_s2.txt').read().strip()
    if os.path.exists('logs/last_known_ts_s4.txt'):
        ts_s4 = open('logs/last_known_ts_s4.txt').read().strip()
    if ts_s2 and ts_s4: return max(ts_s2, ts_s4)
    elif ts_s2: return ts_s2
    elif ts_s4: return ts_s4
    else: return '2026-07-12T00:00:00'

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

def get_live_trades(log_file):
    # Parse ENTRY and EXIT pairs from log
    entries = {}  # direction -> entry_time
    trades  = []
    if not os.path.exists(log_file):
        return trades
    for line in open(log_file):
        try:
            log_ts = pd.Timestamp(line.split(' INFO')[0].strip())
            if log_ts < pd.Timestamp(VALID_FROM):
                continue
        except:
            continue

        if '[ORDER]' not in line:
            continue

        # Parse ENTRY
        # Actual log format: [ORDER] ENTRY buy 100 lots | type=BUY_A | ts=2026-07-12T14:00:00
        entry_match = re.search(
            r'ENTRY\s+(buy|sell)\s+\d+\s+lots.*ts=(\S+)', line, re.I)
        if entry_match:
            side      = entry_match.group(1).lower()
            signal_ts = entry_match.group(2).rstrip('|').strip()
            direction = 'long' if side == 'buy' else 'short'
            entries[signal_ts] = {'direction': direction,
                                   'entry_time': signal_ts,
                                   'entry_price': '-'}
            continue

        # Parse EXIT
        # Actual log format: [ORDER] EXIT sell 100 lots | type=ST_FLIP_RED | ts=2026-07-12T18:00:00
        exit_match = re.search(
            r'EXIT\s+(sell|buy)\s+\d+\s+lots.*ts=(\S+)', line, re.I)
        if exit_match:
            signal_ts = exit_match.group(2).rstrip('|').strip()
            # Match to open entry
            for ets, entry in list(entries.items()):
                trades.append({
                    'direction'  : entry['direction'],
                    'entry_time' : entry['entry_time'],
                    'entry_price': entry['entry_price'],
                    'exit_time'  : signal_ts,
                    'exit_price' : price,
                    'status'     : 'CLOSED'
                })
                del entries[ets]
                break

    # Any remaining entries = still open
    for ets, entry in entries.items():
        trades.append({
            'direction'  : entry['direction'],
            'entry_time' : entry['entry_time'],
            'entry_price': entry['entry_price'],
            'exit_time'  : '(open)',
            'exit_price' : '-',
            'status'     : 'OPEN'
        })
    return trades

def compare(label, bt_signals, lv_trades):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Backtest trades : {len(bt_signals)}")
    print(f"  Live trades     : {len(lv_trades)}")

    if len(bt_signals) == 0 and len(lv_trades) == 0:
        print(f"\n  STATUS: BOTH FLAT - NO SIGNAL YET - MATCH OK")
        return True

    full_match  = 0
    mismatch    = 0
    pending     = 0
    max_trades  = max(len(bt_signals), len(lv_trades))

    for i in range(max_trades):
        print(f"\n  Trade #{i+1}:")
        bt = bt_signals[i] if i < len(bt_signals) else None
        lv = lv_trades[i]  if i < len(lv_trades)  else None

        bt_dir   = bt[5]  if bt else 'MISSING'
        bt_entry = bt[3]  if bt else 'MISSING'
        bt_exit  = bt[4]  if bt else 'MISSING'

        lv_dir   = lv['direction']   if lv else 'MISSING'
        lv_entry = lv['entry_time']  if lv else 'MISSING'
        lv_exit  = lv['exit_time']   if lv else 'MISSING'
        lv_stat  = lv['status']      if lv else 'MISSING'

        print(f"    BT : Dir={bt_dir:6s}  Entry={bt_entry}  Exit={bt_exit}")
        print(f"    LV : Dir={lv_dir:6s}  Entry={lv_entry}  Exit={lv_exit}")

        dir_match   = bt_dir.lower()   == lv_dir.lower()   if bt and lv else False
        entry_match = bt_entry         == lv_entry          if bt and lv else False
        exit_match  = bt_exit          == lv_exit           if bt and lv else False

        print(f"    Direction  : {'MATCH' if dir_match   else 'MISMATCH'}")
        print(f"    Entry time : {'MATCH' if entry_match else 'MISMATCH'}")

        if lv_stat == 'OPEN':
            print(f"    Exit time  : PENDING (trade still open)")
            if dir_match and entry_match:
                print(f"    STATUS     : ENTRY MATCH - waiting for exit")
                pending += 1
            else:
                print(f"    STATUS     : MISMATCH")
                mismatch += 1
        elif not bt:
            print(f"    Exit time  : EXTRA LIVE ORDER - not in backtest")
            print(f"    STATUS     : MISMATCH")
            mismatch += 1
        elif not lv:
            print(f"    Exit time  : MISSING LIVE ORDER")
            print(f"    STATUS     : MISMATCH")
            mismatch += 1
        else:
            print(f"    Exit time  : {'MATCH' if exit_match else 'MISMATCH'}")
            if dir_match and entry_match and exit_match:
                print(f"    STATUS     : FULL MATCH")
                full_match += 1
            else:
                print(f"    STATUS     : MISMATCH")
                mismatch += 1

    print(f"\n  SUMMARY: {full_match} FULL MATCH | {pending} PENDING | {mismatch} MISMATCH")
    return mismatch == 0

# ── MAIN ────────────────────────────────────────────────────
print("=" * 60)
print("VERIFY MATCH REPORT")
print(f"Valid from : {VALID_FROM}  (auto from last_known_ts files)")
print(f"Run time   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
print("=" * 60)

print("\nSTEP 1: Updating CSV...")
update_csv()

print("\nSTEP 2: Running backtests (silent)...")
import io
from contextlib import redirect_stdout, redirect_stderr
with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
    s2_bt = get_backtest_signals(
        RenkoReversalStrategy, 'RenkoReversalStrategy',
        {'renko_timeframe':'1h','renko_box_pct':0.001,
         'st_atr_length':5,'st_factor':1.5})
    s4_bt = get_backtest_signals(
        RenkoSMIIOSupertrendStrategy, 'RenkoSMIIOSupertrendStrategy',
        {'renko_timeframe':'2h','renko_box_pct':0.001,'st_atr_length':10,
         'st_factor':2.0,'smiio_shortlen':20,'smiio_siglen':7})
print("Done.")

print("\nSTEP 3: Reading live bot orders...")
s2_lv = get_live_trades('logs/live_trading_s2.log')
s4_lv = get_live_trades('logs/live_trading_s4.log')

s2_ok = compare("S2 RenkoReversal",  s2_bt, s2_lv)
s4_ok = compare("S4 RenkoSMIIO",     s4_bt, s4_lv)

print(f"\n{'='*60}")
if s2_ok and s4_ok:
    print("OVERALL: MATCH OK - system working correctly")
else:
    print("OVERALL: MISMATCH FOUND - paste this output in chat for fix")
print("=" * 60)
