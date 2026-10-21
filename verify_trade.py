import requests, bisect

BASE = "https://api.india.delta.exchange"
SLIP = 0.05
MAX_MARK_AGE = 1800

def get_candles(symbol, s, e):
    seen = {}
    cur = s
    while cur < e:
        ce = min(cur + 2000*60, e)
        r = requests.get(BASE + "/v2/history/candles", params={"symbol": symbol, "resolution": "1m", "start": cur, "end": ce})
        d = r.json()
        for c in d.get("result", []):
            seen[c["time"]] = c
        cur = ce
    return [seen[t] for t in sorted(seen)]

def fee(spot, px):
    return min(0.00015*spot, 0.05*px)*1.18

def mark_with_age(series, t, ts):
    i = bisect.bisect_right(t, ts) - 1
    if i < 0:
        return None, None
    return series[i]["close"], ts - series[i]["time"]

entry_ts = 1714047480
end_ts = entry_ts + 300000

call = get_candles("C-BTC-68000-030524", entry_ts, end_ts)
put = get_candles("P-BTC-60000-030524", entry_ts, end_ts)
spot = get_candles(".DEXBTUSD", entry_ts, end_ts)
c_t = [x["time"] for x in call]
p_t = [x["time"] for x in put]
s_t = [x["time"] for x in spot]

c_fill, p_fill = 700.0, 626.0
basis = c_fill + p_fill
target_pct = 0.30

cur = entry_ts + 60
while cur < end_ts:
    cm, c_age = mark_with_age(call, c_t, cur)
    pm, p_age = mark_with_age(put, p_t, cur)
    if cm is None or pm is None or c_age > MAX_MARK_AGE or p_age > MAX_MARK_AGE:
        cur += 60; continue
    pnl = (c_fill - cm) + (p_fill - pm)
    sx, _ = mark_with_age(spot, s_t, cur)
    if sx is None: sx = 65000
    floor = 2*SLIP*c_fill + 2*fee(sx, c_fill) + 2*SLIP*p_fill + 2*fee(sx, p_fill)
    if pnl >= target_pct*basis + floor:
        print("TARGET HIT at", cur, "pnl_raw=", pnl, "cm=", cm, "pm=", pm)
        break
    cur += 60

def fill_at(series, t, ts):
    i = bisect.bisect_right(t, ts)
    if i >= len(series) or series[i]["time"] - ts > 1800:
        return None, None
    return series[i]["open"], series[i]["time"]

trigger_ts = 1714269240
c_fill_exit, c_fts = fill_at(call, c_t, trigger_ts)
p_fill_exit, p_fts = fill_at(put, p_t, trigger_ts)
sx_exit, _ = mark_with_age(spot, s_t, trigger_ts)
print("call exit fill:", c_fill_exit, "at", c_fts)
print("put exit fill:", p_fill_exit, "at", p_fts)
print("spot at exit:", sx_exit)

ef_c = c_fill_exit * (1 + SLIP)
ef_p = p_fill_exit * (1 + SLIP)
pnl_net_raw = (c_fill - ef_c) + (p_fill - ef_p)
sx_entry, _ = mark_with_age(spot, s_t, entry_ts)
entry_fee = fee(sx_entry, c_fill) + fee(sx_entry, p_fill)
exit_fee = fee(sx_exit, ef_c) + fee(sx_exit, ef_p)
total_fee = entry_fee + exit_fee
net = (pnl_net_raw - total_fee) * 0.1  # MULT = 100 lots * 0.001
print("pnl_net_raw=", pnl_net_raw, "total_fee=", total_fee, "net=$", round(net,2))
