path = "/home/anildalabanjan7/strategies_options/backtest/rk_backtest.py"
src = open(path).read()

# Fix 1: monthly_rank_step off-by-one (use > entry_ts, not >= entry_date)
OLD1 = '''def monthly_rank_step(entry_ts, expiry):
    entry_date = datetime.fromtimestamp(entry_ts, tz=timezone.utc).date()
    chain = monthly_exp(entry_date, expiry)
    if not chain or chain[-1] != expiry:
        return None
    rank = len(chain) - 1
    return {0: 1000, 1: 2000, 2: 5000}.get(rank)'''

NEW1 = '''def monthly_rank_step(entry_ts, expiry):
    entry_date = datetime.fromtimestamp(entry_ts, tz=timezone.utc).date()
    chain = [e for e in monthly_exp(entry_date, expiry) if ts_of(e) > entry_ts]
    if not chain or chain[-1] != expiry:
        return None
    rank = len(chain) - 1
    return {0: 1000, 1: 2000, 2: 5000}.get(rank)'''

assert src.count(OLD1) == 1, "fix1 anchor not found"
src = src.replace(OLD1, NEW1)

# Fix 4/5: ATM distance cap 7% - find_by_target
OLD2 = '''def find_by_target(t, start_k, direction, e, entry_ts, target, first_step, step=STRIKE_STEP):
    prev = None
    for s in range(first_step, 21):
        k = start_k + direction * s * step
        if k <= 0:
            break
        r = premium_at(t, k, e, entry_ts)'''

NEW2 = '''def find_by_target(t, start_k, direction, e, entry_ts, target, first_step, step=STRIKE_STEP, max_pct=0.07):
    prev = None
    for s in range(first_step, 21):
        k = start_k + direction * s * step
        if k <= 0 or abs(k - start_k) > max_pct * start_k:
            break
        r = premium_at(t, k, e, entry_ts)'''

assert src.count(OLD2) == 1, "fix2 anchor not found"
src = src.replace(OLD2, NEW2)

# Fix 4/5: ATM distance cap 7% - build() loops for straddle/iron_fly and calendar
OLD3 = '''        for off in ATM_ORDER:
            k = base + off * step
            c, p = premium_at("C", k, exp, entry_ts), premium_at("P", k, exp, entry_ts)
            if c and p:
                break
        else:
            return "NO_FILL"'''

NEW3 = '''        for off in ATM_ORDER:
            k = base + off * step
            if abs(k - base) > 0.07 * spot:
                continue
            c, p = premium_at("C", k, exp, entry_ts), premium_at("P", k, exp, entry_ts)
            if c and p:
                break
        else:
            return "NO_FILL"'''

assert src.count(OLD3) == 1, "fix3 anchor not found"
src = src.replace(OLD3, NEW3)

OLD4 = '''        w = VERT_WIDTH_STEPS[kind]
        for off in ATM_ORDER:
            k1 = base + off * step
            k2 = k1 + w * step
            r1, r2 = premium_at("C", k1, exp, entry_ts), premium_at("C", k2, exp, entry_ts)'''

NEW4 = '''        vw = VERT_WIDTH_USD[kind]
        for off in ATM_ORDER:
            k1 = base + off * step
            if abs(k1 - base) > 0.07 * spot:
                continue
            k2 = int(round((k1 + vw) / step) * step)
            r1, r2 = premium_at("C", k1, exp, entry_ts), premium_at("C", k2, exp, entry_ts)'''

assert src.count(OLD4) == 1, "fix4 anchor not found"
src = src.replace(OLD4, NEW4)

OLD5 = '''        for off in ATM_ORDER:
            k = base + off * step
            opts = []
            for t in ("C", "P"):'''

NEW5 = '''        for off in ATM_ORDER:
            k = base + off * step
            if abs(k - base) > 0.07 * spot:
                continue
            opts = []
            for t in ("C", "P"):'''

assert src.count(OLD5) == 1, "fix5 anchor not found"
src = src.replace(OLD5, NEW5)

# Fix 6: VERT_WIDTH_STEPS -> VERT_WIDTH_USD fixed dollar width
OLD6 = 'VERT_WIDTH_STEPS = {"weekly": 2, "monthly": 3}'
NEW6 = 'VERT_WIDTH_USD = {"weekly": 2000, "monthly": 5000}'
assert src.count(OLD6) == 1, "fix6 anchor not found"
src = src.replace(OLD6, NEW6)

# Fix 2: simulate() must return exit_ts; use it for exit= print and TRAIN/TEST bucketing
OLD7 = '''                res[v] = (reason, pnl, entry_fee + xf)
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
    return res'''

