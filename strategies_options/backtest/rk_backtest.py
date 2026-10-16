import time, argparse, bisect, math, requests
from datetime import datetime, timedelta, timezone

BASE = "https://api.india.delta.exchange"
SPOT = ".DEXBTUSD"
CAP, STRIKE_STEP, STEP, CV = 227.0, 1000, 300, 0.001
MAX_FILL_GAP, MAX_MARK_AGE = 1800, 1800
SLIP, HEDGE_RATIO = 0.05, 0.45
TARGET_PREM = {"weekly": 200, "monthly": 1000}
DTES = {"weekly": [8, 10], "monthly": [32, 35, 45]}
STRATS = ["strangle", "straddle", "iron_condor", "iron_fly", "calendar"]
VARIANTS = ["5pct", "10pct", "20pct", "30pct"]
TRAIN_END = datetime(2025, 7, 1, tzinfo=timezone.utc).date()

ap = argparse.ArgumentParser()
ap.add_argument("--start", default="2025-01-01")
ap.add_argument("--end", default="2026-10-14")
ap.add_argument("--strategies", default=",".join(STRATS))
ap.add_argument("--kinds", default="weekly,monthly")
ap.add_argument("--dte", type=int, default=None)
ap.add_argument("--lots", type=int, default=100)
ap.add_argument("--max-skew", type=int, default=1800)
ap.add_argument("--debug", action="store_true")
args = ap.parse_args()
MULT = args.lots * CV


class FetchError(Exception):
    pass


_cache = {}


def get_candles(symbol, s, e):
    key = (symbol, s, e)
    if key in _cache:
        return _cache[key]
    seen, cur = {}, s
    while cur < e:
        ce = min(cur + 5 * 86400, e)
        ok = False
        for att in range(1, 4):
            try:
                r = requests.get(BASE + "/v2/history/candles", timeout=(3, 27),
                                 params={"symbol": symbol, "resolution": "5m", "start": cur, "end": ce})
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


def weekly_exp(a, b):
    d = a
    while d.weekday() != 4:
        d += timedelta(days=1)
    out = []
    while d <= b:
        out.append(d); d += timedelta(days=7)
    return out


def monthly_exp(a, b):
    out, d = [], a.replace(day=1)
    while d <= b:
        nm = d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1)
        last = nm - timedelta(days=1)
        while last.weekday() != 4:
            last -= timedelta(days=1)
        if a <= last <= b:
            out.append(last)
        d = nm
    return out


def osym(t, k, e):
    return f"{t}-BTC-{k}-{e.strftime('%d%m%y')}"


def rstrike(p):
    return int(round(p / STRIKE_STEP) * STRIKE_STEP)


def ts_of(d, h=12):
    return int(datetime(d.year, d.month, d.day, h, tzinfo=timezone.utc).timestamp())


def fee(spot, px):
    return min(0.00015 * spot, 0.05 * px) * 1.18


def premium_at(t, k, e, entry_ts):
    sym = osym(t, k, e)
    c = get_candles(sym, entry_ts, entry_ts + MAX_FILL_GAP + STEP)
    if not c:
        return None
    px, ts = Series(c).fill_at(entry_ts)
    return None if (px is None or px <= 0) else (sym, px, ts)


def find_by_target(t, start_k, direction, e, entry_ts, target, first_step):
    prev = None
    for step in range(first_step, 21):
        k = start_k + direction * step * STRIKE_STEP
        if k <= 0:
            break
        r = premium_at(t, k, e, entry_ts)
        if r is None:
            continue
        cand = (k, r)
        if r[1] <= target:
            if prev is not None and abs(prev[1][1] - target) < abs(r[1] - target):
                return prev
            return cand
        prev = cand
    return prev


def leg(role, t, k, e, r):
    return {"role": role, "type": t, "strike": k, "expiry": e, "symbol": r[0], "raw": r[1], "fill_ts": r[2]}


ATM_ORDER = [0, 1, -1, 2, -2]


