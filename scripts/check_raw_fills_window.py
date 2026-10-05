import hashlib, hmac, os, time, requests

base_url = 'https://api.india.delta.exchange'

def sign(secret, message):
    return hmac.new(bytes(secret, 'utf-8'), bytes(message, 'utf-8'), hashlib.sha256).hexdigest()

def get_fills(api_key, api_secret, product_id, start_us, end_us, label):
    method = 'GET'
    path = '/v2/fills'
    timestamp = str(int(time.time()))
    query = f'?product_ids={product_id}&start_time={start_us}&end_time={end_us}&page_size=200'
    signature_data = method + timestamp + path + query
    signature = sign(api_secret, signature_data)
    headers = {
        'api-key': api_key,
        'timestamp': timestamp,
        'signature': signature,
        'User-Agent': 'raw-fill-check',
        'Content-Type': 'application/json'
    }
    resp = requests.get(base_url + path + query, headers=headers, timeout=(3, 27))
    print(f"=== {label} ===")
    try:
        data = resp.json()
        for f in data.get('result', []):
            print(f"{f['created_at']} | {f['side']} | size={f['size']} | price={f['price']} | order_id={f['order_id']} | fill_id={f['id']} | role={f['role']}")
        print(f"Total fills: {len(data.get('result', []))}")
    except Exception as e:
        print("ERROR parsing response:", e, resp.text[:500])

# S4V3 window: 16-Sep-2026 04:00-04:04 UTC
s4v3_key = os.environ.get('S4V3_API_KEY')
s4v3_secret = os.environ.get('S4V3_API_SECRET')
if s4v3_key and s4v3_secret:
    get_fills(s4v3_key, s4v3_secret, 27, 1789531200000000, 1789531440000000, "S4V3 16-Sep 04:00-04:04 UTC")
else:
    print("S4V3_API_KEY / S4V3_API_SECRET missing")

# S4V2 window: 16-Sep-2026 02:00-02:32 UTC
s4v2_key = os.environ.get('S4V2_API_KEY')
s4v2_secret = os.environ.get('S4V2_API_SECRET')
if s4v2_key and s4v2_secret:
    get_fills(s4v2_key, s4v2_secret, 27, 1789524000000000, 1789525920000000, "S4V2 16-Sep 02:00-02:32 UTC")
else:
    print("S4V2_API_KEY / S4V2_API_SECRET missing")