NEW7 = '''                res[v] = (reason, pnl, entry_fee + xf, cur)
                active.remove(v)
        cur += STEP
    if active:
        if settle_ts > int(time.time()):
            for v in active:
                res[v] = ("UNSETTLED", None, None, None)
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
                res[v] = ("EXPIRY", pnl, entry_fee + xf, settle_ts) if ok else ("UNSETTLED", None, None, None)
    return res'''

assert src.count(OLD7) == 1, "fix7a anchor not found"
src = src.replace(OLD7, NEW7)

# also fix STALE_EXIT tuple to include cur as exit_ts
OLD7b = '''                    for v in list(active):
                        res[v] = ("STALE_EXIT", fx[0], entry_fee + fx[1])
                    active = []
                    break'''
NEW7b = '''                    for v in list(active):
                        res[v] = ("STALE_EXIT", fx[0], entry_fee + fx[1], cur)
                    active = []
                    break'''
assert src.count(OLD7b) == 1, "fix7b anchor not found"
src = src.replace(OLD7b, NEW7b)

# Fix 2 continued: run_group uses exit_ts from res tuple for print + TRAIN/TEST bucketing
OLD8 = '''        for v in VARIANTS:
            mode, pnl_raw, fee_raw = res[v]'''
NEW8 = '''        for v in VARIANTS:
            mode, pnl_raw, fee_raw, exit_ts = res[v]
            exit_date = datetime.fromtimestamp(exit_ts, tz=timezone.utc).date() if exit_ts else exp'''
assert src.count(OLD8) == 1, "fix8 anchor not found"
src = src.replace(OLD8, NEW8)

OLD9 = '''            if pnl_raw is None:
                print(f"{tag} entry={entry_date} exit={exp} dte={dte} {info} {wtxt} "'''
NEW9 = '''            if pnl_raw is None:
                print(f"{tag} entry={entry_date} exit={exit_date} dte={dte} {info} {wtxt} "'''
assert src.count(OLD9) == 1, "fix9 anchor not found"
src = src.replace(OLD9, NEW9)

OLD10 = '''            net = (pnl_raw - fee_raw) * MULT
            accs[v].trade(exp, net, fee_raw * MULT)
            print(f"{tag} entry={entry_date} exit={exp} dte={dte} {info} {wtxt} "'''
NEW10 = '''            net = (pnl_raw - fee_raw) * MULT
            accs[v].trade(exit_date, net, fee_raw * MULT)
            print(f"{tag} entry={entry_date} exit={exit_date} dte={dte} {info} {wtxt} "'''
assert src.count(OLD10) == 1, "fix10 anchor not found"
src = src.replace(OLD10, NEW10)

# Fix 3: breakeven display - vertical_debit uses long strike not short; calendars show NA
OLD11 = '''            sc_leg = next((l for l in legs if l["role"] == "S" and l["type"] == "C"), None)
            sp_leg = next((l for l in legs if l["role"] == "S" and l["type"] == "P"), None)
            if sc_leg and sp_leg:
                be_hi = sc_leg["strike"] + basis
                be_lo = sp_leg["strike"] - basis
                be_disp = f"be_range={(be_lo - spot_px) / spot_px * 100:+.2f}%/{(be_hi - spot_px) / spot_px * 100:+.2f}%"
            elif sc_leg or sp_leg:
                leg0 = sc_leg or sp_leg
                be = leg0["strike"] + basis if leg0["type"] == "C" else leg0["strike"] - basis
                be_disp = f"be={(be - spot_px) / spot_px * 100:+.2f}%"
            else:
                be_disp = "be=NA"'''

NEW11 = '''            sc_leg = next((l for l in legs if l["role"] == "S" and l["type"] == "C"), None)
            sp_leg = next((l for l in legs if l["role"] == "S" and l["type"] == "P"), None)
            bl_leg = next((l for l in legs if l["role"] == "B" and l["type"] == "C"), None)
            if strat in CAL_KIND:
                be_disp = "be=NA"
            elif sc_leg and sp_leg:
                be_hi = sc_leg["strike"] + basis
                be_lo = sp_leg["strike"] - basis
                be_disp = f"be_range={(be_lo - spot_px) / spot_px * 100:+.2f}%/{(be_hi - spot_px) / spot_px * 100:+.2f}%"
            elif strat == "vertical_debit" and bl_leg:
                be = bl_leg["strike"] + basis
                be_disp = f"be={(be - spot_px) / spot_px * 100:+.2f}%"
            elif sc_leg or sp_leg:
                leg0 = sc_leg or sp_leg
                be = leg0["strike"] + basis if leg0["type"] == "C" else leg0["strike"] - basis
                be_disp = f"be={(be - spot_px) / spot_px * 100:+.2f}%"
            else:
                be_disp = "be=NA"'''

assert src.count(OLD11) == 1, "fix11 anchor not found"
src = src.replace(OLD11, NEW11)

open(path, "w").write(src)
print("PATCH2_OK")
