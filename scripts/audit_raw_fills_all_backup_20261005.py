import hashlib, hmac, os, time, requests

base_url = 'https://cdn-ind.testnet.deltaex.org'
PRODUCT_ID = 84  # BTCUSD

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
        headers = {
            'api-key': api_key,
            'timestamp': timestamp,
            'signature': signature,
            'User-Agent': 'audit-raw-fills',
            'Content-Type': 'application/json'
        }
        resp = requests.get(base_url + path + query, headers=headers, timeout=(3, 27))
        data = resp.json()
        if not data.get('success', False):
            print("API ERROR:", data)
            break
        fills = data.get('result', [])
        all_fills.extend(fills)
        after = data.get('meta', {}).get('after')
        if not after or not fills:
            break
    return all_fills

def run_bot(label, key_env, secret_env, start_us, end_us):
    api_key = os.environ.get(key_env)
    api_secret = os.environ.get(secret_env)
    print(f"\n========== {label} RAW LIVE FILLS (from baseline) ==========")
    if not api_key or not api_secret:
        print(f"MISSING {key_env}/{secret_env}")
        return
    fills = get_all_fills(api_key, api_secret, start_us, end_us)
    fills.sort(key=lambda f: f['created_at'])
    total_realized = 0.0
    for f in fills:
        meta = f.get('meta_data', {}) or {}
        newpos = meta.get('new_position', {}) or {}
        rpnl = newpos.get('realized_pnl')
        if rpnl:
            try:
                total_realized += float(rpnl)
            except ValueError:
                pass
        print(f"{f['created_at']} | {f['side']} | size={f['size']} | price={f['price']} | order_id={f['order_id']} | fill_id={f['id']} | role={f['role']} | commission={f['commission']} | realized_pnl={rpnl}")
    print(f"--- {label} TOTAL FILLS: {len(fills)} | SUM realized_pnl (from fills): {total_realized:.2f} ---")

# Baseline: 16-Sep-2026 3:33 PM IST = 10:03 AM UTC = epoch_us 1789552980000000
START_US = 1789552980000000
END_US = int(time.time() * 1000000)

run_bot("S4",   "S4_API_KEY",   "S4_API_SECRET",   START_US, END_US)
run_bot("S4V2", "S4V2_API_KEY", "S4V2_API_SECRET", START_US, END_US)
run_bot("S4V3", "S4V3_API_KEY", "S4V3_API_SECRET", START_US, END_US)

# DEBUG: fetch without product filter to see raw fills/product_ids on testnet
print("\n========== DEBUG: S4 fills, NO product filter ==========")
api_key = os.environ.get("S4_API_KEY")
api_secret = os.environ.get("S4_API_SECRET")
if api_key and api_secret:
    method = 'GET'
    path = '/v2/fills'
    timestamp = str(int(time.time()))
    query = f'?start_time={START_US}&end_time={END_US}&page_size=20'
    signature_data = method + timestamp + path + query
    signature = sign(api_secret, signature_data)
    headers = {
        'api-key': api_key, 'timestamp': timestamp, 'signature': signature,
        'User-Agent': 'debug-fills', 'Content-Type': 'application/json'
    }
    resp = requests.get(base_url + path + query, headers=headers, timeout=(3, 27))
    print("STATUS:", resp.status_code)
    print("BODY:", resp.text[:2000])
