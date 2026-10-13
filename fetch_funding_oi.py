import requests, csv, time

BASE = "https://api.india.delta.exchange/v2/history/candles"
START = 1704067200   # 2024-01-01 00:00:00 UTC
END   = 1751327999   # 2025-06-30 23:59:59 UTC
STEP  = 2000 * 3600  # 2000 hourly candles per request

def fetch(symbol, outfile):
    rows = []
    s = START
    while s < END:
        e = min(s + STEP - 3600, END)
        params = {"resolution": "1h", "symbol": symbol, "start": s, "end": e}
        r = requests.get(BASE, params=params, timeout=30)
        data = r.json()
        if not data.get("success"):
            print(f"ERROR at {s}: {data}")
            break
        result = data.get("result", [])
        rows.extend(result)
        print(f"{symbol}: fetched {len(result)} rows, {s} -> {e}")
        s = e + 3600
        time.sleep(0.3)
    with open(outfile, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close", "volume"])
        for row in rows:
            w.writerow([row.get("time"), row.get("open"), row.get("high"),
                        row.get("low"), row.get("close"), row.get("volume")])
    print(f"Saved {len(rows)} rows to {outfile}")

fetch("FUNDING:BTCUSD", "data/funding_btcusd_1h.csv")
fetch("OI:BTCUSD", "data/oi_btcusd_1h.csv")
