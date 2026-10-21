import requests
import datetime

trades = [
    ("147 Exit", "2026-09-07", 79997.5),
    ("148 Entry", "2026-09-07", 79897.5),
    ("148 Exit",  "2026-09-11", 76902.5),
    ("149 Entry", "2026-09-11", 76902.5),
    ("149 Exit",  "2026-09-14", 76997.5),
    ("150 Entry", "2026-09-14", 77202.5),
    ("150 Exit",  "2026-09-15", 77797.5),
    ("151 Entry", "2026-09-15", 77797.5),
    ("151 Exit",  "2026-09-16", 76002.5),
    ("152 Entry", "2026-09-16", 76002.5),
    ("152 Exit",  "2026-09-23", 86197.5),
    ("153 Entry", "2026-09-23", 86197.5),
    ("153 Exit",  "2026-09-23", 86202.5),
    ("154 Entry", "2026-09-28", 84302.5),
    ("154 Exit",  "2026-09-28", 84097.5),
    ("155 Entry", "2026-09-28", 83797.5),
    ("155 Exit",  "2026-10-01", 83802.5),
    ("156 Entry", "2026-10-01", 83802.5),
    ("156 Exit",  "2026-10-03", 84597.5),
    ("157 Entry", "2026-10-03", 84597.5),
    ("157 Exit",  "2026-10-04", 84802.5),
    ("158 Entry", "2026-10-04", 84902.5),
    ("158 Exit",  "2026-10-05", 86097.5),
    ("159 Entry", "2026-10-05", 86097.5),
    ("159 Exit",  "2026-10-09", 82102.5),
    ("160 Entry", "2026-10-09", 82102.5),
]

print(f"{'Trade':<12}{'Date':<12}{'Price':>10}{'DayLow':>10}{'DayHigh':>10}{'Result':>10}")

for label, date_str, price in trades:
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    start = int(dt.timestamp())
    end = start + 86400
    url = "https://api.india.delta.exchange/v2/history/candles"
    params = {"symbol": "BTCUSD", "resolution": "1d", "start": start, "end": end}
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    if data.get("result"):
        c = data["result"][0]
        low, high = c["low"], c["high"]
        ok = "REAL" if low <= price <= high else "MISMATCH"
        print(f"{label:<12}{date_str:<12}{price:>10}{low:>10}{high:>10}{ok:>10}")
    else:
        print(f"{label:<12}{date_str:<12}{price:>10}{'N/A':>10}{'N/A':>10}{'NO DATA':>10}")
