"""
check_bt_vs_delta.py - Independent comparison: Backtest (BT) trade_log CSV vs
Delta live fills (paired via Audit tab logic). Prints BOTH lists separately,
no forced pairing - for manual side-by-side comparison only.

Usage:
    python3 scripts/check_bt_vs_delta.py --bot s4 --date 2026-09-01
    python3 scripts/check_bt_vs_delta.py --bot s4v2 --date 2026-09-01
"""
import sys
import os
import glob
import argparse
import hashlib
import hmac
import time
import requests
import pandas as pd
from datetime import datetime, timezone, date
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from dashboard.trade_audit_tab import _pair_fills_audit

load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, '.env'))

BASE_URL = 'https://cdn-ind.testnet.deltaex.org'
KEY_MAP = {
    's4': ('S4_API_KEY', 'S4_API_SECRET'),
    's4v2': ('S4V2_API_KEY', 'S4V2_API_SECRET'),
    's4v3': ('S4V3_API_KEY', 'S4V3_API_SECRET'),
    'testmember1_s4': ('TESTMEMBER1_S4_API_KEY', 'TESTMEMBER1_S4_API_SECRET'),
}
BT_CSV_PATTERN = {
    's4':   "output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv",
    's4v2': "output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv",
    's4v3': "output/trade_log_RenkoSMIIOCrossV3Strategy_BTCUSD_*.csv",
}

