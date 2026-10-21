
            unsettled = False
            for side in ("C", "P"):
                ml = main[side]
                if not ml["sl_done"]:
                    l = ml["leg"]
                    px, fts = ml["series"].fill_at(exit_ts)
                    if px is None:
                        m, age = ml["series"].mark_with_age(exit_ts)
                        if m is None or age > MAX_MARK_AGE:
                            unsettled = True
                            break
                        px = m
                    ef = px * (1 + SLIP)
                    ml["pnl"] += l["raw"] - ef
                    ml["fee"] += fee(spot_at(spot_series, exit_ts, spot_px), ef)
                lz = lazy[side]["cur"]
                if lz and not lz["done"] and lz["armed"]:
                    px, fts = lz["series"].fill_at(exit_ts)
                    if px is None:
                        m, age = lz["series"].mark_with_age(exit_ts)
                        if m is None or age > MAX_MARK_AGE:
                            unsettled = True
                            break
                        px = m
                    ef = px * (1 - SLIP)
                    lazy[side]["pnl"] += ef - lz["leg"]["raw"]
                    lazy[side]["fee"] += fee(spot_at(spot_series, exit_ts, spot_px), ef)
            if unsettled:
                skip("UNSETTLED")
                continue

            day_pnl = (main["C"]["pnl"] + main["P"]["pnl"]) * MULT_MAIN * qty_mult
            day_fee = (entry_fee_raw + main["C"]["fee"] + main["P"]["fee"]) * MULT_MAIN * qty_mult
            for side in ("C", "P"):
                day_pnl += lazy[side]["pnl"] * MULT_LAZY * qty_mult
                day_fee += lazy[side]["fee"] * MULT_LAZY * qty_mult

            net = day_pnl - day_fee
            acc.trade(d, net, day_fee)
            trades.append((d, net, day_fee))
            lz_flag = f"lazyC={'Y' if main['C']['sl_done'] else 'N'}(re{lazy['C']['count']}) lazyP={'Y' if main['P']['sl_done'] else 'N'}(re{lazy['P']['count']})"
            print(f"[{tag}] {d} C={ck}@{cr[1]:.0f} P={pk}@{pr[1]:.0f} {lz_flag} pnl=${net:.2f} equity=${acc.eq:.2f}")

        except FetchError as ex:
            print(f"WARNING {d} {ex}")
            skip("FETCH_FAIL")
            continue

    years = max((b - a).days / 365.25, 0.01)
    summarize(f"[{tag}]", acc, years)
    return acc, trades'''

new = '''def run_btst_direct(entry_h, entry_m, a, b, qty_mult=1):
    tag = f"btst_direct {entry_h:02d}:{entry_m:02d}"
    acc = Acc()
    trades = []
    for d in daily_list(a, b):
        _cache.clear()
        entry_ts = ts_of(d, entry_h, entry_m)
        exp = d + timedelta(days=2 if entry_h == 19 else 1)
        exit_ts = ts_of(exp, 17, 15)

        def skip(reason):
            acc.skips[reason] = acc.skips.get(reason, 0) + 1

        try:
            sc = get_candles(SPOT, entry_ts, exit_ts + 2 * STEP)
            if not sc:
                skip("NO_DATA"); continue
            spot_series = Series(sc)
            spot_px = spot_series.mark_price(entry_ts)
            if spot_px is None:
                skip("NO_DATA"); continue

            ck = otm_strike(spot_px, "C", OTM_N)
            pk = otm_strike(spot_px, "P", OTM_N)
            cr = premium_at("C", ck, exp, entry_ts)
            pr = premium_at("P", pk, exp, entry_ts)
            if not cr or not pr:
                skip("NO_FILL"); continue

            main = {
                "C": {"leg": leg("S", "C", ck, exp, cr), "series": None, "sl_done": False, "pnl": 0.0, "fee": 0.0},
                "P": {"leg": leg("S", "P", pk, exp, pr), "series": None, "sl_done": False, "pnl": 0.0, "fee": 0.0},
            }
            for side in ("C", "P"):
                l = main[side]["leg"]
                main[side]["series"] = Series(get_candles(l["symbol"], entry_ts, exit_ts + 2 * STEP))

            entry_fee_raw = fee(spot_px, cr[1]) + fee(spot_px, pr[1])
            cur = max(cr[2], pr[2]) + STEP

            while cur < exit_ts:
                for side in ("C", "P"):
                    ml = main[side]
                    if ml["sl_done"]:
                        continue
                    l = ml["leg"]
                    m, age = ml["series"].mark_with_age(cur)
                    if m is None or age > MAX_MARK_AGE:
                        continue
                    sl_level = l["mkt"] * (1 + SL_MAIN_PCT)
                    if m >= sl_level:
                        px, fts = sl_level, cur
                        ef = px * (1 + SLIP)
                        ml["pnl"] += l["raw"] - ef
                        ml["fee"] += fee(spot_at(spot_series, fts, spot_px), ef)
                        ml["sl_done"] = True
                cur += STEP

            unsettled = False
            for side in ("C", "P"):
                ml = main[side]
                if ml["sl_done"]:
                    continue
                l = ml["leg"]
                px, fts = ml["series"].fill_at(exit_ts)
                if px is None:
                    m, age = ml["series"].mark_with_age(exit_ts)
                    if m is None or age > MAX_MARK_AGE:
                        unsettled = True
                        break
                    px = m
                ef = px * (1 + SLIP)
                ml["pnl"] += l["raw"] - ef
                ml["fee"] += fee(spot_at(spot_series, exit_ts, spot_px), ef)
            if unsettled:
                skip("UNSETTLED")
                continue

            day_pnl = (main["C"]["pnl"] + main["P"]["pnl"]) * MULT_MAIN * qty_mult
            day_fee = (entry_fee_raw + main["C"]["fee"] + main["P"]["fee"]) * MULT_MAIN * qty_mult

            net = day_pnl - day_fee
            acc.trade(d, net, day_fee)
            trades.append((d, net, day_fee))
            flag = f"slC={'Y' if main['C']['sl_done'] else 'N'} slP={'Y' if main['P']['sl_done'] else 'N'}"
            print(f"[{tag}] {d} C={ck}@{cr[1]:.0f} P={pk}@{pr[1]:.0f} {flag} pnl=${net:.2f} equity=${acc.eq:.2f}")

        except FetchError as ex:
            print(f"WARNING {d} {ex}")
            skip("FETCH_FAIL")
            continue

    years = max((b - a).days / 365.25, 0.01)
    summarize(f"[{tag}]", acc, years)
    return acc, trades'''

assert content.count(old) == 1, f"match count: {content.count(old)}"
content = content.replace(old, new)

content = content.replace(
    'print(f"WINDOW {a} to {b} | strategies=[strangle_recost x3, btst_lazy3 x4]")',
    'print(f"WINDOW {a} to {b} | strategies=[strangle_recost x3, btst_direct x4]")'
)
content = content.replace(
    'for h, m, qm in LAZY3_TIMES:\n        _, tr = run_lazy3_variant(h, m, a, b, qty_mult=qm)',
    'for h, m, qm in LAZY3_TIMES:\n        _, tr = run_btst_direct(h, m, a, b, qty_mult=qm)'
)
content = content.replace(
    'summarize("[PORTFOLIO ALL 7 VARIANTS]", portfolio, years)',
    'summarize("[PORTFOLIO ALL 7 VARIANTS]", portfolio, years)'
)

with open('algotest_backtest.py', 'w') as f:
    f.write(content)

print("Patched OK")
EOF

grep -n "def run_btst_direct\|run_lazy3_variant" algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
cd ~/strategies_options/backtest
ls -la algotest_backtest.py.bak_before_direct
cp algotest_backtest.py.bak_before_direct algotest_backtest.py
grep -n "def run_lazy3_variant\|def run_btst_direct" algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
python3 -c "
from algotest_backtest import *
d = date(2025,1,1)
ts19 = ts_of(d, 19, 0)
ts11 = ts_of(d, 11, 20)
for label, ts, exp_days in [('19:00', ts19, 2), ('11:20', ts11, 1)]:
    exp = d + timedelta(days=exp_days)
    sc = get_candles(SPOT, ts, ts + 7200)
    if not sc:
        print(label, 'NO SPOT DATA'); continue
    sx = Series(sc).mark_price(ts)
    print(label, 'spot=', sx)
    ck = otm_strike(sx, 'C', OTM_N)
    pk = otm_strike(sx, 'P', OTM_N)
    cr = premium_at('C', ck, exp, ts)
    pr = premium_at('P', pk, exp, ts)
    print(label, 'CE', ck, cr, 'PE', pk, pr)
"
python3 -c "
from datetime import date, timedelta
from algotest_backtest import *
d = date(2025,1,1)
ts19 = ts_of(d, 19, 0)
ts11 = ts_of(d, 11, 20)
for label, ts, exp_days in [('19:00', ts19, 2), ('11:20', ts11, 1)]:
    exp = d + timedelta(days=exp_days)
    sc = get_candles(SPOT, ts, ts + 7200)
    if not sc:
        print(label, 'NO SPOT DATA'); continue
    sx = Series(sc).mark_price(ts)
    print(label, 'spot=', sx)
    ck = otm_strike(sx, 'C', OTM_N)
    pk = otm_strike(sx, 'P', OTM_N)
    cr = premium_at('C', ck, exp, ts)
    pr = premium_at('P', pk, exp, ts)
    print(label, 'CE', ck, cr, 'PE', pk, pr)
"
python3 -c "
from datetime import date, timedelta
from algotest_backtest import *
d = date(2025,1,1)
ts19 = ts_of(d, 19, 0)
ts11 = ts_of(d, 11, 20)

exp19 = d + timedelta(days=2)
exp11 = d + timedelta(days=1)

pk19 = otm_strike(93797.9, 'P', OTM_N)
ck19 = otm_strike(93797.9, 'C', OTM_N)
pk11 = otm_strike(93809.5, 'P', OTM_N)

sym_c19 = osym('C', ck19, exp19)
sym_p19 = osym('P', pk19, exp19)
sym_p11 = osym('P', pk11, exp11)
print('sym_c19=', sym_c19)
print('sym_p19=', sym_p19)
print('sym_p11=', sym_p11)

c = get_candles(sym_p11, ts11 - MAX_FILL_GAP, ts11 + MAX_FILL_GAP + STEP)
print('p11 candles len=', len(c) if c else 0)
if c:
    print(c[:3])

c19 = get_candles(sym_c19, ts19 - MAX_FILL_GAP, ts19 + MAX_FILL_GAP + STEP)
print('c19 candles len=', len(c19) if c19 else 0)
"
python3 -c "
from algotest_backtest import *
import requests
sym = 'P-BTC-92800-020125'
r = requests.get(f'{BASE_URL}/v2/history/candles', params={'resolution':'1m','symbol':sym,'start':1735707000,'end':1735714200})
print(r.status_code)
print(r.text[:500])
"
grep -n "api.india.delta\|BASE_URL\|base_url\|history/candles" algotest_backtest.py | head -10
python3 -c "
from algotest_backtest import *
import requests
sym = 'P-BTC-92800-020125'
r = requests.get(BASE + '/v2/history/candles', params={'resolution':'1m','symbol':sym,'start':1735707000,'end':1735714200})
print(r.status_code)
print(r.text[:1000])
"
grep -n "def get_candles" -A 30 algotest_backtest.py
grep -n "^STEP\|^MAX_FILL_GAP\|^MAX_MARK_AGE" algotest_backtest.py
python3 -c "
from algotest_backtest import *
d = date(2025,1,1)
ts11 = ts_of(d, 11, 20)
print('ts11=', ts11)
print('STEP=', STEP, 'MAX_FILL_GAP=', MAX_FILL_GAP)
print('window start=', ts11 - MAX_FILL_GAP, 'end=', ts11 + MAX_FILL_GAP + STEP)
"
python3 -c "
from datetime import date
from algotest_backtest import *
d = date(2025,1,1)
ts11 = ts_of(d, 11, 20)
print('ts11=', ts11)
print('STEP=', STEP, 'MAX_FILL_GAP=', MAX_FILL_GAP)
print('window start=', ts11 - MAX_FILL_GAP, 'end=', ts11 + MAX_FILL_GAP + STEP)
sym = 'P-BTC-92800-020125'
c = get_candles(sym, ts11 - MAX_FILL_GAP, ts11 + MAX_FILL_GAP + STEP)
print('candles len=', len(c) if c else 0)
"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=1735708800&end=1735712460" | head -c 1000
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=1735700000&end=1735720000" | python3 -c "
import json,sys
d = json.load(sys.stdin)
r = d['result']
print('count=', len(r))
if r:
    times = sorted(c['time'] for c in r)
    print('min_time=', times[0], 'max_time=', times[-1])
"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=1735700000&end=1735720000" | python3 -c "
import json,sys
d = json.load(sys.stdin)
r = d['result']
times = sorted(c['time'] for c in r)
target_start, target_end = 1735708800, 1735712460
in_range = [t for t in times if target_start <= t <= target_end]
print('candles in our target window:', len(in_range))
print('times near target:', [t for t in times if abs(t - 1735710600) < 3000])
"
echo "Test 1 - exact narrow window:"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=1735708800&end=1735712460" | python3 -c "import json,sys; d=json.load(sys.stdin); print('count=', len(d['result']))"
echo "Test 2 - wider window, same core range:"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=1735705000&end=1735715000" | python3 -c "import json,sys; d=json.load(sys.stdin); print('count=', len(d['result']))"
echo "Test 3 - narrow window shifted slightly:"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=1735708799&end=1735712461" | python3 -c "import json,sys; d=json.load(sys.stdin); print('count=', len(d['result']))"
echo "Test 4 - earlier start, same end:"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=1735705000&end=1735712460" | python3 -c "import json,sys; d=json.load(sys.stdin); print('count=', len(d['result']))"
echo "Test 5 - same start, later end:"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=1735708800&end=1735715000" | python3 -c "import json,sys; d=json.load(sys.stdin); print('count=', len(d['result']))"
echo "Test 6 - exact window size as failing test but different offset:"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=1735700000&end=1735703660" | python3 -c "import json,sys; d=json.load(sys.stdin); print('count=', len(d['result']))"
for s in 1735700000 1735705000 1735707000 1735708000 1735708500 1735708700 1735708790 1735708800 1735708810 1735709000; do   c=$(curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=$s&end=1735712460" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['result']))");   echo "start=$s -> count=$c"; done
for s in 1735707000 1735707200 1735707400 1735707600 1735707800 1735707900 1735707950 1735707960 1735707970 1735708000; do   c=$(curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=$s&end=1735712460" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['result']))");   echo "start=$s -> count=$c"; done
echo "Fix test A - same failing start, much wider end:"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=1735708800&end=1735720000" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['result']))"
echo "Fix test B - failing start, minimal 1hr window:"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=1735708800&end=1735712400" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['result']))"
echo "Fix test C - failing start, 5min window:"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=P-BTC-92800-020125&resolution=1m&start=1735708800&end=1735709100" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['result']))"
fetch_start = ts - 3600  # safe anchor, avoids API empty-result quirk
fetch_end = ts + MAX_FILL_GAP + STEP
candles = get_candles(symbol, fetch_start, fetch_end)
candles = [c for c in candles if ts - MAX_FILL_GAP <= c["time"] <= ts + MAX_FILL_GAP + STEP]
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
grep -n "fetch_start\|ts - 3600\|MAX_FILL_GAP" algotest_backtest.py
c = get_candles(sym, ts - 3600, ts + MAX_FILL_GAP + STEP)
c = [x for x in c if ts - MAX_FILL_GAP <= x["time"] <= ts + MAX_FILL_GAP + STEP]
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
nano algotest_backtest.py
# go to line 150, replace with the two lines, save (Ctrl+O, Enter, Ctrl+X)
sed -n '150p' algotest_backtest.py
sed -i '150s/.*/    c = get_candles(sym, ts - 3600, ts + MAX_FILL_GAP + STEP)/' algotest_backtest.py
sed -i '150a\    c = [x for x in c if ts - MAX_FILL_GAP <= x["time"] <= ts + MAX_FILL_GAP + STEP]' algotest_backtest.py
sed -n '148,153p' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
grep -n "19:00\|1900\|run_lazy3_variant" algotest_backtest.py | head -30
sed -n '500,515p' algotest_backtest.py
grep -n "LAZY3_TIMES" algotest_backtest.py
sed -n '325,360p' algotest_backtest.py
python3 -c "
from algotest_backtest import *
d = date(2025,1,1)
entry_ts = ts_of(d, 19, 0)
exp = d + timedelta(days=2)
sc = get_candles(SPOT, entry_ts, entry_ts+7200)
spot_px = Series(sc).mark_price(entry_ts)
print('spot', spot_px)
ck = otm_strike(spot_px, 'C', OTM_N)
pk = otm_strike(spot_px, 'P', OTM_N)
print('strikes', ck, pk, 'exp', exp)
print('sym', osym('C', ck, exp))
cr = premium_at('C', ck, exp, entry_ts)
print('cr', cr)
"
python3 -c "
from algotest_backtest import *
from datetime import date, timedelta
d = date(2025,1,1)
entry_ts = ts_of(d, 19, 0)
exp = d + timedelta(days=2)
sc = get_candles(SPOT, entry_ts, entry_ts+7200)
spot_px = Series(sc).mark_price(entry_ts)
print('spot', spot_px)
ck = otm_strike(spot_px, 'C', OTM_N)
pk = otm_strike(spot_px, 'P', OTM_N)
print('strikes', ck, pk, 'exp', exp)
print('sym', osym('C', ck, exp))
cr = premium_at('C', ck, exp, entry_ts)
print('cr', cr)
"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=C-BTC-94800-030125&resolution=1m&start=$(python3 -c "from algotest_backtest import ts_of; from datetime import date; print(ts_of(date(2025,1,1),19,0)-3600)")&end=$(python3 -c "from algotest_backtest import ts_of; from datetime import date; print(ts_of(date(2025,1,1),19,0)+1800+60)")" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['result']))"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=C-BTC-94800-030125&resolution=1h&start=1735700000&end=1735900000" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['result']))"
curl -s "https://api.india.delta.exchange/v2/products?symbol=C-BTC-94800-030125" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('result') or d.get('error'))"
grep -n "def otm_strike" -A 15 algotest_backtest.py
sed -n '346,352p' algotest_backtest.py
sed -i '348,352c\
            ck = otm_strike(spot_px, "C", OTM_N)\
            pk = otm_strike(spot_px, "P", OTM_N)\
            cr = premium_at("C", ck, exp, entry_ts)\
            pr = premium_at("P", pk, exp, entry_ts)\
            n_try = OTM_N\
            while (not cr or not pr) and n_try > 1:\
                n_try -= 1\
                ck = otm_strike(spot_px, "C", n_try)\
                pk = otm_strike(spot_px, "P", n_try)\
                cr = premium_at("C", ck, exp, entry_ts)\
                pr = premium_at("P", pk, exp, entry_ts)\
            if not cr or not pr:' algotest_backtest.py
sed -n '346,362p' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
python3 -c "
from algotest_backtest import *
from datetime import date, timedelta
d = date(2025,1,1)
entry_ts = ts_of(d, 19, 0)
exp = d + timedelta(days=2)
sc = get_candles(SPOT, entry_ts, entry_ts+7200)
spot_px = Series(sc).mark_price(entry_ts)
for n in [5,4,3,2,1]:
    ck = otm_strike(spot_px, 'C', n)
    pk = otm_strike(spot_px, 'P', n)
    cr = premium_at('C', ck, exp, entry_ts)
    pr = premium_at('P', pk, exp, entry_ts)
    print(n, ck, pk, cr, pr)
"
sed -n '346,362p' algotest_backtest.py
sed -i '348,359c\
            ck = pk = None\
            cr = pr = None\
            for n in range(OTM_N, 0, -1):\
                if cr is None:\
                    k = otm_strike(spot_px, "C", n)\
                    r = premium_at("C", k, exp, entry_ts)\
                    if r:\
                        ck, cr = k, r\
            for n in range(OTM_N, 0, -1):\
                if pr is None:\
                    k = otm_strike(spot_px, "P", n)\
                    r = premium_at("P", k, exp, entry_ts)\
                    if r:\
                        pk, pr = k, r\
            if not cr or not pr:' algotest_backtest.py
sed -n '346,365p' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
grep -n "lazy\|hedge" algotest_backtest.py | head -20
grep -n "def ts_of" -A 6 algotest_backtest.py
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=C-BTC-94800-020125&resolution=1m&start=1735699740&end=1735700100" | python3 -m json.tool
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=C-BTC-94800-020125&resolution=1m&start=1735698000&end=1735701600" | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d['result']
print('count=',len(r))
for c in sorted(r,key=lambda x:x['time']):
    if 1735699700 <= c['time'] <= 1735700000:
        print(c)
"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=C-BTC-94800-020125&resolution=1m&start=1735698000&end=1735701600" | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d['result']
for c in sorted(r,key=lambda x:x['time']):
    print(c['time'], c['open'], c['high'], c['low'], c['close'])
"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=MARK:C-BTC-94800-020125&resolution=1m&start=1735699200&end=1735700400" | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d['result']
for c in sorted(r,key=lambda x:x['time']):
    print(c['time'], c['close'])
"
python3 -c "
from algotest_backtest import ts_of
from datetime import date
print(ts_of(date(2025,1,1), 9, 20))
"
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=MARK:C-BTC-94800-020125&resolution=1m&start=1735703200&end=1735703600" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for c in sorted(d['result'],key=lambda x:x['time']):
    print(c['time'], c['close'])
"
sed -n '145,165p' algotest_backtest.py
sed -n '148,160p' algotest_backtest.py
sed -i '148,160c\
def premium_at(t, k, e, ts):\
    sym = osym(t, k, e)\
    mc = get_candles(f"MARK:{sym}", ts - 3600, ts + MAX_FILL_GAP + STEP)\
    mc = [x for x in mc if ts - MAX_FILL_GAP <= x["time"] <= ts + MAX_FILL_GAP + STEP]\
    if mc:\
        ms = Series(mc)\
        mpx, mage = ms.mark_with_age(ts)\
        if mpx is not None and mage <= MAX_FILL_GAP and mpx > 0:\
            return (sym, mpx, ts)\
    c = get_candles(sym, ts - 3600, ts + MAX_FILL_GAP + STEP)\
    c = [x for x in c if ts - MAX_FILL_GAP <= x["time"] <= ts + MAX_FILL_GAP + STEP]\
    if not c:\
        return None\
    s = Series(c)\
    px, age = s.mark_with_age(ts)\
    if px is not None and age <= MAX_FILL_GAP and px > 0:\
        return (sym, px, ts)\
    px2, fts2 = s.fill_at(ts)\
    if px2 is not None and px2 > 0:\
        return (sym, px2, fts2)' algotest_backtest.py
sed -n '148,168p' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
sed -i '148,166c\
def premium_at(t, k, e, ts):\
    sym = osym(t, k, e)\
    c = get_candles(sym, ts - 3600, ts + MAX_FILL_GAP + STEP)\
    c = [x for x in c if ts - MAX_FILL_GAP <= x["time"] <= ts + MAX_FILL_GAP + STEP]\
    if c:\
        s = Series(c)\
        px, age = s.mark_with_age(ts)\
        if px is not None and age <= MAX_FILL_GAP and px > 0:\
            return (sym, px, ts)\
    mc = get_candles(f"MARK:{sym}", ts - 3600, ts + MAX_FILL_GAP + STEP)\
    mc = [x for x in mc if ts - MAX_FILL_GAP <= x["time"] <= ts + MAX_FILL_GAP + STEP]\
    if mc:\
        ms = Series(mc)\
        mpx, mage = ms.mark_with_age(ts)\
        if mpx is not None and mage <= MAX_FILL_GAP and mpx > 0:\
            return (sym, mpx, ts)\
    if c:\
        px2, fts2 = s.fill_at(ts)\
        if px2 is not None and px2 > 0:\
            return (sym, px2, fts2)\
    return None' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
sed -n '145,172p' algotest_backtest.py
grep -n "return (sym, px2, fts2)" algotest_backtest.py
sed -n '163,172p' algotest_backtest.py
sed -i '169,170d' algotest_backtest.py
sed -n '145,172p' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=C-BTC-94800-020125&resolution=1m&start=1735701600&end=1735705200" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for c in sorted(d['result'],key=lambda x:x['time']):
    print(c['time'], c['close'])
"
find . -name "__pycache__" -o -name "*.pyc" | xargs rm -rf
grep -n "def mark_with_age" -A 15 algotest_backtest.py
curl -s "https://api.india.delta.exchange/v2/history/candles?symbol=MARK:C-BTC-94800-020125&resolution=1m&start=1735703100&end=1735703700" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for c in sorted(d['result'],key=lambda x:x['time']):
    print(c['time'], c['close'])
"
sed -n '145,167p' algotest_backtest.py
sed -i '154s/age <= MAX_FILL_GAP/age <= 300/' algotest_backtest.py
sed -n '148,160p' algotest_backtest.py
grep -n "age <= MAX_FILL_GAP" algotest_backtest.py
sed -i '155s/age <= MAX_FILL_GAP/age <= 300/' algotest_backtest.py
sed -n '148,167p' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
grep -n "_cache\|cache_file\|\.cache\|pickle\|shelve" algotest_backtest.py | head -20
sed -n '40,73p' algotest_backtest.py
python3 -c "
from algotest_backtest import premium_at, ts_of
from datetime import date
entry_ts = ts_of(date(2025,1,1), 9, 20)
print('entry_ts', entry_ts)
print(premium_at('C', 94800, date(2025,1,2), entry_ts))
"
python3 -c "
from algotest_backtest import get_candles, ts_of, MAX_FILL_GAP, STEP, Series
from datetime import date
entry_ts = ts_of(date(2025,1,1), 9, 20)
c = get_candles('C-BTC-94800-020125', entry_ts - 3600, entry_ts + MAX_FILL_GAP + STEP)
c = [x for x in c if entry_ts - MAX_FILL_GAP <= x['time'] <= entry_ts + MAX_FILL_GAP + STEP]
s = Series(c)
px, age = s.mark_with_age(entry_ts)
print('picked px', px, 'age', age)
for x in c[:10]:
    print(x['time'], x['close'])
"
python3 -c "
from algotest_backtest import get_candles, ts_of
from datetime import date
entry_ts = ts_of(date(2025,1,1), 9, 20)
c = get_candles('C-BTC-94800-020125', entry_ts - 3600, entry_ts + 3600)
for x in c:
    if abs(x['time'] - entry_ts) < 300:
        print(x)
"
sed -n '148,167p' algotest_backtest.py
cd ~/strategies_options/backtest
sed -n '148,167p' algotest_backtest.py
sed -i '150a\    c = [x for x in c if x.get("volume", 0) > 0]' algotest_backtest.py
sed -n '148,170p' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
sed -n '395,450p' algotest_backtest.py
grep -n "SL_MAIN_PCT\s*=\|MAX_MARK_AGE\s*=" algotest_backtest.py
grep -n '"series"\] = Series' algotest_backtest.py
cd ~/strategies_options/backtest
git add algotest_backtest.py
git commit -m "fix stale zero-volume candle bug in premium_at"
git push origin master
sed -n '46,72p' algotest_backtest.py
sed -i '70a\    if not symbol.startswith("MARK:"):\n        out = [x for x in out if x.get("volume", 0) > 0]' algotest_backtest.py
sed -n '68,74p' algotest_backtest.py
sed -n '68,75p' algotest_backtest.py
sed -i '71,72d' algotest_backtest.py
sed -i '70a\    out = [seen[t] for t in sorted(seen)]\n    if not symbol.startswith("MARK:"):\n        out = [x for x in out if x.get("volume", 0) > 0]' algotest_backtest.py
sed -n '66,76p' algotest_backtest.py
sed -n '71,75p' algotest_backtest.py
sed -i '74d' algotest_backtest.py
sed -n '66,76p' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
sed -i '73s/.*/        out = [x for x in out if (x.get("volume") or 0) > 0]/' algotest_backtest.py
sed -n '70,76p' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
sed -i '72s/.*/    if symbol.startswith("C-") or symbol.startswith("P-"):/' algotest_backtest.py
sed -n '70,76p' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
python3 -c "
from algotest_backtest import *
from datetime import date, timedelta
d = date(2025,1,1)
entry_ts = ts_of(d, 10, 20)
exp = d + timedelta(days=1)
exit_ts = ts_of(exp, 17, 15)
sc = get_candles(SPOT, entry_ts, exit_ts + 2*STEP)
spot_px = Series(sc).mark_price(entry_ts)
ck = otm_strike(spot_px, 'C', OTM_N)
cr = premium_at('C', ck, exp, entry_ts)
print('C entry', ck, cr)
c = get_candles(cr[0], entry_ts, exit_ts + 2*STEP)
s = Series(c)
sl_level = cr[1] * (1 + SL_MAIN_PCT)
print('sl_level', sl_level)
maxpx = max(x['close'] for x in c)
print('max close seen', maxpx)
"
python3 -c "
from algotest_backtest import *
from datetime import date, timedelta
d = date(2025,1,1)
entry_ts = ts_of(d, 10, 20)
exp = d + timedelta(days=1)
exit_ts = ts_of(exp, 17, 15)
sc = get_candles(SPOT, entry_ts, exit_ts + 2*STEP)
spot_px = Series(sc).mark_price(entry_ts)
ck = otm_strike(spot_px, 'C', OTM_N)
cr = premium_at('C', ck, exp, entry_ts)
c = get_candles(cr[0], entry_ts, exit_ts + 2*STEP)
s = Series(c)
sl_level = cr[1] * (1 + SL_MAIN_PCT)
for x in sorted(c, key=lambda z: z['time']):
    if x['close'] >= sl_level:
        print('first SL cross at', x['time'], x['close'])
        break
print('loop start cur =', cr[2]+STEP, 'exit_ts=', exit_ts)
"
python3 -c "
from algotest_backtest import *
from datetime import date, timedelta
d = date(2025,1,1)
entry_ts = ts_of(d, 10, 20)
exp = d + timedelta(days=1)
exit_ts = ts_of(exp, 17, 15)
sc = get_candles(SPOT, entry_ts, exit_ts + 2*STEP)
spot_px = Series(sc).mark_price(entry_ts)
ck = otm_strike(spot_px, 'C', OTM_N)
cr = premium_at('C', ck, exp, entry_ts)
c = get_candles(cr[0], entry_ts, exit_ts + 2*STEP)
s = Series(c)
m, age = s.mark_with_age(1735792680)
print('mark at cross time', m, 'age', age)
sl_level = cr[1] * (1 + SL_MAIN_PCT)
print('sl_level', sl_level)
"
grep -n "^STEP\s*=" algotest_backtest.py
sed -n '450,470p' algotest_backtest.py
sed -n '360,395p' algotest_backtest.py
grep -n "^def leg" algotest_backtest.py
sed -n '187,200p' algotest_backtest.py
sed -n '466,480p' algotest_backtest.py
sed -n '408,420p' algotest_backtest.py
sed -i '416s/px, fts = sl_level, cur/px, fts = m, cur/' algotest_backtest.py
sed -n '412,420p' algotest_backtest.py
grep -n "px, fts = sl_level, cur" algotest_backtest.py
sed -i '285s/px, fts = sl_level, cur/px, fts = m, cur/' algotest_backtest.py
sed -i '417s/px, fts = sl_level, cur/px, fts = m, cur/' algotest_backtest.py
grep -n "px, fts = " algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
sed -n '420,448p' algotest_backtest.py
sed -n '485,515p' algotest_backtest.py
grep -n "^MULT_MAIN\|^MULT_LAZY\|qty_mult\s*=" algotest_backtest.py
grep -n "^LOTS_MAIN\|^LOTS_LAZY\|^CV\s*=\|qm\s*=" algotest_backtest.py
sed -n '520,532p' algotest_backtest.py
grep -n "LAZY3_TIMES" algotest_backtest.py
python3 -c "
from algotest_backtest import *
from datetime import date
a = b = date(2025,1,1)
run_lazy3_variant(10, 20, a, b, qty_mult=1)
"
sed -i '496a\            print("DEBUG mainC",main["C"]["pnl"],"mainP",main["P"]["pnl"],"lazyC",lazy["C"]["pnl"],"lazyP",lazy["P"]["pnl"],"feeC",main["C"]["fee"],"feeP",main["P"]["fee"])' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01 2>&1 | grep -A1 "10:20"
sed -i '497a\            print("DEBUG lazyFeeC",lazy["C"]["fee"],"lazyFeeP",lazy["P"]["fee"],"entry_fee_raw",entry_fee_raw)' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01 2>&1 | grep -A2 "10:20" | tail -3
grep -n "DEBUG" algotest_backtest.py
sed -n '490,502p' algotest_backtest.py
sed -i '497s/"DEBUG mainC"/"DEBUG",tag,"mainC"/' algotest_backtest.py
sed -i '498s/"DEBUG lazyFeeC"/"DEBUG",tag,"lazyFeeC"/' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01 2>&1 | grep "DEBUG"
sed -i '488a\                    print("DEBUG LAZY_EXIT",tag,side,"armed_px",lz["leg"]["raw"],"trail_sl",lz["trail_sl"],"exit_px",ef if "ef" in dir() else None)' algotest_backtest.py
sed -n '483,492p' algotest_backtest.py
sed -i '489d' algotest_backtest.py
grep -n "ef = px \* (1 - SLIP)" algotest_backtest.py
sed -i '448a\                                    print("DEBUG LAZY_TRAIL_EXIT",tag,side,"armed_px",lz["leg"]["raw"],"trail_sl",lz["trail_sl"],"px",px,"ef",ef,"ts",fts)' algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01 2>&1 | grep "LAZY_TRAIL_EXIT"
grep -n "^SL_LAZY_PCT\|^TRAIL_STEP\|^TRAIL_MOVE\|^SL_LAZY_PTS\|^SL_MAIN_PCT" algotest_backtest.py
cd ~/strategies_options/backtest
grep -n "^SL_LAZY_PCT\|^TRAIL_STEP\|^TRAIL_MOVE\|^SL_LAZY_PTS\|^SL_MAIN_PCT" algotest_backtest.py
grep -n "SL_LAZY_PTS" algotest_backtest.py
cd ~/strategies_options/backtest
grep -n "SL_LAZY_PTS" algotest_backtest.py
sed -i '24s/SL_LAZY_PTS = 50/SL_LAZY_PCT = 0.50/' algotest_backtest.py
sed -i '400s/lz_leg\["raw"\] - SL_LAZY_PTS/lz_leg["raw"] * (1 - SL_LAZY_PCT)/' algotest_backtest.py
sed -i '438s/lz\["leg"\]\["raw"\] - SL_LAZY_PTS/lz["leg"]["raw"] * (1 - SL_LAZY_PCT)/' algotest_backtest.py
sed -i '444s/lz\["leg"\]\["raw"\] - SL_LAZY_PTS/lz["leg"]["raw"] * (1 - SL_LAZY_PCT)/' algotest_backtest.py
grep -n "SL_LAZY_PCT" algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
sed -i '24s/SL_LAZY_PCT = 0.50/SL_LAZY_PTS = 50/' algotest_backtest.py
sed -i '400s/lz_leg\["raw"\] \* (1 - SL_LAZY_PCT)/lz_leg["raw"] - SL_LAZY_PTS/' algotest_backtest.py
sed -i '438s/lz\["leg"\]\["raw"\] \* (1 - SL_LAZY_PCT)/lz["leg"]["raw"] - SL_LAZY_PTS/' algotest_backtest.py
sed -i '444s/lz\["leg"\]\["raw"\] \* (1 - SL_LAZY_PCT)/lz["leg"]["raw"] - SL_LAZY_PTS/' algotest_backtest.py
grep -n "SL_LAZY_PTS" algotest_backtest.py
cd ~/strategies_options/backtest
sed -i '24s/SL_LAZY_PCT = 0.50/SL_LAZY_PTS = 50/' algotest_backtest.py
sed -i '400s/lz_leg\["raw"\] \* (1 - SL_LAZY_PCT)/lz_leg["raw"] - SL_LAZY_PTS/' algotest_backtest.py
sed -i '438s/lz\["leg"\]\["raw"\] \* (1 - SL_LAZY_PCT)/lz["leg"]["raw"] - SL_LAZY_PTS/' algotest_backtest.py
sed -i '444s/lz\["leg"\]\["raw"\] \* (1 - SL_LAZY_PCT)/lz["leg"]["raw"] - SL_LAZY_PTS/' algotest_backtest.py
grep -n "SL_LAZY_PTS" algotest_backtest.py
grep -n "SL_MAIN_PCT\|run_recost_variant\|re(C,P)" algotest_backtest.py | head -20
sed -n '222,240p' algotest_backtest.py
sed -n '240,322p' algotest_backtest.py
grep -n "^SL_RECOST_PCT" algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01 2>&1 | grep -A1 "10:20" | head -6
sed -i '/print("DEBUG/d' algotest_backtest.py
grep -n "DEBUG" algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-01
git add algotest_backtest.py
git commit -m "fix SL fill price to use actual crossed mark instead of exact sl_level"
git push origin master
python3 -c "
from algotest_backtest import *
from datetime import date, timedelta
d = date(2025,1,1)
entry_ts = ts_of(d, 10, 20)
exp = d + timedelta(days=1)
exit_ts = ts_of(exp, 17, 15)
sc = get_candles(SPOT, entry_ts, exit_ts + 2*STEP)
spot_px = Series(sc).mark_price(entry_ts)
ck = otm_strike(spot_px, 'C', OTM_N)
cr = premium_at('C', ck, exp, entry_ts)
c = get_candles(cr[0], entry_ts, exit_ts + 2*STEP)
s = Series(c)
m, age = s.mark_with_age(1735792680)
print('m',m,'age',age,'sl_level', cr[1]*2)
"
python3 -c "
from algotest_backtest import *
from datetime import date, timedelta
d = date(2025,1,1)
entry_ts = ts_of(d, 10, 20)
exp = d + timedelta(days=1)
exit_ts = ts_of(exp, 17, 15)
sc = get_candles(SPOT, entry_ts, exit_ts + 2*STEP)
spot_px = Series(sc).mark_price(entry_ts)
ck = otm_strike(spot_px, 'C', OTM_N)
cr = premium_at('C', ck, exp, entry_ts)
c = get_candles(cr[0], entry_ts, exit_ts + 2*STEP)
for x in sorted(c, key=lambda z: z['time']):
    if x['time'] >= 1735792500 and x['time'] <= 1735792800:
        print(x['time'], x['close'], x.get('volume'))
"
cd ~/strategies_options/backtest
python3 algotest_backtest.py --start 2024-12-31 --end 2025-01-31
cd ~/strategies_options/backtest
python3 algotest_backtest.py --start 2024-12-31 --end 2025-01-31
import shutil
f = "algotest_backtest.py"
shutil.copy(f, f + ".bak")
s = open(f).read()
I = " "
R = [
]
for old, new, expect in R:
open(f, "w").write(s)
print("PATCHED OK")
cat > patch.py << 'EOF'
import shutil
f = "algotest_backtest.py"
shutil.copy(f, f + ".bak")
s = open(f).read()
I = " "
R = [
    ('i = bisect.bisect_right(self.t, ts) - 1',
     'i = bisect.bisect_left(self.t, ts) - 1', 1),
    ('    def fill_at(self, ts):',
     '    def peak(self, ts):\n        i = bisect.bisect_left(self.t, ts) - 1\n        return self.c[i]["high"] if i >= 0 else 0\n\n    def fill_at(self, ts):', 1),
    ('sl_level = l["mkt"] * (1 + SL_RECOST_PCT)',
     'sl_level = l["mkt"] * (1 + SL_RECOST_PCT)\n' + I*20 + 'm = max(m, sl["series"].peak(cur))', 1),
    ('sl_level = l["mkt"] * (1 + SL_MAIN_PCT)',
     'sl_level = l["mkt"] * (1 + SL_MAIN_PCT)\n' + I*28 + 'm = max(m, ml["series"].peak(cur))', 2),
    ('if m >= lz["trig"]:',
     'if max(m, lz["series"].peak(cur)) >= lz["trig"]:', 1),
    ('lz["leg"]["raw"] = px * (1 + SLIP)',
     'lz["leg"]["raw"] = lz["trig"] * (1 + SLIP)', 1),
    ('lzstate["pnl"] += ef - lz["leg"]["raw"]',
     'ef = lz["trail_sl"] * (1 - SLIP)\n' + I*36 + 'lzstate["pnl"] += ef - lz["leg"]["raw"]', 1),
]
for old, new, expect in R:
    found = s.count(old)
    assert found == expect, f"MISMATCH ({found} vs {expect}): {old}"
    s = s.replace(old, new)
open(f, "w").write(s)
print("PATCHED OK")
EOF

python3 patch.py
cd ~/strategies_options/backtest
python3 patch.py
mv ~/patch.py ~/strategies_options/backtest/patch.py
python3 patch.py
sed -i "s/'sl_level = l\[\"mkt\"\] \* (1 + SL_MAIN_PCT)',\n.*ml\[\"series\"\].peek(cur))', 2)/&/" patch.py
python3 -c "
s = open('patch.py').read()
s = s.replace('ml[\"series\"].peak(cur))', 2)', 'ml[\"series\"].peak(cur))', 1)')
open('patch.py','w').write(s)
"
python3 patch.py
cat > patch.py << 'EOF'
import shutil
f = "algotest_backtest.py"
shutil.copy(f, f + ".bak")
s = open(f).read()
I = " "
R = [
    ('i = bisect.bisect_right(self.t, ts) - 1',
     'i = bisect.bisect_left(self.t, ts) - 1', 1),
    ('    def fill_at(self, ts):',
     '    def peak(self, ts):\n        i = bisect.bisect_left(self.t, ts) - 1\n        return self.c[i]["high"] if i >= 0 else 0\n\n    def fill_at(self, ts):', 1),
    ('sl_level = l["mkt"] * (1 + SL_RECOST_PCT)',
     'sl_level = l["mkt"] * (1 + SL_RECOST_PCT)\n' + I*20 + 'm = max(m, sl["series"].peak(cur))', 1),
    ('sl_level = l["mkt"] * (1 + SL_MAIN_PCT)',
     'sl_level = l["mkt"] * (1 + SL_MAIN_PCT)\n' + I*28 + 'm = max(m, ml["series"].peak(cur))', 1),
    ('if m >= lz["trig"]:',
     'if max(m, lz["series"].peak(cur)) >= lz["trig"]:', 1),
    ('lz["leg"]["raw"] = px * (1 + SLIP)',
     'lz["leg"]["raw"] = lz["trig"] * (1 + SLIP)', 1),
    ('lzstate["pnl"] += ef - lz["leg"]["raw"]',
     'ef = lz["trail_sl"] * (1 - SLIP)\n' + I*36 + 'lzstate["pnl"] += ef - lz["leg"]["raw"]', 1),
]
for old, new, expect in R:
    found = s.count(old)
    assert found == expect, f"MISMATCH ({found} vs {expect}): {old}"
    s = s.replace(old, new)
open(f, "w").write(s)
print("PATCHED OK")
EOF

python3 patch.py
cd ~/strategies_options/backtest
git add algotest_backtest.py
git commit -m "fix: candle lookback, SL high-trigger, lazy leg fill/exit per AlgoTest"
git pull origin master
git push origin master
python3 -c "
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak2')
s=open(f).read()
o='px, fts = m, cur'
assert s.count(o)==2, s.count(o)
open(f,'w').write(s.replace(o,'px, fts = sl_level, cur'))
print('OK')
"
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-31
cd ~/strategies_options/backtest
python3 -c "
from algotest_backtest import get_candles
d = get_candles('BTCUSD', '2025-01-01')
print(type(d), len(d) if d else d)
"
grep -n "def get_candles" algotest_backtest.py
python3 -c "
from algotest_backtest import get_candles
d = get_candles('BTCUSD', '2025-01-01', '2025-01-01')
print(type(d), len(d) if d else d)
"
sed -n '45,80p' algotest_backtest.py
cgrep -n "argparse\|add_argument\|strptime\|mktime" algotest_backtest.py | head -20
grep -n "argparse\|add_argument\|strptime\|mktime" algotest_backtest.py | head -20
sed -n '525,560p' algotest_backtest.py
grep -n "NO_DATA" algotest_backtest.py
sed -n '220,260p' algotest_backtest.py
grep -n "^BASE\|^SPOT\|^STEP" algotest_backtest.py
python3 -c "
import requests, datetime
d = datetime.date(2025,1,1)
entry_ts = int(datetime.datetime(2025,1,1,9,20).timestamp())
exit_ts = int(datetime.datetime(2025,1,1,17,29).timestamp())
r = requests.get('https://api.india.delta.exchange/v2/history/candles', params={'symbol':'.DEXBTUSD','resolution':'1m','start':entry_ts,'end':exit_ts+120})
print(r.status_code)
print(r.json())
"
grep -n "def ts_of" -A 10 algotest_backtest.py
grep -n "^IST\|from datetime\|import datetime" algotest_backtest.py
python3 -c "
from datetime import date
from algotest_backtest import ts_of, get_candles, STEP
d = date(2025,1,1)
entry_ts = ts_of(d, 9, 20)
exit_ts = ts_of(d, 17, 29)
print('entry_ts', entry_ts, 'exit_ts', exit_ts)
sc = get_candles('.DEXBTUSD', entry_ts, exit_ts + 2*STEP)
print('len', len(sc))
"
grep -n "class Series" -A 30 algotest_backtest.py | head -40
python3 -c "
from datetime import date
from algotest_backtest import ts_of, get_candles, Series, STEP
d = date(2025,1,1)
entry_ts = ts_of(d, 9, 20)
exit_ts = ts_of(d, 17, 29)
sc = get_candles('.DEXBTUSD', entry_ts, exit_ts + 2*STEP)
s = Series(sc)
print('spot_px', s.mark_price(entry_ts))
print('first candle time', sc[0]['time'], 'entry_ts', entry_ts)
"
python3 -c "
s = open('algotest_backtest.py').read()
old = 'i = bisect.bisect_left(self.t, ts) - 1\n        return (None, None) if i < 0 else (self.c[i][\"close\"], ts - self.t[i])'
new = 'i = bisect.bisect_right(self.t, ts) - 1\n        return (None, None) if i < 0 else (self.c[i][\"close\"], ts - self.t[i])'
assert s.count(old) == 1, 'not found'
open('algotest_backtest.py','w').write(s.replace(old,new))
print('reverted mark_with_age to bisect_right')
"
Reverted. Now re-run: `python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-31`
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-31
python3 -c "
from algotest_backtest import ts_of, get_candles, premium_at
from datetime import date
d = date(2025,1,4)
cs = get_candles('P-BTC-97200-040125', ts_of(d,9,20), ts_of(d,17,29))
highs = [(c['time'], c['high']) for c in cs]
print(max(highs, key=lambda x: x[1]))
"
cd ~/strategies_options/backtest
python3 -c "
from algotest_backtest import ts_of, get_candles
from datetime import date
d = date(2025,1,4)
cs = get_candles('P-BTC-97200-040125', ts_of(d,9,20), ts_of(d,17,29))
print(max((c['time'], c['high']) for c in cs))
"
python3 -c "
from algotest_backtest import ts_of, premium_at
from datetime import date
d = date(2025,1,4)
print(premium_at('P', 97200, d, ts_of(d,9,20)))
"
sed -n '260,300p' algotest_backtest.py
grep -n "^def leg" -A 15 algotest_backtest.py
python3 algotest_backtest.py --start 2025-01-04 --end 2025-01-04
python3 -c "
from algotest_backtest import ts_of, premium_at
from datetime import date
d = date(2025,1,4)
print(premium_at('P', 97200, d, ts_of(d,9,20)))
"
python3 -c "
from algotest_backtest import ts_of, get_candles, premium_at, Series, SL_RECOST_PCT, MAX_MARK_AGE, STEP
from datetime import date
d = date(2025,1,4)
entry_ts = ts_of(d,9,20)
exit_ts = ts_of(d,17,29)
pr = premium_at('P', 97200, d, entry_ts)
s = Series(get_candles(pr[0], entry_ts, exit_ts + 2*STEP))
mkt = pr[1]
sl_level = mkt * (1 + SL_RECOST_PCT)
print('mkt', mkt, 'sl_level', sl_level)
cur = pr[2] + STEP
while cur < exit_ts:
    m, age = s.mark_with_age(cur)
    if m is not None and age <= MAX_MARK_AGE:
        peak = s.peak(cur)
        mm = max(m, peak)
        if mm >= sl_level:
            print('TRIGGER at', cur, 'm', m, 'peak', peak)
            break
    cur += STEP
else:
    print('no trigger')
"
python3 -c "
from algotest_backtest import get_candles
cs = get_candles('P-BTC-97200-040125', 1735983360-120, 1735983360+120)
for c in cs: print(c)
"
python3 -c "
from algotest_backtest import ts_of, get_candles
from datetime import date
d = date(2025,1,4)
cs = get_candles('P-BTC-97200-040125', ts_of(d,9,20), ts_of(d,17,29))
print(max((c['time'], c['high']) for c in cs))
print(len(cs))
"
python3 -c "
from algotest_backtest import get_candles
for i in range(2):
    cs = get_candles('P-BTC-97200-040125', 1735983360-120, 1735983360+120)
    for c in cs: print(i, c)
"
python3 -c "
import requests
r = requests.get('https://api.india.delta.exchange/v2/history/candles', params={'symbol':'P-BTC-97200-040125','resolution':'1m','start':1735962600,'end':1735991942})
d = r.json()['result']
print([c for c in d if c['time']==1735983360])
"
python3 -c "
from algotest_backtest import ts_of, get_candles, STEP
from datetime import date
d = date(2025,1,4)
entry_ts = ts_of(d,9,20)
exit_ts = ts_of(d,17,29)
cs = get_candles('P-BTC-97200-040125', entry_ts, exit_ts + 2*STEP)
spike = [c for c in cs if c['time']==1735983360]
print('spike found:', spike)
print(max((c['time'], c['high']) for c in cs))
"
cd ~/strategies_options/backtest
python3 -c "
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak3')
s=open(f).read()
o='m, age = ml[\"series\"].mark_with_age(exit_ts)\n                        if m is None or age > MAX_MARK_AGE:\n                            unsettled = True\n                            break\n'
n='m, age = ml[\"series\"].mark_with_age(exit_ts)\n                        if m is None or age > MAX_MARK_AGE:\n                            m = 0.11\n'
assert s.count(o)==1
open(f,'w').write(s.replace(o,n)); print('OK1')
"
python3 -c "
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak4')
s=open(f).read()
o1='''    def mark_with_age(self, ts):
        i = bisect.bisect_left(self.t, ts) - 1
        return (None, None) if i < 0 else (self.c[i][\"close\"], ts - self.t[i])
'''
n1='''    def _spike(self, i):
        if i <= 0 or i + 1 >= len(self.c):
            return None
        p, c, n = self.c[i-1][\"close\"], self.c[i][\"close\"], self.c[i+1][\"close\"]
        return max(p, n) if (c > 2*p and c > 2*n) else None

    def mark_with_age(self, ts):
        i = bisect.bisect_left(self.t, ts) - 1
        if i < 0:
            return (None, None)
        sp = self._spike(i)
        return (sp if sp is not None else self.c[i][\"close\"], ts - self.t[i])
'''
o2='''        return self.c[i][\"high\"] if i >= 0 else 0
'''
n2='''        if i < 0:
            return 0
        sp = self._spike(i)
        return sp if sp is not None else self.c[i][\"high\"]
'''
assert s.count(o1)==1 and s.count(o2)==1
open(f,'w').write(s.replace(o1,n1).replace(o2,n2)); print('OK2')
"
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-31 > out.txt
grep '09:20\] 2025-01-04' out.txt | head -1
tail -60 out.txt
grep -n "def mark_with_age" -A 3 algotest_backtest.py
python3 -c "
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak4')
s=open(f).read()
o1='''    def mark_with_age(self, ts):
        i = bisect.bisect_right(self.t, ts) - 1
        return (None, None) if i < 0 else (self.c[i][\"close\"], ts - self.t[i])
'''
n1='''    def _spike(self, i):
        if i <= 0 or i + 1 >= len(self.c):
            return None
        p, c, n = self.c[i-1][\"close\"], self.c[i][\"close\"], self.c[i+1][\"close\"]
        return max(p, n) if (c > 2*p and c > 2*n) else None

    def mark_with_age(self, ts):
        i = bisect.bisect_right(self.t, ts) - 1
        if i < 0:
            return (None, None)
        sp = self._spike(i)
        return (sp if sp is not None else self.c[i][\"close\"], ts - self.t[i])
'''
o2='''        return self.c[i][\"high\"] if i >= 0 else 0
'''
n2='''        if i < 0:
            return 0
        sp = self._spike(i)
        return sp if sp is not None else self.c[i][\"high\"]
'''
assert s.count(o1)==1 and s.count(o2)==1
open(f,'w').write(s.replace(o1,n1).replace(o2,n2)); print('OK2')
"
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-07 > out.txt
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-07
grep -n 'px, fts = sl_level, cur\|lz\["leg"\]\["raw"\]\|ef = lz\["trail_sl"\]\|def ' algotest_backtest.py | grep -B2 -A2 'px, fts\|lz\['
cd ~/strategies_options/backtest
grep -n 'px, fts = sl_level, cur\|lz\["leg"\]\["raw"\]\|ef = lz\["trail_sl"\]\|def ' algotest_backtest.py | grep -B2 -A2 'px, fts\|lz\['
python3 -c "
lines = open('algotest_backtest.py').read().splitlines()
for a,b in [(280,315),(400,470)]:
    print(f'=== {a}-{b} ===')
    for i in range(a-1,b):
        print(i+1, lines[i])
"
cd ~/strategies_options/backtest
python3 - <<'PYEOF'
import shutil
f = 'algotest_backtest.py'
shutil.copy(f, f + '.bak6')
s = open(f).read()

def rep(o, n, c=1):
    assert s.count(o) == c, (s.count(o), repr(o))
    return s.replace(o, n)

# 1. add open_at() right before fill_at()
o = '    def fill_at(self, ts):'
n = '''    def open_at(self, ts):
        i = bisect.bisect_left(self.t, ts)
        if i >= len(self.c) or self.c[i]["time"] - ts > 300:
            return None
        return self.c[i]["open"]

    def fill_at(self, ts):'''
s = rep(o, n)

# 2. recost (sl) + lazy3-main (ml) SL fill: worse of trigger level and next open
o = 'px, fts = sl_level, cur'
assert s.count(o) == 2
s = s.replace(o, 'px, fts = max(sl_level, sl["series"].open_at(cur) or sl_level), cur', 1)
s = s.replace(o, 'px, fts = max(sl_level, ml["series"].open_at(cur) or sl_level), cur', 1)

# 3. lazy leg entry/exit fill: use next-candle open, not exact trigger/trail level
o = 'px, fts = lz["series"].fill_at(cur)'
assert s.count(o) == 2
s = s.replace(o, 'px, fts = lz["series"].open_at(cur)', 2)

# 4. lazy entry raw price uses actual fill, not exact trigger
o = 'lz["leg"]["raw"] = lz["trig"] * (1 + SLIP)'
s = rep(o, 'lz["leg"]["raw"] = px * (1 + SLIP)')

# 5. lazy exit: worse of actual fill price and trail_sl level
o = 'ef = lz["trail_sl"] * (1 - SLIP)'
s = rep(o, 'ef = min(px, lz["trail_sl"]) * (1 - SLIP)')

open(f, 'w').write(s)
print('OK')
PYEOF

python3 -m py_compile algotest_backtest.py && echo SYNTAX_OK
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-07 > out_real.txt; echo EXIT=$?; grep -i error out_real.txt; grep SUMMARY out_real.txt
cd ~/strategies_options/backtest
python3 - <<'PYEOF'
import shutil
f = 'algotest_backtest.py'
shutil.copy(f, f + '.bak7')
s = open(f).read()
o = 'px, fts = lz["series"].open_at(cur)'
assert s.count(o) == 2, s.count(o)
s = s.replace(o, 'px, fts = lz["series"].open_at(cur), cur')
open(f, 'w').write(s)
print('OK')
PYEOF

python3 -m py_compile algotest_backtest.py && echo SYNTAX_OK
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-07 > out_real.txt; echo EXIT=$?; grep -i error out_real.txt; grep SUMMARY out_real.txt
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-07 2>&1 | tee out_real.txt
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-07
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak6')
s=open(f).read()
o='px, fts = lz["series"].fill_at(cur)'
assert s.count(o)==2, s.count(o)
s=s.replace(o,'px = lz["series"].open_at(cur); fts = cur')
o2='lz["leg"]["raw"] = px * (1 + SLIP)'
assert s.count(o2)==1
s=s.replace(o2,'lz["leg"]["raw"] = max(px, lz["trig"]) * (1 + SLIP)')
open(f,'w').write(s); print('OK')
E

python3 -m py_compile algotest_backtest.py && echo SYNTAX_OK
grep -n 'open_at(cur)\|lz\["leg"\]\["raw"\] = ' algotest_backtest.py
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak8')
s=open(f).read()
o='lz["leg"]["raw"] = px * (1 + SLIP)'
assert s.count(o)==1
s=s.replace(o,'lz["leg"]["raw"] = max(px, lz["trig"]) * (1 + SLIP)')
open(f,'w').write(s); print('OK')
E

python3 -m py_compile algotest_backtest.py && echo SYNTAX_OK
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-07 > out_real.txt; grep SUMMARY out_real.txt
python3 algotest_backtest.py --start 2025-01-01 --end 2025-01-07
grep -n "exp = d + \|SLIP = " algotest_backtest.py
cd ~/strategies_options/backtest
grep -n "exp = d + \|SLIP = " algotest_backtest.py
grep -n "exp = d + \|SLIP = " algotest_backtest.py
cd ~/strategies_options/backtest
grep -n "exp = d + \|SLIP = " algotest_backtest.py
cp algotest_backtest.py algotest_backtest.py.bak9
sed -i 's/exp = d + timedelta(days=2 if entry_h == 19 else 1)/exp = d + timedelta(days=1)/' algotest_backtest.py
sed -i 's/^SLIP = 0.05/SLIP = 0.03/' algotest_backtest.py
grep -n "exp = d + \|SLIP = " algotest_backtest.py
git add algotest_backtest.py
git commit -m "Fix 19:00 expiry to d+1, SLIP=0.03"
git push origin master
git pull origin master
grep -n "variant\|argparse\|add_argument" algotest_backtest.py | head -30
cd ~/strategies_options/backtest
grep -n "variant\|argparse\|add_argument" algotest_backtest.py | head -30
sed -n '520,560p' algotest_backtest.py
python3 algotest_backtest.py --start 2026-08-01 --end 2026-08-31 2>&1 | tee out_aug26.txt
grep -i "19:00\|\[.*19.*\]" out_aug26.txt | head -40
python3 algotest_backtest.py --start 2026-08-01 --end 2026-08-31
python3 algotest_backtest.py --start 2026-10-01 --end 2026-10-31 | grep "19:00"
grep -n "MULT_MAIN\|MULT_LAZY\|^CV\|^CAP\b" algotest_backtest.py
cd ~/strategies_options/backtest
grep -n "MULT_MAIN\|MULT_LAZY\|^CV\|^CAP\b" algotest_backtest.py
grep -n "LOTS_MAIN\|LOTS_LAZY" algotest_backtest.py
sed -n '358,400p' algotest_backtest.py
cd ~/strategies_options/backtest
sed -n '358,400p' algotest_backtest.py
grep -n "def get_candles\|resolution" algotest_backtest.py
cd ~/strategies_options/backtest
grep -n "def get_candles\|resolution" algotest_backtest.py
sed -n '400,460p' algotest_backtest.py
cd ~/strategies_options/backtest
sed -n '400,460p' algotest_backtest.py
sed -n '460,520p' algotest_backtest.py
cp algotest_backtest.py algotest_backtest.py.bak10
sed -i 's/lz\["leg"\]\["raw"\] = max(px, lz\["trig"\]) \* (1 + SLIP)/lz["leg"]["raw"] = px * (1 + SLIP)/' algotest_backtest.py
grep -n 'lz\["leg"\]\["raw"\]' algotest_backtest.py
python3 algotest_backtest.py --start 2026-08-01 --end 2026-08-31 | grep "19:00"
python3 algotest_backtest.py --start 2026-08-01 --end 2026-08-31
anildalabanjan7@instance-20260905-001123:~/strategies_options/backtest$ python3 algotest_backtest.py --start 2026-08-01 --end 2026-08-31
WINDOW 2026-08-01 to 2026-08-31 | strategies=[strangle_recost x3, btst_lazy3 x4]
[strangle_recost 09:20] 2026-08-01 C=64000@2 P=62000@2 re(C,P)=(1,1) pnl=$-3.80 equity=$223.20
[strangle_recost 09:20] 2026-08-03 C=64000@14 P=62000@16 re(C,P)=(0,1) pnl=$-3.55 equity=$219.65
cp algotest_backtest.py algotest_backtest.py.bak11
sed -i 's/^LAZY3_TIMES = .*/LAZY3_TIMES = [(19, 0, 4)]/' algotest_backtest.py
sed -i 's/^RECOST_TIMES = .*/RECOST_TIMES = []/' algotest_backtest.py
grep -n "LAZY3_TIMES\|RECOST_TIMES" algotest_backtest.py
python3 algotest_backtest.py --start 2026-08-01 --end 2026-08-31
[200~cp algotest_backtest.py.bak11 algotest_backtest.py.tmp
git diff algotest_backtest.py.bak11 algotest_backtest.py
~
sed -i 's/^RECOST_TIMES = .*/RECOST_TIMES = [(9, 20), (10, 20), (11, 20)]/' algotest_backtest.py
sed -i 's/^LAZY3_TIMES = .*/LAZY3_TIMES = [(19, 0, 4), (9, 20, 1), (10, 20, 1), (11, 20, 1)]/' algotest_backtest.py
grep -n "RECOST_TIMES\|LAZY3_TIMES" algotest_backtest.py
rm -f algotest_backtest.py.tmp
git add algotest_backtest.py
git commit -m "Fix lazy leg entry fill - remove trigger floor"
git push origin master
grep -n "debug\|DEBUG" algotest_backtest.py | head -5
grep -n "args.debug" algotest_backtest.py
sed -n '459,465p' algotest_backtest.py
cp algotest_backtest.py algotest_backtest.py.bak12
sed -i '464a\                                        if args.debug: print(f"  LAZY_ARM {side} strike={lz[\x27leg\x27][\x27symbol\x27]} entry_px={lz[\x27leg\x27][\x27raw\x27]:.2f} ts={fts}")' algotest_backtest.py
sed -n '459,467p' algotest_backtest.py
grep -n "lzstate\[.pnl.\] += ef\|lzstate\[.count.\] += 1" algotest_backtest.py
sed -i '475a\                                    if args.debug: print(f"  LAZY_EXIT {side} exit_px={ef:.2f} pnl={ef - lz[\x27leg\x27][\x27raw\x27]:.2f} ts={fts}")' algotest_backtest.py
grep -n "lzstate\[.count.\] += 1" algotest_backtest.py
sed -i '489a\                                    if args.debug: print(f"  LAZY_REENTRY {side} count={lzstate[\x27count\x27]} new_trig={inst[\x27trig\x27]:.2f}")' algotest_backtest.py
sed -n '486,491p' algotest_backtest.py
python3 algotest_backtest.py --start 2026-08-19 --end 2026-08-20 --debug
grep -n "trig\b" algotest_backtest.py
grep -n '"mkt"' algotest_backtest.py | head -10
nohup python3 algotest_backtest.py --start 2024-01-01 --end 2026-10-20 > out_full.txt 2>&1 &
disown
tail -50 out_full.txt
cd ~/strategies_options/backtest
nohup python3 algotest_backtest.py --start 2024-01-01 --end 2026-10-20 > out_full.txt 2>&1 &
disown
ps -p 3943833
tail -50 out_full.txt
cd ~/strategies_options/backtest
tail -50 out_full.txt
wc -l out_full.txt
tail -1 out_full.txt
grep -c "^SUMMARY" out_full.txt
grep "^SUMMARY" out_full.txt
grep -oP '\] \d{4}-\d{2}-\d{2}.*pnl=\$-?[0-9.]+' out_full.txt | awk '{split($2,d,"-"); m=d[1]"-"d[2]; for(i=1;i<=NF;i++){if($i~/^pnl=/){gsub("pnl=\\$","",$i); sum[m]+=$i}}} END{for(m in sum) print m, sum[m]}' | sort
grep -oP '^\[[^\]]+\] \d{4}-\d{2}-\d{2}.*pnl=\$-?[0-9.]+' out_full.txt | sed -E 's/^\[([^]]+)\] (\d{4}-\d{2})-\d{2}.*pnl=\$(-?[0-9.]+).*/\1|\2|\3/' | awk -F'|' '{sum[$1"|"$2]+=$3} END{for(k in sum) print k, sum[k]}' | sort
grep -oP '^\[\S+ \S+\]( \S+)? \d{4}-\d{2}-\d{2}.*pnl=\$-?[0-9.]+' out_full.txt | awk '{
  variant=$1" "$2; gsub(/[\[\]]/,"",variant);
  for(i=1;i<=NF;i++){ if($i ~ /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/){ split($i,d,"-"); m=d[1]"-"d[2] } }
  for(i=1;i<=NF;i++){ if($i~/^pnl=/){ gsub("pnl=\\$","",$i); sum[variant"|"m]+=$i } }
} END{ for(k in sum){ split(k,p,"|"); printf "%-25s %s %10.2f\n", p[1], p[2], sum[k] } }' out_full.txt | sort -k1,1 -k2,2
grep -E "^\[btst_lazy3 19:00\] 2026-08-(0[1-9]|[12][0-9]|3[01])" out_full.txt
grep -E "^\[btst_lazy3 19:00\] 2026-08-" out_full.txt
pwd
ls ~/strategies_options/backtest/out_full.txt
cd ~/strategies_options/backtest
grep -o "^\[btst_lazy3[^]]*\]" out_full.txt | sort -u
grep "^\[btst_lazy3 19:00\]" out_full.txt | tail -5
grep "^\[btst_lazy3 19:00\]" out_full.txt | wc -l
grep "^\[btst_lazy3 19:00\] 2026-0" out_full.txt | cut -d' ' -f2 | cut -c1-7 | sort -u
grep "^\[btst_lazy3 19:00\] 2026-" out_full.txt | awk '{print $3}' | cut -c1-7 | sort -u
grep "2026-08" out_full.txt | grep -i "btst_lazy3 19:00"
grep "2026-08" out_full.txt | grep "btst_lazy3 19:00" | grep -oP 'pnl=\$-?[0-9.]+' | sed 's/pnl=\$//' | awk '{s+=$1} END{print s}'
grep -n "bisect_right(self.t, ts)" algotest_backtest.py
grep -n 'lz\["series"\].peak(cur)' algotest_backtest.py
cd ~/strategies_options/backtest
grep -n "bisect_right(self.t, ts)" algotest_backtest.py
grep -n 'lz\["series"\].peak(cur)' algotest_backtest.py
sed -n '110,140p' algotest_backtest.py
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak9')
s=open(f).read()
a='i = bisect.bisect_right(self.t, ts) - 1\n        if i < 0:\n            return (None, None)'
b='if max(m, lz["series"].peak(cur)) >= lz["trig"]:'
assert s.count(a)==1 and s.count(b)==1
s=s.replace(a,a.replace('bisect_right','bisect_left')).replace(b,'if m >= lz["trig"]:')
open(f,'w').write(s); print('OK')
E

grep -n "bisect_left(self.t, ts) - 1" algotest_backtest.py
grep -n 'if m >= lz\["trig"\]:' algotest_backtest.py
python3 algotest_backtest.py --start 2026-08-01 --end 2026-08-31 > out_aug.txt; grep "btst_lazy3 19:00\] 2026-08-\(22\|27\)" out_aug.txt
grep "2026-08-26" out_aug.txt | grep "btst_lazy3 19:00"
wc -l out_aug.txt
grep -c "btst_lazy3 19:00" out_aug.txt
grep "btst_lazy3 19:00" out_aug.txt | head -5
cat out_aug.txt
grep -n "NO_DATA" algotest_backtest.py | head -20
sed -n '250,270p' algotest_backtest.py
sed -n '365,385p' algotest_backtest.py
001123:~/strategies_options/backtest$ ^C
anildalabanjan7@instance-20260905-001123:~/strategies_options/backtest$ sed -n '250,270p' algotest_backtest.py
sed -n '365,385p' algotest_backtest.py
anildalabanjan7@instance-20260905-001123:~/strategies_options/backtest$grep -n "get_candles(SPOT, entry_ts" algotest_backtest.py
grep -n "get_candles(SPOT, entry_ts" algotest_backtest.py
grep -n "mark_price\|mark_with_age" algotest_backtest.py
sed -n '256,267p' algotest_backtest.py
sed -n '370,380p' algotest_backtest.py
grep -n "^STEP" algotest_backtest.py
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak10')
s=open(f).read()
old='sc = get_candles(SPOT, entry_ts, exit_ts + 2 * STEP)'
n=s.count(old)
assert n==2, f"expected 2, got {n}"
s=s.replace(old, 'sc = get_candles(SPOT, entry_ts - STEP, exit_ts + 2 * STEP)')
open(f,'w').write(s); print('OK', n)
E

python3 algotest_backtest.py --start 2026-08-01 --end 2026-08-31 > out_aug.txt; cat out_aug.txt
cat out_aug.txt
grep "btst_lazy3 19:00\] 2026-08-\(22\|27\)" out_aug.txt
tail -5 out_aug.txt
grep -c "btst_lazy3 19:00" out_aug.txt
grep -n "bisect_left(self.t, ts) - 1" algotest_backtest.py
grep -n 'if m >= lz\["trig"\]:' algotest_backtest.py
ps aux | grep algotest_backtest
jobs
grep -c "btst_lazy3 19:00" out_aug.txt
wc -l out_aug.txt
tail -10 out_aug.txt
python3 algotest_backtest.py --start 2026-08-01 --end 2026-08-31 | grep "btst_lazy3 19:00\] 2026-08-\(22\|27\)"
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 | grep --line-buffered "btst_lazy3 19:00\] 2026-08-\(22\|27\)"
anildalabanjan7@instance-20260905-001123:~/strategies_options/backtest$ 
sed -n '450,465p' algotest_backtest.py
grep -n '"trig"\]' algotest_backtest.py | head -20
grep -n '"trig"' algotest_backtest.py
sed -n '415,430p' algotest_backtest.py
grep -n '"mkt"' algotest_backtest.py
grep -n "^SLIP" algotest_backtest.py
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak11')
s=open(f).read()
old='SLIP = 0.03'
n=s.count(old)
assert n==1, f"expected 1, got {n}"
s=s.replace(old, 'SLIP = 0.05')
open(f,'w').write(s); print('OK')
E

python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31
grep -n "_spike" algotest_backtest.py
sed -n '100,116p' algotest_backtest.py
git add algotest_backtest.py
git commit -m "Fix lookahead bugs: causal _spike(), remove wick-based SL arming"
git push origin master
git add strategies_options/backtest/algotest_backtest.py
git commit -m "Fix lookahead bugs: causal _spike(), remove wick-based SL arming"
git push origin master
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak12')
s=open(f).read()
old='''    def _spike(self, i):
        if i <= 0 or i + 1 >= len(self.c):
            return None
        p, c, n = self.c[i-1]["close"], self.c[i]["close"], self.c[i+1]["close"]
        return max(p, n) if (c > 2*p and c > 2*n) else None'''
n=s.count(old)
assert n==1, f"got {n}"
new='''    def _spike(self, i):
        if i <= 0:
            return None
        p, c = self.c[i-1]["close"], self.c[i]["close"]
        return p if (c > 2*p) else None'''
s=s.replace(old,new)
open(f,'w').write(s); print('OK')
E

cd ~/strategies_options/backtest
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak12')
s=open(f).read()
old='''    def _spike(self, i):
        if i <= 0 or i + 1 >= len(self.c):
            return None
        p, c, n = self.c[i-1]["close"], self.c[i]["close"], self.c[i+1]["close"]
        return max(p, n) if (c > 2*p and c > 2*n) else None'''
n=s.count(old)
assert n==1, f"got {n}"
new='''    def _spike(self, i):
        if i <= 0:
            return None
        p, c = self.c[i-1]["close"], self.c[i]["close"]
        return p if (c > 2*p) else None'''
s=s.replace(old,new)
open(f,'w').write(s); print('OK')
E

grep -n "lazy\[" algotest_backtest.py | head -20
sed -n '435,452p' algotest_backtest.py
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak13')
s=open(f).read()
old='                            m = max(m, ml["series"].peak(cur))\n                            if m >= sl_level:'
n=s.count(old)
assert n==1, f"got {n}"
s=s.replace(old, '                            if m >= sl_level:')
open(f,'w').write(s); print('OK')
E

python3 -u algotest_backtest.py --start 2026-08-01 --end 2
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 > out_aug.txt 2>&1
grep "btst_lazy3 19:00\] 2026-08-\(22\|27\)" out_aug.txt
tail -5 out_aug.txt
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31
python3 algotest_backtest.py --start 2026-08-22 --end 2026-08-22 --debug 2>&1 | grep -i "lazy\|SL\|ARM"
python3 -c "from datetime import datetime,timezone; print(datetime.fromtimestamp(1787472000,tz=timezone.utc))"
python3 algotest_backtest.py --start 2026-08-22 --end 2026-08-22 --debug 2>&1 | grep -i "P-BTC-74800\|main\|SL_level\|mkt"
grep -n "if args.debug" algotest_backtest.py
sed -n '439,448p' algotest_backtest.py
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak14')
s=open(f).read()
old='''                            if m >= sl_level:
                                px, fts = max(sl_level, ml["series"].open_at(cur) or sl_level), cur'''
n=s.count(old)
assert n==1, f"got {n}"
new='''                            if m >= sl_level:
                                px, fts = max(sl_level, ml["series"].open_at(cur) or sl_level), cur
                                if args.debug: print(f"  MAIN_SL {side} entry_mkt={l['mkt']:.2f} sl_level={sl_level:.2f} fill_px={px:.2f} ts={fts}")'''
s=s.replace(old,new)
open(f,'w').write(s); print('OK')
E

python3 algotest_backtest.py --start 2026-08-22 --end 2026-08-22 --debug 2>&1 | grep -i "MAIN_SL\|LAZY_ARM"
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak15')
s=open(f).read()
old='''                            if m >= sl_level:
                                px, fts = max(sl_level, ml["series"].open_at(cur) or sl_level), cur
                                if args.debug: print(f"  MAIN_SL {side} entry_mkt={l['mkt']:.2f} sl_level={sl_level:.2f} fill_px={px:.2f} ts={fts}")'''
n=s.count(old)
assert n==1, f"got {n}"
new='''                            if m >= sl_level:
                                px, fts = max(sl_level, ml["series"].open_at(cur) or sl_level), cur'''
s=s.replace(old,new)
open(f,'w').write(s); print('OK')
E

git add algotest_backtest.py
git commit -m "Remove temp debug instrumentation"
git push origin master
grep -n "LAZY_REENTRY\|elif lz and lz\[.done.\]" algotest_backtest.py
sed -n '478,495p' algotest_backtest.py
cd ~/strategies_options/backtest
grep -n "LAZY_REENTRY\|elif lz and lz\[.done.\]" algotest_backtest.py
sed -n '478,495p' algotest_backtest.py
grep -n "def spawn_lazy" algotest_backtest.py
sed -n '460,480p' algotest_backtest.py
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak16')
s=open(f).read()
old = '''                                    lz["done"] = True
                                    lzstate["last_exit_px"] = ef
                    elif lz and lz["done"] and lzstate["count"] < 4:
                        m2, age2 = lz["series"].mark_with_age(cur)
                        if m2 is not None and age2 <= MAX_MARK_AGE and lzstate["last_exit_px"]:
                            if m2 >= lzstate["last_exit_px"] * 2:
                                inst = spawn_lazy(side, cur)
                                if inst:
                                    inst["armed"] = True
                                    lzstate["cur"] = inst
                                    lzstate["fee"] += inst["fee_real"]
                                    lzstate["count"] += 1
                                    if args.debug: print(f"  LAZY_REENTRY {side} count={lzstate['count']} new_trig={inst['trig']:.2f}")'''
n = s.count(old)
assert n == 1, f"got {n}"
new = '''                                    lz["done"] = True
                                    lzstate["last_exit_px"] = ef
                                    if lzstate["count"] < 4:
                                        inst = spawn_lazy(side, fts)
                                        if inst:
                                            lzstate["cur"] = inst
                                            lzstate["fee"] += inst["fee_real"]
                                            lzstate["count"] += 1
                                            if args.debug: print(f"  LAZY_REENTRY {side} count={lzstate['count']} pending strike={inst['leg']['symbol']} trig={inst['trig']:.2f}")'''
s = s.replace(old, new)
open(f,'w').write(s); print('OK')
E

python3 algotest_backtest.py --start 2026-08-01 --end 2026-08-31 --debug > out_aug.txt 2>&1
grep "btst_lazy3 19:00\] 2026-08-\(19\|10\|11\)" out_aug.txt
tail -20 out_aug.txt
grep "btst_lazy3 19:00\] 2026-08-\(19\|10\|11\)" out_aug.txt
tail -5 out_aug.txt
python3 algotest_backtest.py --start 2026-08-01 --end 2026-08-31 --debug > out_aug.txt 2>&1
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 --debug 2>&1 | tee out_aug.txt
git add algotest_backtest.py
git commit -m "Fix Bug A: lazy re-entry spawns fresh OTM5 instrument instead of reusing old strike"
git push origin master
git add strategies_options/backtest/algotest_backtest.py
git commit -m "Fix Bug A: lazy re-entry spawns fresh OTM5 instrument instead of reusing old strike"
git push origin master
grep -n "MULT_LAZY\|qty_mult" algotest_backtest.py | head -10
sed -n '479,486p' algotest_backtest.py
cd ~/strategies_options/backtest
sed -n '479,486p' algotest_backtest.py
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak17')
s=open(f).read()
old = '''                                    if lzstate["count"] < 4:
                                        inst = spawn_lazy(side, fts)
                                        if inst:
                                            lzstate["cur"] = inst
                                            lzstate["fee"] += inst["fee_real"]
                                            lzstate["count"] += 1'''
n = s.count(old)
assert n == 1, f"got {n}"
new = '''                                    if lzstate["count"] < 4:
                                        inst = spawn_lazy(side, fts)
                                        if inst:
                                            lzstate["cur"] = inst
                                            lzstate["count"] += 1'''
s = s.replace(old, new)
open(f,'w').write(s); print('OK')
E

sed -n '479,485p' algotest_backtest.py
git add algotest_backtest.py
git commit -m "Fix duplicate fee charge on lazy re-entry spawn"
git push origin master
grep -n "MULT_LAZY\|qty_mult" algotest_backtest.py | head -10
grep -n "^LOTS_LAZY\|^LOTS_MAIN\|run_lazy3_variant(h, m, a, b, qty_mult=qm)" algotest_backtest.py
grep -n "qm = \|qm=" algotest_backtest.py
sed -n '540,555p' algotest_backtest.py
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 --debug 2>&1 | tee out_aug.txt
sed -n '453,476p' algotest_backtest.py
cd ~/strategies_options/backtest
sed -n '453,476p' algotest_backtest.py
grep -n "def peak\|def open_at\|def mark_with_age" algotest_backtest.py
python3 - <<'E'
import shutil
f='algotest_backtest.py'; shutil.copy(f,f+'.bak18')
s=open(f).read()

# Part 1: add low_at method after peak()
old1 = '''    def peak(self, ts):
        i = bisect.bisect_left(self.t, ts) - 1
        if i < 0:
            return 0
        sp = self._spike(i)
        return sp if sp is not None else self.c[i]["high"]'''
n1 = s.count(old1)
assert n1 == 1, f"peak block: got {n1}"
new1 = old1 + '''

    def low_at(self, ts):
        i = bisect.bisect_left(self.t, ts) - 1
        return None if i < 0 else self.c[i]["low"]'''
s = s.replace(old1, new1)

# Part 2+3: arm block + trail/exit block
old2 = '''                            if not lz["armed"]:
                                if m >= lz["trig"]:
                                    px, fts = lz["series"].open_at(cur), cur
                                    if px is not None:
                                        lz["leg"]["raw"] = px * (1 + SLIP)
                                        lz["trail_sl"] = lz["leg"]["raw"] - SL_LAZY_PTS
                                        lz["armed"] = True
                                        lzstate["fee"] += lz["fee_real"]
                                        if args.debug: print(f"  LAZY_ARM {side} strike={lz['leg']['symbol']} entry_px={lz['leg']['raw']:.2f} ts={fts}")
                                continue
                            if m - lz["leg"]["raw"] >= TRAIL_MOVE:
                                steps = int((m - lz["leg"]["raw"]) // TRAIL_MOVE)
                                lz["trail_sl"] = max(lz["trail_sl"], lz["leg"]["raw"] - SL_LAZY_PTS + steps * TRAIL_STEP)
                            if m <= lz["trail_sl"]:
                                px, fts = lz["series"].open_at(cur), cur
                                if px is not None:
                                    ef = px * (1 - SLIP)
                                    ef = min(px, lz["trail_sl"]) * (1 - SLIP)
                                    lzstate["pnl"] += ef - lz["leg"]["raw"]
                                    if args.debug: print(f"  LAZY_EXIT {side} exit_px={ef:.2f} pnl={ef - lz['leg']['raw']:.2f} ts={fts}")
                                    lzstate["fee"] += fee(spot_at(spot_series, fts, spot_px), ef)'''
n2 = s.count(old2)
assert n2 == 1, f"arm/exit block: got {n2}"
new2 = '''                            if not lz["armed"]:
                                if max(m, lz["series"].peak(cur)) >= lz["trig"]:
                                    lz["leg"]["raw"] = lz["trig"] * 1.005
                                    lz["trail_sl"] = lz["leg"]["raw"] - SL_LAZY_PTS
                                    lz["armed"] = True
                                    lzstate["fee"] += lz["fee_real"]
                                    if args.debug: print(f"  LAZY_ARM {side} strike={lz['leg']['symbol']} entry_px={lz['leg']['raw']:.2f} ts={cur}")
                                continue
                            mp = max(m, lz["series"].peak(cur))
                            if mp - lz["leg"]["raw"] >= TRAIL_MOVE:
                                steps = int((mp - lz["leg"]["raw"]) // TRAIL_MOVE)
                                lz["trail_sl"] = max(lz["trail_sl"], lz["leg"]["raw"] - SL_LAZY_PTS + steps * TRAIL_STEP)
                            lo = lz["series"].low_at(cur)
                            if lo is not None and lo <= lz["trail_sl"]:
                                px, fts = lz["trail_sl"], cur
                                if px is not None:
                                    ef = px
                                    lzstate["pnl"] += ef - lz["leg"]["raw"]
                                    if args.debug: print(f"  LAZY_EXIT {side} exit_px={ef:.2f} pnl={ef - lz['leg']['raw']:.2f} ts={fts}")
                                    lzstate["fee"] += fee(spot_at(spot_series, fts, spot_px), ef)'''
s = s.replace(old2, new2)

open(f,'w').write(s); print('OK', n1, n2)
E

sed -n '122,135p' algotest_backtest.py
sed -n '453,478p' algotest_backtest.py
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 --debug 2>&1 | tee out_aug.txt
git add algotest_backtest.py
git commit -m "Fix lazy arm/exit: use wick-peak trigger with 1.005x fill, low-touch stop instead of close-based fill"
git push origin master
grep "btst_lazy3 19:00\]" out_aug.txt | grep -v "2026-08-01\|2026-08-26" | grep -oP 'pnl=\$-?[0-9.]+' | sed 's/pnl=\$//' | awk '{s+=$1} END{print s}'
cd ~/strategies_options/backtest
grep "btst_lazy3 19:00\]" out_aug.txt | grep -v "2026-08-01\|2026-08-26" | grep -oP 'pnl=\$-?[0-9.]+' | sed 's/pnl=\$//' | awk '{s+=$1} END{print s}'
python3 - <<'EOF'
import re
f = "algotest_backtest.py"
s = open(f).read()
old = '''                            mp = max(m, lz["series"].peak(cur))
                            if mp - lz["leg"]["raw"] >= TRAIL_MOVE:
                                steps = int((mp - lz["leg"]["raw"]) // TRAIL_MOVE)
                                lz["trail_sl"] = max(lz["trail_sl"], lz["leg"]["raw"] - SL_LAZY_PTS + steps * TRAIL_STEP)
                            lo = lz["series"].low_at(cur)
                            if lo is not None and lo <= lz["trail_sl"]:'''
new = '''                            lo = lz["series"].low_at(cur)
                            if lo is not None and lo <= lz["trail_sl"]:'''
assert old in s, "OLD BLOCK NOT FOUND"
s = s.replace(old, new, 1)
old2 = '''                                            if args.debug: print(f"  LAZY_REENTRY {side} count={lzstate['count']} pending strike={inst['leg']['symbol']} trig={inst['trig']:.2f}")
                cur += STEP'''
new2 = '''                                            if args.debug: print(f"  LAZY_REENTRY {side} count={lzstate['count']} pending strike={inst['leg']['symbol']} trig={inst['trig']:.2f}")
                                continue
                            mp = max(m, lz["series"].peak(cur))
                            if mp - lz["leg"]["raw"] >= TRAIL_MOVE:
                                steps = int((mp - lz["leg"]["raw"]) // TRAIL_MOVE)
                                lz["trail_sl"] = max(lz["trail_sl"], lz["leg"]["raw"] - SL_LAZY_PTS + steps * TRAIL_STEP)
                cur += STEP'''
assert old2 in s, "OLD2 BLOCK NOT FOUND"
s = s.replace(old2, new2, 1)
open(f, "w").write(s)
print("PATCHED OK")
EOF

python3 algotest_backtest.py --start 2026-08-01 --end 2026-08-31 --debug 2>&1 | grep -E "btst_lazy3 19:00|LAZY_" | tee out_aug.txt
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 --debug 2>&1 | grep -E --line-buffered "btst_lazy3 19:00|LAZY_" | tee out_aug.txt
python3 -u -c "
from algotest_backtest import run_lazy3_variant
from datetime import date
run_lazy3_variant(19, 0, date(2026,8,1), date(2026,8,31), qty_mult=4)
" 2>&1 | grep -E --line-buffered "btst_lazy3 19:00|LAZY_" | tee out_aug.txt
grep -n "def spawn_lazy" -A 20 algotest_backtest.py
sed -n '435,480p' algotest_backtest.py
grep -n "^STEP\|STEP =" algotest_backtest.py | head -5
grep "2026-08-19" out_aug_raw.txt | grep -E "LAZY_ARM|LAZY_EXIT|LAZY_REENTRY"
python3 -u -c "
from algotest_backtest import run_lazy3_variant
from datetime import date
run_lazy3_variant(19, 0, date(2026,8,1), date(2026,8,31), qty_mult=4)
" 2>&1 | tee out_aug_raw.txt
python3 -u -c "
from algotest_backtest import run_lazy3_variant
from datetime import date
import algotest_backtest as m
m.args.debug = True
run_lazy3_variant(19, 0, date(2026,8,19), date(2026,8,20), qty_mult=4)
" 2>&1 | tee out_aug19.txt
grep -n "spawn_lazy(side, fts)" algotest_backtest.py
sed -n '472,490p' algotest_backtest.py
grep -n "momentum\|MOMENTUM" algotest_backtest.py
python3 - <<'EOF'
f = "algotest_backtest.py"
s = open(f).read()
old = '''                                    if lzstate["count"] < 4:'''
new = '''                                    if lzstate["count"] < 2:'''
assert s.count(old) == 2, f"found {s.count(old)} occurrences, expected 2"
s = s.replace(old, new)
open(f, "w").write(s)
print("PATCHED OK")
EOF

python3 - <<'EOF'
f = "algotest_backtest.py"
s = open(f).read()
old = '''                                    if lzstate["count"] < 4:'''
new = '''                                    if lzstate["count"] < 2:'''
assert s.count(old) == 1, f"found {s.count(old)} occurrences, expected 1"
s = s.replace(old, new)
open(f, "w").write(s)
print("PATCHED OK")
EOF

python3 -u -c "
from algotest_backtest import run_lazy3_variant
from datetime import date
import algotest_backtest as m
m.args.debug = True
run_lazy3_variant(19, 0, date(2026,8,19), date(2026,8,20), qty_mult=4)
" 2>&1 | tee out_aug19_v2.txt
grep -n "SL_LAZY_PTS\s*=\|TRAIL_MOVE\s*=\|TRAIL_STEP\s*=\|MAX_MARK_AGE\s*=" algotest_backtest.py
grep -n "def otm_strike" -A 10 algotest_backtest.py
grep -n "^OTM_N\s*=" algotest_backtest.py
sed -i 's/^OTM_N = 5/OTM_N = 2/' algotest_backtest.py
grep -n "^OTM_N" algotest_backtest.py
sed -i 's/^OTM_N = 2/OTM_N = 5/' algotest_backtest.py
python3 - <<'EOF'
f = "algotest_backtest.py"
s = open(f).read()
old = '''            def spawn_lazy(side, trigger_ts):
                cur_spot = spot_series.mark_price(trigger_ts) or spot_px
                lk = otm_strike(cur_spot, side, OTM_N)'''
new = '''            def spawn_lazy(side, trigger_ts):
                cur_spot = spot_series.mark_price(trigger_ts) or spot_px
                lk = otm_strike(cur_spot, side, 2)'''
assert s.count(old) == 1, f"found {s.count(old)}"
s = s.replace(old, new)
open(f, "w").write(s)
print("PATCHED OK")
EOF

cpython3 -u -c "
from algotest_backtest import run_lazy3_variant
from datetime import date
import algotest_backtest as m
m.args.debug = True
run_lazy3_variant(19, 0, date(2026,8,19), date(2026,8,20), qty_mult=4)
" 2>&1 | tee out_aug19_v3.txt
python3 -u -c "
from algotest_backtest import run_lazy3_variant
from datetime import date
import algotest_backtest as m
m.args.debug = True
run_lazy3_variant(19, 0, date(2026,8,19), date(2026,8,20), qty_mult=4)
" 2>&1 | tee out_aug19_v3.txt
nohup python3 -u algotest_backtest.py --start 2024-01-01 --end 2026-10-20 --debug > out_full.txt 2>&1 &
kill 4180730
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 --debug 2>&1 | tee out_aug_v2.txt
kill 4180730
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 --debug 2>&1 | tee out_aug_v2.txt
cd ~/strategies_options/backtest
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 --debug 2>&1 | tee out_aug_v2.txt
cd ~/strategies_options/backtest
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 --debug 2>&1 | tee out_aug_v2.txt
python3 -u -c "
from algotest_backtest import run_lazy3_variant
from datetime import date
import algotest_backtest as m
m.args.debug = True
run_lazy3_variant(19, 0, date(2026,8,30), date(2026,8,31), qty_mult=4)
" 2>&1 | tee out_aug30.txt
grep -n "lz\[.trail_sl.\] = lz\[.leg.\]\[.raw.\] - SL_LAZY_PTS" algotest_backtest.py
grep -n "def low_at\|def peak\b" -A 8 algotest_backtest.py
sed -i 's/if lzstate\["count"\] < 2:/if lzstate["count"] < 4:/' algotest_backtest.py
grep -n 'lzstate\["count"\] < ' algotest_backtest.py
python3 algotest_backtest.py --start 2024-01-01 --end 2026-10-20 | tee out_full.txt
python3 -u algotest_backtest.py --start 2024-01-01 --end 2026-10-20 | tee out_full.txt
sed -n '1,60p' algotest_backtest.py
sed -n '160,200p' algotest_backtest.py
sed -n '55,95p' algotest_backtest.py
python3 << 'EOF'
import re

with open('algotest_backtest.py', 'r') as f:
    content = f.read()

old = '''_cache = {}


def get_candles(symbol, s, e):
    key = (symbol, s, e)
    if key in _cache:
        return _cache[key]
    seen, cur = {}, s
    while cur < e:
        ce = min(cur + 2000 * STEP, e)
        ok = False
        for att in range(1, 4):
            try:
                r = requests.get(BASE + "/v2/history/candles", timeout=(3, 27),
                                  params={"symbol": symbol, "resolution": "1m", "start": cur, "end": ce})
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(att); continue
                d = r.json()
                if d.get("success", False):
                    for c in d.get("result", []):
                        seen[c["time"]] = c
                ok = True
                break
            except Exception as ex:
                print(f"WARNING fetch {symbol}: {ex}")
                time.sleep(att)
        if not ok:
            raise FetchError(f"{symbol} {cur}-{ce}")
        cur = ce
    out = [seen[t] for t in sorted(seen)]
    if symbol.startswith("C-") or symbol.startswith("P-"):
        out = [x for x in out if (x.get("volume") or 0) > 0]
    _cache[key] = out
    return out'''

new = '''_cache = {}
_cache_ranges = {}


def get_candles(symbol, s, e):
    ranges = _cache_ranges.setdefault(symbol, [])
    covered = any(rs <= s and e <= re for rs, re in ranges)
    if not covered:
        seen = _cache.setdefault(symbol, {})
        cur = s
        while cur < e:
            ce = min(cur + 2000 * STEP, e)
            ok = False
            for att in range(1, 4):
                try:
                    r = requests.get(BASE + "/v2/history/candles", timeout=(3, 27),
                                      params={"symbol": symbol, "resolution": "1m", "start": cur, "end": ce})
                    if r.status_code == 429 or r.status_code >= 500:
                        time.sleep(att); continue
                    d = r.json()
                    if d.get("success", False):
                        for c in d.get("result", []):
                            seen[c["time"]] = c
                    ok = True
                    break
                except Exception as ex:
                    print(f"WARNING fetch {symbol}: {ex}")
                    time.sleep(att)
            if not ok:
                raise FetchError(f"{symbol} {cur}-{ce}")
            cur = ce
        ranges.append((s, e))
    out = [_cache[symbol][t] for t in sorted(_cache[symbol]) if s <= t <= e]
    if symbol.startswith("C-") or symbol.startswith("P-"):
        out = [x for x in out if (x.get("volume") or 0) > 0]
    return out'''

if old not in content:
    print("ERROR: old block not found, no changes made")
else:
    content = content.replace(old, new)
    with open('algotest_backtest.py', 'w') as f:
        f.write(content)
    print("OK: patched successfully")
EOF

grep -n "_cache_ranges" algotest_backtest.py
python3 -u algotest_backtest.py --start 2024-01-01 --end 2026-10-20 | tee out_full.txt
grep -n "for.*date\|while.*date\|def run_recost_variant\|def run_lazy_variant" algotest_backtest.py
grep -n "cur_date\|for d in\|while d\|current_date\|days =" algotest_backtest.py
sed -i '254a\        print(f"...{d}", end="\\r", flush=True)' algotest_backtest.py
sed -n '250,260p' algotest_backtest.py
sed -n '256,260p' algotest_backtest.py
python3 -u algotest_backtest.py --start 2024-01-01 --end 2026-10-20 | tee out_full.txt
sed -i 's/print(f"...{d}", end="\\\\r", flush=True)/print(f"...{d}", flush=True)/' algotest_backtest.py
grep -n '\.\.\.{d}' algotest_backtest.py
sed -i '255s/.*/        print(f"...{d}", flush=True)/' algotest_backtest.py
sed -n '255p' algotest_backtest.py
python3 -u algotest_backtest.py --start 2024-01-01 --end 2026-10-20 | tee out_full.txt
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 | tee out_aug_v3.txt
grep -n "_cache.clear()" algotest_backtest.py
sed -i 's/_cache.clear()/_cache.clear(); _cache_ranges.clear()/' algotest_backtest.py
grep -n "_cache.clear()" algotest_backtest.py
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 | tee out_aug_v3.txt
python3 << 'EOF'
with open('algotest_backtest.py', 'r') as f:
    content = f.read()

old = '''_cache = {}
_cache_ranges = {}


def get_candles(symbol, s, e):
    ranges = _cache_ranges.setdefault(symbol, [])
    covered = any(rs <= s and e <= re for rs, re in ranges)
    if not covered:
        seen = _cache.setdefault(symbol, {})
        cur = s
        while cur < e:
            ce = min(cur + 2000 * STEP, e)
            ok = False
            for att in range(1, 4):
                try:
                    r = requests.get(BASE + "/v2/history/candles", timeout=(3, 27),
                                      params={"symbol": symbol, "resolution": "1m", "start": cur, "end": ce})
                    if r.status_code == 429 or r.status_code >= 500:
                        time.sleep(att); continue
                    d = r.json()
                    if d.get("success", False):
                        for c in d.get("result", []):
                            seen[c["time"]] = c
                    ok = True
                    break
                except Exception as ex:
                    print(f"WARNING fetch {symbol}: {ex}")
                    time.sleep(att)
            if not ok:
                raise FetchError(f"{symbol} {cur}-{ce}")
            cur = ce
        ranges.append((s, e))
    out = [_cache[symbol][t] for t in sorted(_cache[symbol]) if s <= t <= e]
    if symbol.startswith("C-") or symbol.startswith("P-"):
        out = [x for x in out if (x.get("volume") or 0) > 0]
    return out'''

new = '''_cache = {}


def get_candles(symbol, s, e):
    key = (symbol, s, e)
    if key in _cache:
        return _cache[key]
    seen, cur = {}, s
    while cur < e:
        ce = min(cur + 2000 * STEP, e)
        ok = False
        for att in range(1, 4):
            try:
                r = requests.get(BASE + "/v2/history/candles", timeout=(3, 27),
                                  params={"symbol": symbol, "resolution": "1m", "start": cur, "end": ce})
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(att); continue
                d = r.json()
                if d.get("success", False):
                    for c in d.get("result", []):
                        seen[c["time"]] = c
                ok = True
                break
            except Exception as ex:
                print(f"WARNING fetch {symbol}: {ex}")
                time.sleep(att)
        if not ok:
            raise FetchError(f"{symbol} {cur}-{ce}")
        cur = ce
    out = [seen[t] for t in sorted(seen)]
    if symbol.startswith("C-") or symbol.startswith("P-"):
        out = [x for x in out if (x.get("volume") or 0) > 0]
    _cache[key] = out
    return out'''

if old not in content:
    print("ERROR: not found")
else:
    content = content.replace(old, new)
    with open('algotest_backtest.py', 'w') as f:
        f.write(content)
    print("OK: reverted")
EOF

sed -i 's/_cache.clear(); _cache_ranges.clear()/_cache.clear()/' algotest_backtest.py
grep -n "_cache.clear()\|_cache_ranges" algotest_backtest.py
python3 -u algotest_backtest.py --start 2026-08-01 --end 2026-08-31 | tee out_aug_v4.txt
grep -n 'lzstate\["count"\]\|re{lz\|f"re{' algotest_backtest.py
