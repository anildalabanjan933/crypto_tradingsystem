import sys, os, requests, time, pandas as pd, re
from datetime import datetime, timezone, timedelta
sys.path.insert(0, '/home/anildalabanjan933/crypto_trading_system')

from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from engine.backtest_engine import BacktestEngine
from backtest_analyzer import BacktestReportGenerator


def _csv_lock_write(filepath, df):
    """Write CSV with file lock - prevents race condition corruption."""
    import fcntl, tempfile, os
    lock_path = filepath + '.lock'
    with open(lock_path, 'w') as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            # Write to temp file first then rename - atomic operation
            tmp_path = filepath + '.tmp'
            df.to_csv(tmp_path, index=False)
            os.replace(tmp_path, filepath)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

BASE     = 'https://cdn-ind.testnet.deltaex.org'
CSV_PATH = 'data/btc_1m_delta.csv'

def get_valid_from():
    # BASELINE FILE = single truth, never overwritten by bot orders
    # Only updated manually when new clean baseline is set
    baseline_file = 'logs/valid_from_baseline.txt'
    if os.path.exists(baseline_file):
        val = open(baseline_file).read().strip()
        import re as _re
        if _re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$', val):
            return val
    # Fallback: use max of ts files (most recent clean order)
    ts_s2, ts_s4 = None, None
    if os.path.exists('logs/last_known_ts_s2.txt'):
        ts_s2 = open('logs/last_known_ts_s2.txt').read().strip()
    if os.path.exists('logs/last_known_ts_s4.txt'):
        ts_s4 = open('logs/last_known_ts_s4.txt').read().strip()
    if ts_s2 and ts_s4: return max(ts_s2, ts_s4)
    elif ts_s2: return ts_s2
    elif ts_s4: return ts_s4
    else: return '2026-07-14T09:00:00'

VALID_FROM = get_valid_from()
TODAY      = (datetime.now(timezone.utc) + __import__('datetime').timedelta(days=1)).strftime('%Y-%m-%d')

def update_csv():
    # Direct import - never fails silently unlike subprocess
    import sys as _sys
    _data_path = '/home/anildalabanjan933/crypto_trading_system/data'
    if _data_path not in _sys.path:
        _sys.path.insert(0, _data_path)
    try:
        from download_market_data import download_or_update
        download_or_update('BTC')
    except Exception as _e:
        print(f"CSV update warning: {_e}")


def get_backtest_signals(strategy_class, name, params):
    # Read directly from signal CSV - faster and guaranteed match
    # S2 = logs/signals_s2.csv | S4 = logs/signals_s4.csv
    if 'Reversal' in name or 's2' in name.lower():
        sig_csv = 'logs/signals_s2.csv'
    else:
        sig_csv = 'logs/signals_s4.csv'

    trades = []
    if not os.path.exists(sig_csv):
        print(f"  WARNING: Signal CSV not found: {sig_csv}")
        return trades

    import csv as _csv
    with open(sig_csv) as fh:
        reader = _csv.DictReader(fh)
        for row in reader:
            entry_time = row['entry_time'].strip()
            exit_time  = row['exit_time'].strip()
            direction  = row['direction'].strip()
            if entry_time < VALID_FROM:
                continue
            # Build trade row compatible with existing comparison logic
            # t[3]=entry_time t[4]=exit_time t[5]=direction
            trade = [''] * 31
            trade[3] = entry_time
            trade[4] = exit_time
            trade[5] = direction
            trades.append(trade)

    # Check if last signal is open (exit_time in future = still open)
    from datetime import timezone
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    if trades and trades[-1][4] > now_str:
        trades[-1][4] = ''  # mark as open - exit not yet reached

    return trades


