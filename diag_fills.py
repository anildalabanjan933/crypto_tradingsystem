import os, hmac, hashlib, time, requests, datetime

ACC = "S4V2"
API_KEY = os.environ.get(f'{ACC}_API_KEY', '')
API_SECRET = os.environ.get(f'{ACC}_API_SECRET', '')

if not API_KEY or not API_SECRET:
    print(f"ERROR: {ACC}_API_KEY / {ACC}_API_SECRET not found in environment")
    exit(1)

BASE_URL = "https://cdn-ind.testnet.deltaex.org"
PATH = "/v2/fills"

start_dt = datetime.datetime(2026, 8, 23, 20, 30, 0, tzinfo=datetime.timezone.utc)
end_dt   = datetime.datetime(2026, 8, 24, 0, 0, 0, tzinfo=datetime.timezone.utc)
start_us = int(start_dt.timestamp() * 1e6)
end_us   = int(end_dt.timestamp() * 1e6)

prm = {"product_id": 84, "start_time": start_us, "end_time": end_us, "page_size": 100}
qs = "&".join(f"{a}={b}" for a, b in sorted(prm.items()))
ts = str(int(time.time()))
msg = "GET" + ts + PATH + "?" + qs
sig = hmac.new(API_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
headers = {"api-key": API_KEY, "timestamp": ts, "signature": sig}

r = requests.get(f"{BASE_URL}{PATH}?{qs}", headers=headers, timeout=10)
d = r.json()

if not d.get("success"):
    print("API ERROR:", d)
    exit(1)

fills = d.get("result", [])
print(f"Total fills returned: {len(fills)}\n")
print(f"{'created_at':<22} {'side':<5} {'size':<6} {'price':<10} {'order_id':<15} {'new_pos_size':<12}")
for f in sorted(fills, key=lambda x: x.get("created_at", "")):
    meta = f.get("meta_data", {}) or {}
    npos = meta.get("new_position", {}) or {}
    print(f"{f.get('created_at','')[:19]:<22} {f.get('side',''):<5} {f.get('size',''):<6} {f.get('price',''):<10} {str(f.get('order_id','')):<15} {str(npos.get('size','')):<12}")
