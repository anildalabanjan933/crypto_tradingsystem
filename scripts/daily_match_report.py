import sys, os, re
sys.path.insert(0, '.')
from datetime import datetime, timezone
import csv

# Read VALID_FROM baseline
_baseline_file = 'logs/valid_from_baseline.txt'
today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
VALID_FROM = open(_baseline_file).read().strip() if os.path.exists(_baseline_file) else today + 'T00:00:00'

print("=" * 70)
print(f"DAILY MATCH REPORT - {today} UTC")
print(f"Valid from : {VALID_FROM}")
print("=" * 70)

# Read backtest signals directly from signal CSV
def get_bt_signals(sig_csv):
    trades = {}
    if not os.path.exists(sig_csv):
        print(f"  WARNING: Signal CSV not found: {sig_csv}")
        return trades
    with open(sig_csv) as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            entry_time = row['entry_time'].strip()
            exit_time  = row['exit_time'].strip()
            direction  = row['direction'].strip()
            if entry_time < VALID_FROM:
                continue
            trades[entry_time] = {
                'entry_datetime': entry_time,
                'exit_datetime':  exit_time,
                'direction':      direction
            }
    return trades

# Get live trades from log
def parse_live(logfile):
    pairs, cur = [], None
    if not os.path.exists(logfile):
        return pairs
    for ln in open(logfile):
        if '[ORDER]' not in ln:
            continue
        ts_match = re.search(r'ts=(\S+)', ln)
        if not ts_match:
            continue
        ts = ts_match.group(1).rstrip('|').strip()
        if ts < VALID_FROM:
            continue
        if 'ENTRY' in ln:
            dir_match = re.search(r'dir=(long|short)', ln, re.I)
            if dir_match:
                direction = dir_match.group(1).lower()
            else:
                direction = 'long' if 'buy' in ln.lower() else 'short'
            cur = {'entry': ts, 'dir': direction, 'exit': None}
        elif 'EXIT' in ln and cur:
            cur['exit'] = ts
            pairs.append(cur)
            cur = None
    if cur:
        pairs.append(cur)
    return pairs

def show_report(label, bt_dict, lv_list):
    print(f"\n{'='*70}")
    print(f"{label}")
    print(f"{'='*70}")
    print(f"{'#':<3} {'ENTRY':<22} {'LV EXIT':<22} {'LV DIR':<7} {'BT EXIT':<22} {'BT DIR':<7} {'STATUS':<8} DEBUG")

    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    all_entries = sorted(set(list(bt_dict.keys()) + [lv['entry'] for lv in lv_list]))
    matches = mismatches = pending = 0

    for i, entry_ts in enumerate(all_entries):
        bt = bt_dict.get(entry_ts)
        lv_match = [lv for lv in lv_list if lv['entry'] == entry_ts]
        lv = lv_match[0] if lv_match else None

        bt_exit = bt['exit_datetime'] if bt else 'MISSING'
        bt_dir  = bt['direction']     if bt else 'MISSING'
        lv_exit = lv['exit'] or 'OPEN' if lv else 'MISSING'
        lv_dir  = lv['dir']           if lv else 'MISSING'

        # PENDING if bt exit is in future (signal not due yet)
        if bt and bt_exit > now_str and (not lv or not lv['exit']):
            status = 'PENDING'
            debug  = 'Exit time not reached yet - check after ' + bt_exit
            pending += 1
        elif lv_exit == 'OPEN':
            status = 'PENDING'
            debug  = 'Trade still open - check on exit'
            pending += 1
        elif not bt:
            status = 'EXTRA'
            debug  = 'Live fired signal not in backtest - check UTC/data source'
            mismatches += 1
        elif not lv:
            status = 'MISSING'
            debug  = 'Backtest has trade but live did not fire - check position state'
            mismatches += 1
        elif bt_exit == lv_exit and bt_dir == lv_dir:
            status = 'MATCH'
            debug  = 'OK'
            matches += 1
        else:
            debug_parts = []
            if bt_dir != lv_dir:
                debug_parts.append(f'DIR: BT={bt_dir} LV={lv_dir}')
            if bt_exit != lv_exit:
                debug_parts.append(f'EXIT: BT={bt_exit} LV={lv_exit}')
            status = 'MISMATCH'
            debug  = ' | '.join(debug_parts)
            mismatches += 1

        print(f"{i+1:<3} {entry_ts:<22} {lv_exit:<22} {lv_dir:<7} {bt_exit:<22} {bt_dir:<7} {status:<8} {debug}")

    print(f"\nSUMMARY: {matches} MATCH | {pending} PENDING | {mismatches} MISMATCH")
    if mismatches == 0 and pending == 0 and matches == 0:
        print("RESULT: NO TRADES YET - waiting for first signal after VALID_FROM")
    elif mismatches == 0 and pending == 0:
        print("RESULT: FULL MATCH - all closed trades match backtest exactly")
    elif mismatches == 0:
        print("RESULT: ENTRY MATCH - waiting for open trades to close")
    else:
        print("RESULT: MISMATCH FOUND - see DEBUG column for exact reason")

bt2 = get_bt_signals('logs/signals_s2.csv')
bt4 = get_bt_signals('logs/signals_s4.csv')
lv2 = parse_live('logs/live_trading_s2.log')
lv4 = parse_live('logs/live_trading_s4.log')

show_report("S2 RenkoReversal - TRADES FROM VALID_FROM", bt2, lv2)
show_report("S4 RenkoSMIIO - TRADES FROM VALID_FROM", bt4, lv4)

print(f"\n{'='*70}")
print("DEBUG GUIDE:")
print("  PENDING  = exit time not reached yet or trade still open - normal")
print("  EXTRA    = live fired signal not in backtest - UTC bug or wrong data")
print("  MISSING  = backtest has trade but live did not fire - check bot state")
print("  MISMATCH = direction or exit time differs - check logs")
print("  MATCH    = perfect - no action needed")
print(f"{'='*70}")
