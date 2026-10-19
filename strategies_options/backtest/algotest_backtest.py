import time, argparse, math, bisect, requests
from datetime import datetime, timedelta, timezone

BASE = "https://api.india.delta.exchange"
SPOT = ".DEXBTUSD"
CAP = 227.0
STEP = 60
STRIKE_STEP = 200
OTM_N = 5
SLIP = 0.05
MAX_FILL_GAP = 1800
MAX_MARK_AGE = 1800
CV = 0.001

LOTS_RECOST = 333
LOTS_MAIN = 1
LOTS_LAZY = 250
MULT_RECOST = LOTS_RECOST * CV
MULT_MAIN = LOTS_MAIN * CV
MULT_LAZY = LOTS_LAZY * CV

SL_RECOST_PCT = 2.00
SL_MAIN_PCT = 1.00
SL_LAZY_PTS = 50
TRAIL_STEP = 10
TRAIL_MOVE = 10

IST = timezone(timedelta(hours=5, minutes=30))
TRAIN_END = datetime(2025, 7, 1, tzinfo=timezone.utc).date()

ap = argparse.ArgumentParser()
ap.add_argument("--start", default="2024-01-01")
ap.add_argument("--end", default="2026-10-13")
ap.add_argument("--debug", action="store_true")
args = ap.parse_args()


class FetchError(Exception):
    pass


_cache = {}


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
    _cache[key] = out
    return out


_settle_cache = {}


def settlement_price(symbol):
    if symbol in _settle_cache:
        return _settle_cache[symbol]
    v = None
    for att in range(1, 4):
        try:
            r = requests.get(f"{BASE}/v2/products/{symbol}", timeout=(3, 27))
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(att); continue
            d = r.json()
            if d.get("success", False):
                sp = (d.get("result") or {}).get("settlement_price")
                v = float(sp) if sp is not None else None
            break
        except Exception as ex:
            print(f"WARNING settle {symbol}: {ex}"); time.sleep(att)
    _settle_cache[symbol] = v
    return v


class Series:
    def __init__(self, c):
        self.c = c
        self.t = [x["time"] for x in c]

    def mark_with_age(self, ts):
        i = bisect.bisect_right(self.t, ts) - 1
        return (None, None) if i < 0 else (self.c[i]["close"], ts - self.t[i])

    def mark_price(self, ts):
        return self.mark_with_age(ts)[0]

    def fill_at(self, ts):
        i = bisect.bisect_right(self.t, ts)
        if i >= len(self.c) or self.c[i]["time"] - ts > MAX_FILL_GAP:
            return None, None
        return self.c[i]["open"], self.c[i]["time"]


def ts_of(d, h=12, m=0):
    return int(datetime(d.year, d.month, d.day, h, m, tzinfo=IST).timestamp())


def daily_list(a, b):
    out, d = [], a
    while d <= b:
        out.append(d)
        d += timedelta(days=1)
    return out


def otm_strike(spot, side, n):
    base = int(round(spot / STRIKE_STEP) * STRIKE_STEP)
    return base + (n * STRIKE_STEP if side == "C" else -n * STRIKE_STEP)


def osym(t, k, e):
    return f"{t}-BTC-{k}-{e.strftime('%d%m%y')}"


def fee(spot, px):
    return min(0.00015 * spot, 0.05 * px) * 1.18


def spot_at(series, ts, fallback):
    v = series.mark_price(ts)
    return v if v else fallback


def premium_at(t, k, e, ts):
    sym = osym(t, k, e)
    c = get_candles(sym, ts, ts + MAX_FILL_GAP + STEP)
    if not c:
        return None
    px, fts = Series(c).fill_at(ts)
    return None if (px is None or px <= 0) else (sym, px, fts)