def get_live_trades(log_file):
    # Parse ENTRY and EXIT pairs from log
    entries = {}  # direction -> entry_time
    trades  = []
    pending_entry = {}
    if not os.path.exists(log_file):
        return trades
    lines_list = open(log_file).readlines()
    for i, line in enumerate(lines_list):
        try:
            log_ts = pd.Timestamp(line.split(' INFO')[0].strip())
            if log_ts < pd.Timestamp(VALID_FROM):
                continue
        except:
            continue

        if '[ORDER]' not in line:
            continue

        # Parse ENTRY - only confirmed orders
        if 'ENTRY' in line and 'FAILED' in line:
            continue
        entry_attempt = re.search(
            r'ENTRY\s+(buy|sell)\s+\d+\s+lots.*ts=(\S+)', line, re.I)
        if entry_attempt:
            side = entry_attempt.group(1).lower()
            signal_ts = entry_attempt.group(2).rstrip('|').strip()
            dir_match = re.search(r'dir=(long|short)', line, re.I)
            direction = dir_match.group(1).lower() if dir_match else ('long' if side == 'buy' else 'short')
            # Check next 5 lines for FAILED - if so skip this entry
            failed = False
            for j in range(1, 6):
                next_line = lines_list[i+j] if i+j < len(lines_list) else ''
                if 'ENTRY FAILED' in next_line or 'invalid_api_key' in next_line:
                    failed = True
                    break
                if '[ORDER]' in next_line:
                    break
            if failed:
                continue
            pending_entry[signal_ts] = {'direction': direction, 'entry_time': signal_ts,
                                   'entry_price': '-'}
            continue

        # Confirm ENTRY - move pending to entries on confirmed line
        if '[ORDER] ENTRY confirmed' in line:
            for sig_ts, entry_data in list(pending_entry.items()):
                entries[sig_ts] = entry_data
                del pending_entry[sig_ts]
            continue

        # Parse EXIT
        # Actual log format: [ORDER] EXIT sell 100 lots | type=ST_FLIP_RED | ts=2026-07-12T18:00:00
        exit_match = re.search(
            r'EXIT\s+(sell|buy)\s+\d+\s+lots.*ts=(\S+)', line, re.I)
        if exit_match:
            signal_ts = exit_match.group(2).rstrip('|').strip()
            price = '-'
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

    if len(bt_signals) == 0 and len(lv_trades) >= 1:
        lv = lv_trades[0]
        if lv.get('status') == 'OPEN':
            try:
                entry_dt = datetime.fromisoformat(lv['entry_time'])
                age_mins = (datetime.now(timezone.utc) - entry_dt.replace(tzinfo=timezone.utc)).total_seconds() / 60
                if age_mins <= 30:
                    print(f"\n  Trade #1:")
                    print(f"    BT : Dir=PENDING  Entry=PENDING  Exit=PENDING")
                    print(f"    LV : Dir={lv['direction']:6s}  Entry={lv['entry_time']}  Exit=(open)")
                    print(f"    Direction  : PENDING")
                    print(f"    Entry time : PENDING")
                    print(f"    Exit time  : PENDING (trade still open)")
                    print(f"    STATUS     : PENDING (backtest CSV catching up - {age_mins:.0f}m since entry)")
                    print(f"\n  SUMMARY: 0 FULL MATCH | 1 PENDING | 0 MISMATCH")
                    return True
            except:
                pass

    full_match  = 0
    mismatch    = 0
    pending     = 0

    # Match trades by entry timestamp not by position number
    # Build lookup of backtest trades by entry timestamp
    bt_by_entry = {}
    for bt in bt_signals:
        bt_by_entry[bt[3]] = bt  # bt[3] = entry_datetime

    # Also build list of all unique timestamps from both
    all_entries = sorted(set(
        [bt[3] for bt in bt_signals] +
        [lv['entry_time'] for lv in lv_trades]
    ))

    trade_num = 0
    for entry_ts in all_entries:
        bt = bt_by_entry.get(entry_ts)
        lv_list = [lv for lv in lv_trades if lv['entry_time'] == entry_ts]
        lv = lv_list[0] if lv_list else None

        # Skip if both missing (should not happen)
        if not bt and not lv:
            continue

        trade_num += 1
        i = trade_num - 1
        print(f"\n  Trade #{trade_num}:")

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
            # Live has trade but backtest does not
            # If live trade is currently OPEN = backtest will catch up when it closes
            # If live trade is CLOSED = real mismatch
            if lv_stat == 'OPEN':
                print(f"    Exit time  : PENDING (current open trade - backtest will match when closed)")
                print(f"    STATUS     : PENDING")
                pending += 1
            else:
                print(f"    Exit time  : EXTRA LIVE ORDER - not in backtest")
                print(f"    STATUS     : MISMATCH")
                mismatch += 1
        elif not lv:
            # Backtest has trade but live does not
            # If backtest trade is the last open (unclosed) = live bot has moved ahead
            # Check if live bot has a newer trade = backtest just behind
            if bt_exit == '' or bt_exit is None or str(bt_exit).strip() == '':
                print(f"    Exit time  : PENDING (backtest open trade - live bot ahead)")
                print(f"    STATUS     : PENDING")
                pending += 1
            else:
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

print("\nSTEP 2: Reading signal CSVs...")
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
