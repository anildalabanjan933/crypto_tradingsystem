path = "/home/anildalabanjan7/strategies_options/backtest/rk_backtest.py"
src = open(path).read()

OLD_FBT = '''def find_by_target(t, start_k, direction, e, entry_ts, target, first_step):
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
    return prev'''

NEW_FBT = '''def find_by_target(t, start_k, direction, e, entry_ts, target, first_step, step=STRIKE_STEP):
    prev = None
    for s in range(first_step, 21):
        k = start_k + direction * s * step
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
    return prev'''

assert src.count(OLD_FBT) == 1, "find_by_target anchor not found"
src = src.replace(OLD_FBT, NEW_FBT)

OLD_MEXP = '''def monthly_exp(a, b):
    out, d = [], a.replace(day=1)
    while d <= b:
        nm = d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1)
        last = nm - timedelta(days=1)
        while last.weekday() != 4:
            last -= timedelta(days=1)
        if a <= last <= b:
            out.append(last)
        d = nm
    return out'''

NEW_MEXP = OLD_MEXP + '''


def monthly_rank_step(entry_ts, expiry):
    entry_date = datetime.fromtimestamp(entry_ts, tz=timezone.utc).date()
    chain = monthly_exp(entry_date, expiry)
    if not chain or chain[-1] != expiry:
        return None
    rank = len(chain) - 1
    return {0: 1000, 1: 2000, 2: 5000}.get(rank)'''

assert src.count(OLD_MEXP) == 1, "monthly_exp anchor not found"
src = src.replace(OLD_MEXP, NEW_MEXP)

OLD_BUILD = '''def build(strat, kind, exp, entry_ts, spot):
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
    if strat in ("vertical_debit", "vertical_credit"):
        w = VERT_WIDTH_STEPS[kind]
        for off in ATM_ORDER:
            k1 = base + off * STRIKE_STEP
            k2 = k1 + w * STRIKE_STEP
            r1, r2 = premium_at("C", k1, exp, entry_ts), premium_at("C", k2, exp, entry_ts)
            if r1 and r2 and r1[1] > r2[1]:
                if strat == "vertical_debit":
                    return [leg("B", "C", k1, exp, r1), leg("S", "C", k2, exp, r2)]
                return [leg("S", "C", k1, exp, r1), leg("B", "C", k2, exp, r2)]
        return "NO_FILL"
    if strat in CAL_KIND:
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
    return "NO_FILL"'''

NEW_BUILD = '''def build(strat, kind, exp, entry_ts, spot):
    tp = TARGET_PREM[kind]
    if strat in ("strangle", "iron_condor"):
        step = STRIKE_STEP if kind == "weekly" else monthly_rank_step(entry_ts, exp)
        if step is None:
            return "NO_FILL"
        base = int(round(spot / step) * step)
        c = find_by_target("C", base, 1, exp, entry_ts, tp, 0, step)
        p = find_by_target("P", base, -1, exp, entry_ts, tp, 0, step)
        if not c or not p:
            return "NO_FILL"
        legs = [leg("S", "C", c[0], exp, c[1]), leg("S", "P", p[0], exp, p[1])]
        if strat == "iron_condor":
            hc = find_by_target("C", c[0], 1, exp, entry_ts, HEDGE_RATIO * c[1][1], 1, step)
            hp = find_by_target("P", p[0], -1, exp, entry_ts, HEDGE_RATIO * p[1][1], 1, step)
            if not hc or not hp:
                return "NO_FILL"
            legs += [leg("B", "C", hc[0], exp, hc[1]), leg("B", "P", hp[0], exp, hp[1])]
        return legs
    if strat in ("straddle", "iron_fly"):
        step = STRIKE_STEP if kind == "weekly" else monthly_rank_step(entry_ts, exp)
        if step is None:
            return "NO_FILL"
        base = int(round(spot / step) * step)
        for off in ATM_ORDER:
            k = base + off * step
            c, p = premium_at("C", k, exp, entry_ts), premium_at("P", k, exp, entry_ts)
            if c and p:
                break
        else:
            return "NO_FILL"
        legs = [leg("S", "C", k, exp, c), leg("S", "P", k, exp, p)]
        if strat == "iron_fly":
            hc = find_by_target("C", k, 1, exp, entry_ts, HEDGE_RATIO * c[1], 1, step)
            hp = find_by_target("P", k, -1, exp, entry_ts, HEDGE_RATIO * p[1], 1, step)
            if not hc or not hp:
                return "NO_FILL"
            legs += [leg("B", "C", hc[0], exp, hc[1]), leg("B", "P", hp[0], exp, hp[1])]
        return legs
    if strat in ("vertical_debit", "vertical_credit"):
        step = STRIKE_STEP if kind == "weekly" else monthly_rank_step(entry_ts, exp)
        if step is None:
            return "NO_FILL"
        base = int(round(spot / step) * step)
        w = VERT_WIDTH_STEPS[kind]
        for off in ATM_ORDER:
            k1 = base + off * step
            k2 = k1 + w * step
            r1, r2 = premium_at("C", k1, exp, entry_ts), premium_at("C", k2, exp, entry_ts)
            if r1 and r2 and r1[1] > r2[1]:
                if strat == "vertical_debit":
                    return [leg("B", "C", k1, exp, r1), leg("S", "C", k2, exp, r2)]
                return [leg("S", "C", k1, exp, r1), leg("B", "C", k2, exp, r2)]
        return "NO_FILL"
    if strat in CAL_KIND:
        fars = monthly_exp(exp + timedelta(days=1), exp + timedelta(days=75))
        if not fars:
            return "NO_FAR_EXPIRY"
        far = fars[0]
        near_step = STRIKE_STEP if kind == "weekly" else monthly_rank_step(entry_ts, exp)
        far_step = monthly_rank_step(entry_ts, far)
        if near_step is None or far_step is None:
            return "NO_FILL"
        g = math.gcd(near_step, far_step)
        step = near_step * far_step // g
        base = int(round(spot / step) * step)
        for off in ATM_ORDER:
            k = base + off * step
            opts = []
            for t in ("C", "P"):
                n, f = premium_at(t, k, exp, entry_ts), premium_at(t, k, far, entry_ts)
                if n and f and f[1] > n[1]:
                    opts.append((f[1] - n[1], t, n, f))
            if opts:
                _, t, n, f = min(opts, key=lambda x: x[0])
                return [leg("S", t, k, exp, n), leg("B", t, k, far, f)]
        return "NO_FILL"
    return "NO_FILL"'''

assert src.count(OLD_BUILD) == 1, "build anchor not found"
src = src.replace(OLD_BUILD, NEW_BUILD)

open(path, "w").write(src)
print("PATCH_OK")
