import sys, os, json, hashlib, hmac, time, requests
from scripts.cts_env import PRODUCT_ID as _CTS_PRODUCT_ID
sys.path.insert(0, os.getcwd())

from dashboard.trade_audit_tab import _merge_partial_fills_audit, _pair_fills_audit

base_url = 'https://cdn-ind.testnet.deltaex.org'
PRODUCT_ID = _CTS_PRODUCT_ID   # resolved via CTS_ENV

def sign(secret, message):
    return hmac.new(bytes(secret, 'utf-8'), bytes(message, 'utf-8'), hashlib.sha256).hexdigest()

def get_all_fills(api_key, api_secret, start_us, end_us):
    method = 'GET'
    path = '/v2/fills'
    all_fills = []
    after = None
    while True:
        timestamp = str(int(time.time()))
        query = f'?product_ids={PRODUCT_ID}&start_time={start_us}&end_time={end_us}&page_size=200'
        if after:
            query += f'&after={after}'
        signature_data = method + timestamp + path + query
        signature = sign(api_secret, signature_data)
        headers = {'api-key': api_key, 'timestamp': timestamp, 'signature': signature,
                   'User-Agent': 'debug-audit-pnl', 'Content-Type': 'application/json'}
        resp = requests.get(base_url + path + query, headers=headers, timeout=(3, 27))
        data = resp.json()
        fills = data.get('result', [])
        all_fills.extend(fills)
        after = data.get('meta', {}).get('after')
        if not after or not fills:
            break
    return all_fills

api_key = os.environ.get("S4V2_API_KEY")
api_secret = os.environ.get("S4V2_API_SECRET")
START_US = 1789552980000000
END_US = int(time.time() * 1000000)

fills = get_all_fills(api_key, api_secret, START_US, END_US)
fills.sort(key=lambda f: f['created_at'])
print(f"RAW FILLS FETCHED: {len(fills)}")

merged = _merge_partial_fills_audit(fills)
print(f"AFTER MERGE: {len(merged)}")

pairs = _pair_fills_audit(merged)
print(f"PAIRS PRODUCED: {len(pairs)}")
total_pnl = 0.0
total_charges = 0.0
for p in pairs:
    print(f"{p['entry_ts_raw']} -> {p['exit_ts_raw']} | {p['dir']} | lot={p['lot']} | entry={p['entry_p']} exit={p['exit_p']} | pnl_usd={p['pnl_usd']:.4f} | charges={p['charges']:.4f}")
    total_pnl += p['pnl_usd']
    total_charges += p['charges']
print(f"\nTOTAL pnl_usd (dashboard logic): {total_pnl:.2f}")
print(f"TOTAL charges: {total_charges:.2f}")
print(f"NET (pnl_usd - charges): {total_pnl - total_charges:.2f}")
