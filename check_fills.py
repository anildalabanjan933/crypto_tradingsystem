import hashlib
import hmac
import requests
import time
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--bot', default='s4', choices=['s4', 's4v2', 's4v3', 'testmember1_s4'])
parser.add_argument('--date', default=None, help='YYYY-MM-DD (UTC)')
args = parser.parse_args()

BOT_KEY_MAP = {
    's4': ('S4_API_KEY', 'S4_API_SECRET'),
    's4v2': ('S4V2_API_KEY', 'S4V2_API_SECRET'),
    's4v3': ('S4V3_API_KEY', 'S4V3_API_SECRET'),
    'testmember1_s4': ('TESTMEMBER1_S4_API_KEY', 'TESTMEMBER1_S4_API_SECRET'),
}
_key_env, _secret_env = BOT_KEY_MAP[args.bot]

base_url = 'https://cdn-ind.testnet.deltaex.org'
api_key = os.environ.get(_key_env)
api_secret = os.environ.get(_secret_env)

def generate_signature(secret, message):
    message = bytes(message, 'utf-8')
    secret = bytes(secret, 'utf-8')
    hash = hmac.new(secret, message, hashlib.sha256)
    return hash.hexdigest()

if args.date:
    _y, _m, _d = map(int, args.date.split('-'))
    start_dt = datetime(_y, _m, _d, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(_y, _m, _d, 23, 59, 59, tzinfo=timezone.utc)
else:
    start_dt = datetime(2026, 9, 2, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(2026, 9, 3, 23, 59, 59, tzinfo=timezone.utc)
start_us = int(start_dt.timestamp() * 1_000_000)
end_us = int(end_dt.timestamp() * 1_000_000)

method = 'GET'
timestamp = str(int(time.time()))
path = '/v2/fills'
url = f'{base_url}{path}'

query = {"product_ids": 84, "start_time": start_us, "end_time": end_us}
query_string = '?' + '&'.join([f'{k}={v}' for k, v in query.items()])

payload = ''
signature_data = method + timestamp + path + query_string + payload
signature = generate_signature(api_secret, signature_data)

req_headers = {
    'api-key': api_key,
    'timestamp': timestamp,
    'signature': signature,
    'User-Agent': 'python-rest-client',
    'Content-Type': 'application/json'
}

try:
    response = requests.request(
        method, url, data=payload, params=query, timeout=(3, 27), headers=req_headers
    )
    response.raise_for_status()
    data = response.json()
    for fill in data.get('result', []):
        print(fill.get('created_at'), fill.get('side'), fill.get('size'), fill.get('price'), fill.get('order_id'))
except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")
    print(response.text if 'response' in dir() else '')
except ValueError:
    print("Failed to parse JSON response")