def get_delta_fills(bot, date_str):
    k, s = KEY_MAP[bot]
    api_key = os.environ.get(k)
    api_secret = os.environ.get(s)
    if not api_key or not api_secret:
        raise RuntimeError(f"Missing API credentials for bot={bot}")
    y, m, d = map(int, date_str.split('-'))
    start_dt = datetime(y, m, d, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(y, m, d, 23, 59, 59, tzinfo=timezone.utc)
    start_us = int(start_dt.timestamp() * 1_000_000)
    end_us = int(end_dt.timestamp() * 1_000_000)
    method = 'GET'
    timestamp = str(int(time.time()))
    path = '/v2/fills'
    url = f'{BASE_URL}{path}'
    query = {"product_ids": 84, "start_time": start_us, "end_time": end_us, "page_size": 100}
    query_string = '?' + '&'.join([f'{qk}={qv}' for qk, qv in query.items()])
    sig_data = method + timestamp + path + query_string + ''
    signature = hmac.new(api_secret.encode(), sig_data.encode(), hashlib.sha256).hexdigest()
    headers = {'api-key': api_key, 'timestamp': timestamp, 'signature': signature,
               'User-Agent': 'python-rest-client', 'Content-Type': 'application/json'}
    r = requests.get(url, params=query, headers=headers, timeout=(3, 27))
    r.raise_for_status()
    return r.json().get('result', [])

def get_bt_rows(bot, date_str):
    pattern = BT_CSV_PATTERN[bot]
    files = sorted(glob.glob(os.path.join(PROJECT_ROOT, pattern)), reverse=True)
    if not files:
        return []
    df = pd.read_csv(files[0])
    if 'entry_datetime' not in df.columns:
        return []
    df['entry_datetime'] = pd.to_datetime(df['entry_datetime'], errors='coerce')
    df['exit_datetime'] = pd.to_datetime(df['exit_datetime'], errors='coerce')
    y, m, d = map(int, date_str.split('-'))
    target = date(y, m, d)
    df = df[(df['entry_datetime'].dt.date == target) | (df['exit_datetime'].dt.date == target)]
    df = df.sort_values('entry_datetime')
    rows = []
    for _, r in df.iterrows():
        rows.append({
            'dir': str(r.get('direction', '')).upper(),
            'entry_ts': str(r.get('entry_datetime', '')),
            'exit_ts': str(r.get('exit_datetime', '')),
            'entry_p': float(r.get('entry_price', 0)),
            'exit_p': float(r.get('exit_price', 0)),
            'net_pnl_usd': float(r.get('net_pnl', 0)),
        })
    return rows

# ===== Additional checks: entry/exit delay + big loss flag =====
def analyze_live_trades(lv_rows, bot):
    """Adds delay_sec (vs nearest clean boundary) and big_loss flag to each live trade."""
    tf_min = 120 if bot == 's4' else 30
    if bot == 's4v3':
        tf_min = 240
    BIG_LOSS_USD = 40.0  # ~Rs4,000 backtest single-trade ceiling / ~84 INR rate

    for r in lv_rows:
        try:
            entry_dt = datetime.fromisoformat(r['entry_ts_raw'].replace('Z', '+00:00'))
            minute = entry_dt.minute
            hour = entry_dt.hour
            total_min = hour * 60 + minute
            nearest_boundary_min = round(total_min / tf_min) * tf_min
            boundary_dt = entry_dt.replace(hour=0, minute=0, second=0, microsecond=0) + \
                __import__('datetime').timedelta(minutes=nearest_boundary_min)
            delay_sec = (entry_dt - boundary_dt).total_seconds()
            r['entry_delay_sec'] = round(delay_sec, 1)
        except Exception:
            r['entry_delay_sec'] = None
        try:
            exit_dt = datetime.fromisoformat(r['exit_ts_raw'].replace('Z', '+00:00'))
            minute = exit_dt.minute
            hour = exit_dt.hour
            total_min = hour * 60 + minute
            nearest_boundary_min = round(total_min / tf_min) * tf_min
            boundary_dt = exit_dt.replace(hour=0, minute=0, second=0, microsecond=0) + \
                __import__('datetime').timedelta(minutes=nearest_boundary_min)
            exit_delay_sec = (exit_dt - boundary_dt).total_seconds()
            r['exit_delay_sec'] = round(exit_delay_sec, 1)
        except Exception:
            r['exit_delay_sec'] = None
        r['big_loss_flag'] = r.get('pnl_usd', 0) < -BIG_LOSS_USD
    return lv_rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bot', required=True, choices=list(KEY_MAP.keys()))
    parser.add_argument('--date', required=True, help='YYYY-MM-DD (UTC)')
    args = parser.parse_args()

    print(f"\n========== BT (BACKTEST) TRADES - {args.bot.upper()} - {args.date} ==========")
    bt_rows = get_bt_rows(args.bot, args.date)
    if not bt_rows:
        print("No BT rows found for this date.")
    for i, r in enumerate(bt_rows, 1):
        print(f"{i}. {r['dir']} | entry={r['entry_ts']} @ {r['entry_p']} | exit={r['exit_ts']} @ {r['exit_p']} | net_pnl=${r['net_pnl_usd']:.2f}")
    print(f"BT TOTAL TRADES: {len(bt_rows)}")

    print(f"\n========== DELTA LIVE FILLS (via Audit pairing) - {args.bot.upper()} - {args.date} ==========")
    fills = get_delta_fills(args.bot, args.date)
    lv_rows = _pair_fills_audit(fills)
    lv_rows = analyze_live_trades(lv_rows, args.bot)
    if not lv_rows:
        print("No live trades found for this date.")
    for i, r in enumerate(lv_rows, 1):
        _edelay = r.get('entry_delay_sec')
        _edelay_str = f"{_edelay}s" if _edelay is not None else "N/A"
        _xdelay = r.get('exit_delay_sec')
        _xdelay_str = f"{_xdelay}s" if _xdelay is not None else "N/A"
        _loss_flag = "  !! BIG LOSS !!" if r.get('big_loss_flag') else ""
        print(f"{i}. {r['dir']} | entry={r['entry_ts_raw']} @ {r['entry_p']} (entry_delay={_edelay_str}) | exit={r['exit_ts_raw']} @ {r['exit_p']} (exit_delay={_xdelay_str}) | pnl=${r['pnl_usd']:.2f}{_loss_flag}")
    print(f"LIVE TOTAL TRADES: {len(lv_rows)}")

    print(f"\n========== SUMMARY (manual compare - no auto-pairing) ==========")
    print(f"BT trade count:   {len(bt_rows)}")
    print(f"LIVE trade count: {len(lv_rows)}")
    if len(bt_rows) != len(lv_rows):
        print("!! COUNT MISMATCH - review both lists above manually !!")
    else:
        print("Counts match - review prices/times/pnl above manually for slippage/delay.")

if __name__ == '__main__':
    main()
