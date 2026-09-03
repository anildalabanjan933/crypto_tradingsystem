"""
check_audit_fills.py - Fetches Delta live fills for a bot/date and pairs them
using the Audit tab's own _pair_fills_audit() logic (dashboard/trade_audit_tab.py).
Read-only, diagnostic tool - does not modify any live trading files.

Usage:
    python3 scripts/check_audit_fills.py --bot s4 --date 2026-09-01
    python3 scripts/check_audit_fills.py --bot s4v2 --date 2026-09-01
"""
import sys
import os
import argparse
import hashlib
import hmac
import time
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dashboard.trade_audit_tab import _pair_fills_audit

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

BASE_URL = 'https://cdn-ind.testnet.deltaex.org'
KEY_MAP = {
    's4': ('S4_API_KEY', 'S4_API_SECRET'),
    's4v2': ('S4V2_API_KEY', 'S4V2_API_SECRET'),
    's4v3': ('S4V3_API_KEY', 'S4V3_API_SECRET'),
    'testmember1_s4': ('TESTMEMBER1_S4_API_KEY', 'TESTMEMBER1_S4_API_SECRET'),
}

def get_fills(bot, date_str):
    k, s = KEY_MAP[bot]
    api_key = os.environ.get(k)
    api_secret = os.environ.get(s)
    if not api_key or not api_secret:
        raise RuntimeError(f"Missing API credentials for bot={bot} (env vars {k}/{s})")

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
    headers = {
        'api-key': api_key,
        'timestamp': timestamp,
        'signature': signature,
        'User-Agent': 'python-rest-client',
        'Content-Type': 'application/json'
    }
    r = requests.get(url, params=query, headers=headers, timeout=(3, 27))
    r.raise_for_status()
    return r.json().get('result', [])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bot', required=True, choices=list(KEY_MAP.keys()))
    parser.add_argument('--date', required=True, help='YYYY-MM-DD (UTC)')
    args = parser.parse_args()

    print(f"\n=== {args.bot.upper()} AUDIT PAIRING ({args.date}) ===")
    fills = get_fills(args.bot, args.date)
    trades = _pair_fills_audit(fills)
    for t in trades:
        print(t)

if __name__ == '__main__':
    main()