def find_cost_match(t, direction, exp, ts, target, start_k, max_steps=30):
    prev = None
    for n in range(1, max_steps + 1):
        k = start_k + direction * n * STRIKE_STEP
        r = premium_at(t, k, exp, ts)
        if r is None:
            continue
        if r[1] <= target:
            return (k, r)
        prev = (k, r)
    return prev


def leg(role, t, k, e, r):
    px = r[1] * (1 - SLIP) if role == "S" else r[1] * (1 + SLIP)
    return {"role": role, "type": t, "strike": k, "expiry": e, "symbol": r[0], "raw": px, "mkt": r[1], "fill_ts": r[2]}


class Acc:
    def __init__(s):
        s.eq = s.peak = CAP; s.mdd = 0.0; s.pnls = []; s.fees = []
        s.skips = {}; s.breach = None; s.per = {"TRAIN": [0, 0.0], "TEST": [0, 0.0]}

    def trade(s, d, pnl, fe):
        s.eq += pnl; s.pnls.append(pnl); s.fees.append(fe)
        s.peak = max(s.peak, s.eq); s.mdd = max(s.mdd, s.peak - s.eq)
        if s.eq <= 0 and s.breach is None:
            s.breach = d
        p = "TRAIN" if d < TRAIN_END else "TEST"
        s.per[p][0] += 1; s.per[p][1] += pnl


def summarize(tag, acc, years):
    n = len(acc.pnls)
    sk = ",".join(f"{k}={v}" for k, v in acc.skips.items()) or "none"
    if n == 0:
        print(f"SUMMARY {tag} trades=0 skips[{sk}]"); return
    mean = sum(acc.pnls) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in acc.pnls) / (n - 1)) if n > 1 else 0
    sharpe = mean / sd * math.sqrt(n / years) if sd > 0 else 0
    wins = sum(1 for x in acc.pnls if x > 0)
    print(f"SUMMARY {tag} trades={n} win%={wins / n * 100:.1f} net=${sum(acc.pnls):.2f} "
          f"avg_net=${mean:.2f} avg_fees=${sum(acc.fees) / n:.2f} final_equity=${acc.eq:.2f} "
          f"maxDD=${acc.mdd:.2f} sharpe(per-trade,ann.)={sharpe:.2f} first_breach={acc.breach} "
          f"TRAIN(n,net)={acc.per['TRAIN'][0]},{acc.per['TRAIN'][1]:.2f} "
          f"TEST(n,net)={acc.per['TEST'][0]},{acc.per['TEST'][1]:.2f} skips[{sk}]")