def build(strat, kind, exp, entry_ts, spot):
    base, tp = rstrike(spot), TARGET_PREM[kind]
    if strat in ("strangle", "iron_condor"):
        c = find_by_target("C", base, 1, exp, entry_ts, tp, 0)
        p = find_by_target("P", base, -1, exp, entry_ts, tp, 0)
        if not c or not p:
            return "NO_FILL"
        legs = [leg("S", "C", c[0], exp, c[1]), leg("S", "P", p[0], exp, p[1])]
        if strat == "iron_condor":
            hc = find_by_target("C", c[0], 1, exp, entry_ts, HEDGE_RATIO * c[1][1], 1)
            hp = find_by_target("P", p[0], -1, exp, entry_ts, HEDGE_RATIO * p[1][1], 1)
            if not hc or not hp:
                return "NO_FILL"
            legs += [leg("B", "C", hc[0], exp, hc[1]), leg("B", "P", hp[0], exp, hp[1])]
        return legs
    if strat in ("straddle", "iron_fly"):
        for off in ATM_ORDER:
            k = base + off * STRIKE_STEP
            c, p = premium_at("C", k, exp, entry_ts), premium_at("P", k, exp, entry_ts)
            if c and p:
                break
        else:
            return "NO_FILL"
        legs = [leg("S", "C", k, exp, c), leg("S", "P", k, exp, p)]
        if strat == "iron_fly":
            hc = find_by_target("C", k, 1, exp, entry_ts, HEDGE_RATIO * c[1], 1)
            hp = find_by_target("P", k, -1, exp, entry_ts, HEDGE_RATIO * p[1], 1)
            if not hc or not hp:
                return "NO_FILL"
            legs += [leg("B", "C", hc[0], exp, hc[1]), leg("B", "P", hp[0], exp, hp[1])]
        return legs
    if strat == "calendar":
        fars = monthly_exp(exp + timedelta(days=1), exp + timedelta(days=75))
        if not fars:
            return "NO_FAR_EXPIRY"
        far = fars[0]
        for off in ATM_ORDER:
            k = base + off * STRIKE_STEP
            opts = []
            for t in ("C", "P"):
                n, f = premium_at(t, k, exp, entry_ts), premium_at(t, k, far, entry_ts)
                if n and f and f[1] > n[1]:
                    opts.append((f[1] - n[1], t, n, f))
            if opts:
                _, t, n, f = min(opts, key=lambda x: x[0])
                return [leg("S", t, k, exp, n), leg("B", t, k, far, f)]
        return "NO_FILL"


def basis_of(strat, legs):
    s = sum(l["raw"] for l in legs if l["role"] == "S")
    b = sum(l["raw"] for l in legs if l["role"] == "B")
    return (b - s) if strat == "calendar" else (s - b)


def raw_pnl(legs, marks):
    return sum((l["raw"] - m) if l["role"] == "S" else (m - l["raw"]) for l, m in zip(legs, marks))


def trigger(v, strat, basis, legs, marks):
    sold = [(l, m) for l, m in zip(legs, marks) if l["role"] == "S"]
    sold_entry = sum(l["raw"] for l, m in sold)
    sold_mark = sum(m for l, m in sold)
    credit = sum(l["raw"] for l in legs if l["role"] == "S") - sum(l["raw"] for l in legs if l["role"] == "B")
    pnl = raw_pnl(legs, marks)
    tg = {"5pct": 0.05, "10pct": 0.10, "20pct": 0.20, "30pct": 0.30}[v]
    if pnl >= tg * credit:
        return "TARGET"
    if sold_mark >= 2 * sold_entry:
        return "SL"
    return None


def settle_leg(l, spot_series, settle_ts):
    sp = settlement_price(l["symbol"])
    if sp is not None:
        return sp
    m, age = spot_series.mark_with_age(settle_ts)
    if m is None or age > STEP:
        return None
    return max(m - l["strike"], 0) if l["type"] == "C" else max(l["strike"] - m, 0)


def simulate(strat, legs, basis, entry_fill_ts, spot_series, spot_px, settle_ts):
    for l in legs:
        l["fill"] = l["raw"] * (1 - SLIP) if l["role"] == "S" else l["raw"] * (1 + SLIP)
    entry_fee = sum(fee(spot_px, l["fill"]) for l in legs)
    res, active, cur = {}, list(VARIANTS), entry_fill_ts + STEP
    while cur < settle_ts and active:
        marks, bad = [], False
        for l in legs:
            m, age = l["series"].mark_with_age(cur)
            if m is None or age > MAX_MARK_AGE:
                bad = True; break
            marks.append(m)
        if not bad:
            for v in list(active):
                reason = trigger(v, strat, basis, legs, marks)
                if not reason:
                    continue
                fills = [l["series"].fill_at(cur) for l in legs]
                if any(f[1] is None for f in fills):
                    continue
                pnl, xf, es = 0.0, 0.0, (spot_series.mark_price(cur) or spot_px)
                for l, (px, _) in zip(legs, fills):
                    if l["role"] == "S":
                        ef = px * (1 + SLIP); pnl += l["fill"] - ef
                    else:
                        ef = px * (1 - SLIP); pnl += ef - l["fill"]
                    xf += fee(es, ef)
                res[v] = (reason, pnl, entry_fee + xf)
                active.remove(v)
        cur += STEP
    if active:
        if settle_ts > int(time.time()):
            for v in active:
                res[v] = ("UNSETTLED", None, None)
        else:
            pnl, xf, ok = 0.0, 0.0, True
            for l in legs:
                if l["expiry_ts"] == settle_ts:
                    sv = settle_leg(l, spot_series, settle_ts)
                    if sv is None:
                        ok = False; break
                    pnl += (l["fill"] - sv) if l["role"] == "S" else (sv - l["fill"])
                else:
                    px, ts = l["series"].fill_at(settle_ts)
                    if ts is None:
                        m, age = l["series"].mark_with_age(settle_ts)
                        if m is None or age > MAX_MARK_AGE:
                            ok = False; break
                        px = m
                    ef = px * (1 - SLIP)
                    pnl += ef - l["fill"]
                    xf += fee(spot_series.mark_price(settle_ts) or spot_px, ef)
            for v in active:
                res[v] = ("EXPIRY", pnl, entry_fee + xf) if ok else ("UNSETTLED", None, None)
    return res


