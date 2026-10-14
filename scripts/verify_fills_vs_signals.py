import os, hmac, hashlib, time, requests, csv, sys
from datetime import datetime, timezone

def load_env(bot):
    """Loads correct API key/secret pair for s4 or s4v2 from .env"""
    env = {}
    with open(".env") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    if bot == "s4":
        return env.get("S4_API_KEY") or env.get("DELTA_API_KEY_S4") or env.get("API_KEY"), \
               env.get("S4_API_SECRET") or env.get("DELTA_API_SECRET_S4") or env.get("API_SECRET")
    else:
        return env.get("S4V2_API_KEY") or env.get("DELTA_API_KEY_S4V2"), \
               env.get("S4V2_API_SECRET") or env.get("DELTA_API_SECRET_S4V2")

def sign(secret, message):
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

def get_fills(api_key, api_secret, base_url, start_ts_us, end_ts_us):
    method = "GET"
    path = "/v2/fills"
    all_fills = []
    after = None
    while True:
        qs_parts = [f"start_time={start_ts_us}", f"end_time={end_ts_us}", "page_size=100"]
        if after:
            qs_parts.append(f"after={after}")
        query_string = "?" + "&".join(qs_parts)
        timestamp = str(int(time.time()))
        sig_data = method + timestamp + path + query_string
        signature = sign(api_secret, sig_data)
        headers = {
            "api-key": api_key, "timestamp": timestamp, "signature": signature,
            "User-Agent": "python-verify-script", "Content-Type": "application/json"
        }
        r = requests.get(base_url + path + query_string, headers=headers, timeout=15)
        data = r.json()
        if not data.get("success"):
            print("API ERROR:", data)
            break
        all_fills.extend(data.get("result", []))
        after = data.get("meta", {}).get("after")
        if not after:
            break
    return all_fills

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else "2026-08-21"
    start_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = start_dt.replace(hour=23, minute=59, second=59)
    start_us = int(start_dt.timestamp() * 1_000_000)
    end_us = int(end_dt.timestamp() * 1_000_000)

    base_url = "https://cdn-ind.testnet.deltaex.org"

    for bot in ["s4", "s4v2"]:
        api_key, api_secret = load_env(bot)
        if not api_key or not api_secret:
            print(f"{bot.upper()}: API key/secret not found in .env under expected names - skipping")
            continue
        print(f"\n=== {bot.upper()} REAL DELTA FILLS for {date_str} ===")
        fills = get_fills(api_key, api_secret, base_url, start_us, end_us)
        print(f"Total real fills: {len(fills)}")
        for f in fills:
            print(f"  id={f['id']} side={f['side']} price={f['price']} size={f['size']} "
                  f"created_at={f['created_at']} fill_type={f['fill_type']} order_id={f['order_id']}")

        print(f"\n--- {bot.upper()} signals CSV rows for {date_str} ---")
        sig_file = f"logs/signals_{bot}.csv"
        with open(sig_file) as fh:
            for row in csv.reader(fh):
                if row[0].startswith(date_str) or (row[1].startswith(date_str)):
                    print(f"  entry={row[0]} exit={row[1]} dir={row[2]} entry_p={row[4]} exit_p={row[5]}")

if __name__ == "__main__":
    main()