def run_recost_variant(entry_h, entry_m, a, b):
    tag = f"strangle_recost {entry_h:02d}:{entry_m:02d}"
    acc = Acc()
    trades = []
    for d in daily_list(a, b):
        if d.weekday() == 4 or d.weekday() == 6:
            continue
        _cache.clear()
        entry_ts = ts_of(d, entry_h, entry_m)
        exit_ts = ts_of(d, 17, 29)
        exp = d

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

            slots = {
                "C": {"active": leg("S", "C", ck, exp, cr), "reentries": 0, "series": None, "pnl": 0.0, "fee": 0.0, "done": False},
                "P": {"active": leg("S", "P", pk, exp, pr), "reentries": 0, "series": None, "pnl": 0.0, "fee": 0.0, "done": False},
            }
            for side in ("C", "P"):
                l = slots[side]["active"]
                slots[side]["series"] = Series(get_candles(l["symbol"], entry_ts, exit_ts + 2 * STEP))

            entry_fee_raw = fee(spot_px, cr[1]) + fee(spot_px, pr[1])
            cur = max(cr[2], pr[2]) + STEP

            while cur < exit_ts:
                for side in ("C", "P"):
                    sl = slots[side]
                    if sl["done"]:
                        continue
                    if sl.get("wait"):
                        w = sl["wait"]
                        m, age = sl["series"].mark_with_age(cur)
                        if m is not None and age <= MAX_MARK_AGE and m <= w["mkt"]:
                            px, fts = sl["series"].fill_at(cur)
                            if px is not None:
                                sl["active"] = leg("S", side, w["strike"], exp, (w["symbol"], px, fts))
                                sl["reentries"] += 1
                                sl["fee"] += fee(spot_at(spot_series, fts, spot_px), px)
                                sl["wait"] = None
                        continue
                    l = sl["active"]
                    m, age = sl["series"].mark_with_age(cur)
                    if m is None or age > MAX_MARK_AGE:
                        continue
                    sl_level = l["mkt"] * (1 + SL_RECOST_PCT)
                    if m >= sl_level:
                        px, fts = sl_level, cur
                        ef = px * (1 + SLIP)
                        sl["pnl"] += l["raw"] - ef
                        sl["fee"] += fee(spot_at(spot_series, fts, spot_px), ef)
                        if sl["reentries"] < 1:
                            sl["wait"] = l
                        else:
                            sl["done"] = True
                cur += STEP

            unsettled = False
            for side in ("C", "P"):
                sl = slots[side]
                if sl["done"] or sl.get("wait"):
                    continue
                l = sl["active"]
                px, fts = sl["series"].fill_at(exit_ts)
                if px is None:
                    m, age = sl["series"].mark_with_age(exit_ts)
                    if m is None or age > MAX_MARK_AGE:
                        unsettled = True
                        break
                    px = m
                ef = px * (1 + SLIP)
                sl["pnl"] += l["raw"] - ef
                sl["fee"] += fee(spot_at(spot_series, exit_ts, spot_px), ef)
            if unsettled:
                skip("UNSETTLED")
                continue

            day_pnl = slots["C"]["pnl"] + slots["P"]["pnl"]
            day_fee = entry_fee_raw + slots["C"]["fee"] + slots["P"]["fee"]
            net = (day_pnl - day_fee) * MULT_RECOST
            fee_scaled = day_fee * MULT_RECOST
            acc.trade(d, net, fee_scaled)
            trades.append((d, net, fee_scaled))
            print(f"[{tag}] {d} C={ck}@{cr[1]:.0f} P={pk}@{pr[1]:.0f} "
                  f"re(C,P)=({slots['C']['reentries']},{slots['P']['reentries']}) "
                  f"pnl=${net:.2f} equity=${acc.eq:.2f}")

        except FetchError as ex:
            print(f"WARNING {d} {ex}")
            skip("FETCH_FAIL")
            continue

    years = max((b - a).days / 365.25, 0.01)
    summarize(f"[{tag}]", acc, years)
    return acc, trades