class Acc:
    def __init__(s):
        s.eq = s.peak = CAP; s.mdd = 0.0; s.pnls = []; s.fees = []
        s.skips = {}; s.breach = None; s.per = {"TRAIN": [0, 0.0], "HOLDOUT": [0, 0.0]}

    def trade(s, d, pnl, fe):
        s.eq += pnl; s.pnls.append(pnl); s.fees.append(fe)
        s.peak = max(s.peak, s.eq); s.mdd = max(s.mdd, s.peak - s.eq)
        if s.eq <= 0 and s.breach is None:
            s.breach = d
        p = "TRAIN" if d < TRAIN_END else "HOLDOUT"
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
          f"HOLDOUT(n,net)={acc.per['HOLDOUT'][0]},{acc.per['HOLDOUT'][1]:.2f} skips[{sk}]")


def run_group(strat, kind, dte, a, b):
    exps = weekly_exp(a, b) if kind == "weekly" else monthly_exp(a, b)
    accs = {v: Acc() for v in VARIANTS}
    gtag = f"{strat} {kind} {dte}DTE"
    for exp in exps:
        entry_ts, settle_ts = ts_of(exp - timedelta(days=dte)), ts_of(exp)
        def skip(reason):
            print(f"[{gtag}] {exp} submode={reason} day_pnl=$0.00 fees=$0.00 equity=(unchanged)")
            for v in VARIANTS:
                accs[v].skips[reason] = accs[v].skips.get(reason, 0) + 1
        try:
            sc = get_candles(SPOT, entry_ts, settle_ts + 2 * STEP)
            if not sc:
                skip("NO_DATA"); continue
            spot_series = Series(sc)
            spot_px = spot_series.mark_price(entry_ts)
            if spot_px is None:
                skip("NO_DATA"); continue
            legs = build(strat, kind, exp, entry_ts, spot_px)
            if isinstance(legs, str):
                skip(legs); continue
            for l in legs:
                l["expiry_ts"] = ts_of(l["expiry"])
                l["series"] = Series(get_candles(l["symbol"], entry_ts, settle_ts + 2 * STEP))
        except FetchError as ex:
            print(f"WARNING {exp} {ex}"); skip("FETCH_FAIL"); continue
        basis = basis_of(strat, legs)
        if basis <= 0:
            skip("BAD_BASIS"); continue
        skew = max(l["fill_ts"] for l in legs) - min(l["fill_ts"] for l in legs)
        if skew > args.max_skew:
            skip("SKEW"); continue
        res = simulate(strat, legs, basis, max(l["fill_ts"] for l in legs), spot_series, spot_px, settle_ts)
        info = " ".join(f"{l['role']}{l['type']}{l['strike']}@{l['raw']:.0f}" for l in legs)
        for v in VARIANTS:
            mode, pnl_raw, fee_raw = res[v]
            tag = f"[{gtag} {v}]"
            if pnl_raw is None:
                print(f"{tag} {exp} submode={mode} day_pnl=$0.00 fees=$0.00 equity=${accs[v].eq:.2f}")
                accs[v].skips[mode] = accs[v].skips.get(mode, 0) + 1
                continue
            net = (pnl_raw - fee_raw) * MULT
            accs[v].trade(exp, net, fee_raw * MULT)
            print(f"{tag} {exp} submode={mode} day_pnl=${net:.2f} fees=${fee_raw * MULT:.2f} "
                  f"equity=${accs[v].eq:.2f} skew={skew} {info}")
    years = max((b - a).days / 365.25, 0.01)
    for v in VARIANTS:
        summarize(f"[{gtag} {v}]", accs[v], years)


if __name__ == "__main__":
    a = datetime.strptime(args.start, "%Y-%m-%d").date()
    b = datetime.strptime(args.end, "%Y-%m-%d").date()
    print(f"WINDOW {a} to {b} | TRAIN<{TRAIN_END} HOLDOUT>= | lots={args.lots} max_skew={args.max_skew}")
    for kind in args.kinds.split(","):
        for dte in DTES[kind]:
            if args.dte and dte != args.dte:
                continue
            for strat in args.strategies.split(","):
                run_group(strat, kind, dte, a, b)
