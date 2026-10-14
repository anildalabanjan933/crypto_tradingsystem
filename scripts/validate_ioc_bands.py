import os, hmac, hashlib, time, requests, json
import pandas as pd
from dotenv import load_dotenv
load_dotenv(dotenv_path="/home/anildalabanjan933/crypto_trading_system/.env")

BASE = "https://cdn-ind.testnet.deltaex.org"

def sig(secret, msg):
    return hmac.new(bytes(secret,'utf-8'), bytes(msg,'utf-8'), hashlib.sha256).hexdigest()

def get_fills(api_key, api_secret):
    method = "GET"
    path = "/v2/fills"
    all_fills = []
    after = None
    for _ in range(50):
        qs = "?page_size=100" + (f"&after={after}" if after else "")
        ts = str(int(time.time()))
        msg = method + ts + path + qs
        headers = {
            "api-key": api_key, "timestamp": ts, "signature": sig(api_secret, msg),
            "User-Agent": "validate-script", "Content-Type": "application/json"
        }
        r = requests.get(BASE+path+qs, headers=headers)
        if r.status_code != 200:
            print("ERROR", r.status_code, r.text[:300]); break
        data = r.json()
        res = data.get("result", [])
        all_fills.extend(res)
        after = data.get("meta", {}).get("after")
        if not after or not res:
            break
    return all_fills

bots = {
    "S4": (os.getenv("S4_API_KEY"), os.getenv("S4_API_SECRET")),
    "S4V2": (os.getenv("S4V2_API_KEY"), os.getenv("S4V2_API_SECRET")),
}

rows = []
for name, (k, s) in bots.items():
    fills = get_fills(k, s)
    print(f"{name}: pulled {len(fills)} fills")
    for f in fills:
        md = f.get("meta_data", {}) or {}
        mark = md.get("mark")
        fill_price = f.get("price")
        if mark and fill_price:
            try:
                slip = abs(float(fill_price) - float(mark))
                rows.append({
                    "bot": name, "created_at": f.get("created_at"),
                    "mark_price": mark, "fill_price": fill_price,
                    "slippage_$": slip, "side": f.get("side"),
                    "order_type": md.get("order_type"), "fill_type": f.get("fill_type")
                })
            except:
                pass

df = pd.DataFrame(rows)
if df.empty:
    print("NO DATA")
else:
    df.to_csv("output/ioc_band_slippage_history.csv", index=False)
    print(f"\nSaved: output/ioc_band_slippage_history.csv")
    print(f"Total fills analyzed: {len(df)}")
    print(f"Date range: {df['created_at'].min()} to {df['created_at'].max()}")
    print(f"\nSlippage stats ($):\n{df['slippage_$'].describe()}")
    print(f"\n% fills slippage > $150: {(df['slippage_$']>150).mean()*100:.2f}%")
    print(f"% fills slippage > $250: {(df['slippage_$']>250).mean()*100:.2f}%")
    print(f"Max slippage seen: ${df['slippage_$'].max():.2f}")