def run_lazy3_variant(entry_h, entry_m, a, b, qty_mult=1):
    tag = f"btst_lazy3 {entry_h:02d}:{entry_m:02d}"
    acc = Acc()
    trades = []
    for d in daily_list(a, b):
        _cache.clear()
        entry_ts = ts_of(d, entry_h, entry_m)
        exp = d + timedelta(days=2 if entry_h == 19 else 1)
        exit_day = exp
        exit_ts = ts_of(exit_day, 17, 15)

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

            lazy = {
                "C": {"cur": None, "count": 0, "last_exit_px": None, "pnl": 0.0, "fee": 0.0},
                "P": {"cur": None, "count": 0, "last_exit_px": None, "pnl": 0.0, "fee": 0.0},
            }
            entry_fee_raw = fee(spot_px, cr[1]) + fee(spot_px, pr[1])
            cur = max(cr[2], pr[2]) + STEP

            def spawn_lazy(side, trigger_ts):
                cur_spot = spot_series.mark_price(trigger_ts) or spot_px
                lk = otm_strike(cur_spot, side, OTM_N)
                lr = premium_at(side, lk, exp, trigger_ts)
                if not lr:
                    return None
                lz_leg = leg("B", side, lk, exp, lr)
                return {
                    "leg": lz_leg,
                    "series": Series(get_candles(lz_leg["symbol"], lr[2], exit_ts + 2 * STEP)),
                    "trail_sl": lz_leg["raw"] - SL_LAZY_PTS,
                    "done": False,
                    "fee_entry": 0.0,
                    "fee_real": fee(cur_spot, lr[1]),
                    "armed": False,
                    "trig": lz_leg["mkt"] * 2,
                }

            while cur < exit_ts:
                for side in ("C", "P"):
                    ml = main[side]
                    if not ml["sl_done"]:
                        l = ml["leg"]
                        m, age = ml["series"].mark_with_age(cur)
                        if m is not None and age <= MAX_MARK_AGE:
                            sl_level = l["mkt"] * (1 + SL_MAIN_PCT)
                            if m >= sl_level:
                                px, fts = sl_level, cur
                                if True:
                                    ef = px * (1 + SLIP)
                                    ml["pnl"] += l["raw"] - ef
                                    ml["fee"] += fee(spot_at(spot_series, fts, spot_px), ef)
                                    ml["sl_done"] = True
                                    inst = spawn_lazy(side, fts)
                                    if inst:
                                        lazy[side]["cur"] = inst
                                        lazy[side]["fee"] += inst["fee_entry"]

                    lzstate = lazy[side]
                    lz = lzstate["cur"]
                    if lz and not lz["done"]:
                        m, age = lz["series"].mark_with_age(cur)
                        if m is not None and age <= MAX_MARK_AGE:
                            if not lz["armed"]:
                                if m >= lz["trig"]:
                                    px, fts = lz["series"].fill_at(cur)
                                    if px is not None:
                                        lz["leg"]["raw"] = px * (1 + SLIP)
                                        lz["trail_sl"] = lz["leg"]["raw"] - SL_LAZY_PTS
                                        lz["armed"] = True
                                        lzstate["fee"] += lz["fee_real"]
                                continue
                            if m - lz["leg"]["raw"] >= TRAIL_MOVE:
                                steps = int((m - lz["leg"]["raw"]) // TRAIL_MOVE)
                                lz["trail_sl"] = max(lz["trail_sl"], lz["leg"]["raw"] - SL_LAZY_PTS + steps * TRAIL_STEP)
                            if m <= lz["trail_sl"]:
                                px, fts = lz["series"].fill_at(cur)
                                if px is not None:
                                    ef = px * (1 - SLIP)
                                    lzstate["pnl"] += ef - lz["leg"]["raw"]
                                    lzstate["fee"] += fee(spot_at(spot_series, fts, spot_px), ef)
                                    lz["done"] = True
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
                cur += STEP

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
    return acc, trades


RECOST_TIMES = [(9, 20), (10, 20), (11, 20)]
LAZY3_TIMES = [(19, 0, 4), (9, 20, 1), (10, 20, 1), (11, 20, 1)]

if __name__ == "__main__":
    a = datetime.strptime(args.start, "%Y-%m-%d").date()
    b = datetime.strptime(args.end, "%Y-%m-%d").date()
    print(f"WINDOW {a} to {b} | strategies=[strangle_recost x3, btst_lazy3 x4]")

    all_trades = []
    for h, m in RECOST_TIMES:
        _, tr = run_recost_variant(h, m, a, b)
        all_trades.extend(tr)
    for h, m, qm in LAZY3_TIMES:
        _, tr = run_lazy3_variant(h, m, a, b, qty_mult=qm)
        all_trades.extend(tr)

    all_trades.sort(key=lambda x: x[0])
    merged = {}
    for d, net, fe in all_trades:
        if d not in merged:
            merged[d] = [0.0, 0.0]
        merged[d][0] += net
        merged[d][1] += fe

    portfolio = Acc()
    for d in sorted(merged):
        portfolio.trade(d, merged[d][0], merged[d][1])

    years = max((b - a).days / 365.25, 0.01)
    summarize("[PORTFOLIO ALL 7 VARIANTS]", portfolio, years)
