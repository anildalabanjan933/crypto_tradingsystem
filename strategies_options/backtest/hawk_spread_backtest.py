"""
hawk_spread_backtest.py — BTC Weekly Calendar + Ratio Spread ("Hawk Spread")
Reuses validated engine from algotest_backtest.py (fee fix, UNSETTLED fix,
two-sided slippage, trail SL anchor fix, re-cost market-price fix).

ASSUMPTIONS (Claude report-1, all labeled, confirm/change if wrong):
1. Entry: Friday 19:00 IST (fixed, not DST-adjusted)
2. Exit (Week1 expiry): Friday 17:00 IST (30 min before 17:30 IST settlement)
3. Mid-week adjustment check: Sunday 17:00 IST (one-time check, not recurring)
4. Adjustment trigger: Week1 combined sold-leg premium decayed >=25% from entry
   AND spot still between the two sold strikes at check time
5. Week2 buy legs closed together with Week1 at exit (not rolled/carried)
6. Uncapped primary run (faithful to "unlimited loss beyond breakeven" as stated)
Lot sizing: LOTS_SELL=500, LOTS_BUY=300 (5:3 ratio), CV=0.001 (same convention
as algotest_backtest.py MULT_RECOST/MULT_LAZY)
"""

import argparse
from datetime import timedelta

from algotest_backtest import (
    Series, get_candles, premium_at, find_cost_match, leg, fee, spot_at,
    Acc, summarize, daily_list, ts_of, STEP, SLIP, STRIKE_STEP, MAX_MARK_AGE,
    FetchError, _cache, SPOT, otm_strike,
)

CV = 0.001
LOTS_SELL = 500
LOTS_BUY = 300
MULT_SELL = LOTS_SELL * CV
MULT_BUY = LOTS_BUY * CV

PREMIUM_TARGET = 300.0
ADJ_DECAY_PCT = 0.25     # 25% decay trigger (test grid: 0.20/0.25/0.30/0.40)
ADJ_QTY_LOTS = 500       # matches Week1 sell qty
ADJ_MULT = ADJ_QTY_LOTS * CV


def next_friday(d):
    days_ahead = (4 - d.weekday()) % 7
    days_ahead = 7 if days_ahead == 0 else days_ahead
    return d + timedelta(days=days_ahead)


def atm_strike(spot_px):
    return round(spot_px / STRIKE_STEP) * STRIKE_STEP


def run_hawk_variant(a, b, adj_decay=ADJ_DECAY_PCT):
    tag = "hawk_spread"
    acc = Acc()
    trades = []

    fridays = []
    d = a
    while d <= b:
        if d.weekday() == 4:
            fridays.append(d)
        d += timedelta(days=1)

    def skip(reason):
        acc.skips[reason] = acc.skips.get(reason, 0) + 1

    for fri in fridays:
        _cache.clear()
        entry_ts = ts_of(fri, 19, 0)
        week1_exp = next_friday(fri)          # Week1 = next Friday (7 DTE)
        week2_exp = next_friday(week1_exp)     # Week2 = Friday after (14 DTE)
        exit_ts = ts_of(week1_exp, 17, 0)
        adj_ts = ts_of(fri + timedelta(days=2), 17, 0)  # Sunday 17:00 IST

        try:
            sc = get_candles(SPOT, entry_ts, exit_ts + 2 * STEP)
            if not sc:
                skip("NO_DATA"); continue
            spot_series = Series(sc)
            spot_px = spot_series.mark_price(entry_ts)
            if spot_px is None:
                skip("NO_DATA"); continue

            atm = atm_strike(spot_px)

            # Week1 sold legs: strike where premium ~= PREMIUM_TARGET
            cres = find_cost_match("C", +1, week1_exp, entry_ts, PREMIUM_TARGET, atm)
            pres = find_cost_match("P", -1, week1_exp, entry_ts, PREMIUM_TARGET, atm)
            if not cres or not pres:
                skip("NO_FILL"); continue
            ck, cr = cres
            pk, pr = pres

            # Week2 bought legs: strike where premium ~= PREMIUM_TARGET
            cres2 = find_cost_match("C", +1, week2_exp, entry_ts, PREMIUM_TARGET, atm)
            pres2 = find_cost_match("P", -1, week2_exp, entry_ts, PREMIUM_TARGET, atm)
            if not cres2 or not pres2:
                skip("NO_FILL"); continue
            ck2, cr2 = cres2
            pk2, pr2 = pres2

            w1 = {
                "C": {"leg": leg("S", "C", ck, week1_exp, cr), "series": None, "pnl": 0.0, "fee": 0.0},
                "P": {"leg": leg("S", "P", pk, week1_exp, pr), "series": None, "pnl": 0.0, "fee": 0.0},
            }
            w2 = {
                "C": {"leg": leg("B", "C", ck2, week2_exp, cr2), "series": None, "pnl": 0.0, "fee": 0.0},
                "P": {"leg": leg("B", "P", pk2, week2_exp, pr2), "series": None, "pnl": 0.0, "fee": 0.0},
            }
            for grp in (w1, w2):
                for side in ("C", "P"):
                    l = grp[side]["leg"]
                    grp[side]["series"] = Series(get_candles(l["symbol"], entry_ts, exit_ts + 2 * STEP))

            entry_fee_raw = (fee(spot_px, cr[1]) + fee(spot_px, pr[1])) * MULT_SELL + (fee(spot_px, cr2[1]) + fee(spot_px, pr2[1])) * MULT_BUY

            adj = {"active": False, "C": None, "P": None}
            adj_checked = False
            cur = max(cr[2], pr[2], cr2[2], pr2[2]) + STEP

            while cur < exit_ts:
                if not adj_checked and cur >= adj_ts:
                    adj_checked = True
                    mC, ageC = w1["C"]["series"].mark_with_age(adj_ts)
                    mP, ageP = w1["P"]["series"].mark_with_age(adj_ts)
                    adj_spot = spot_series.mark_price(adj_ts)
                    if mC is not None and mP is not None and ageC <= MAX_MARK_AGE and ageP <= MAX_MARK_AGE and adj_spot is not None:
                        entry_combined = w1["C"]["leg"]["mkt"] + w1["P"]["leg"]["mkt"]
                        cur_combined = mC + mP
                        decayed_pct = (entry_combined - cur_combined) / entry_combined if entry_combined else 0
                        in_range = pk < adj_spot < ck
                        if decayed_pct >= adj_decay and in_range:
                            next_ck = ck + STRIKE_STEP
                            next_pk = pk - STRIKE_STEP
                            acr = premium_at("C", next_ck, week1_exp, adj_ts)
                            apr = premium_at("P", next_pk, week1_exp, adj_ts)
                            if acr and apr:
                                adj["active"] = True
                                adj["C"] = {"leg": leg("B", "C", next_ck, week1_exp, acr),
                                            "series": Series(get_candles(acr[0], adj_ts, exit_ts + 2 * STEP))}
                                adj["P"] = {"leg": leg("B", "P", next_pk, week1_exp, apr),
                                            "series": Series(get_candles(apr[0], adj_ts, exit_ts + 2 * STEP))}
                                entry_fee_raw += (fee(adj_spot, acr[1]) + fee(adj_spot, apr[1])) * ADJ_MULT
                cur += STEP

            unsettled = False
            total_pnl = 0.0
            total_fee = entry_fee_raw

            for side in ("C", "P"):
                l = w1[side]["leg"]
                px, fts = w1[side]["series"].fill_at(exit_ts)
                if px is None:
                    m, age = w1[side]["series"].mark_with_age(exit_ts)
                    if m is None or age > MAX_MARK_AGE:
                        unsettled = True; break
                    px = m
                ef = px * (1 + SLIP)
                total_pnl += (l["raw"] - ef) * MULT_SELL
                total_fee += fee(spot_at(spot_series, exit_ts, spot_px), ef) * MULT_SELL

            if not unsettled:
                for side in ("C", "P"):
                    l = w2[side]["leg"]
                    px, fts = w2[side]["series"].fill_at(exit_ts)
                    if px is None:
                        m, age = w2[side]["series"].mark_with_age(exit_ts)
                        if m is None or age > MAX_MARK_AGE:
                            unsettled = True; break
                        px = m
                    ef = px * (1 - SLIP)
                    total_pnl += (ef - l["raw"]) * MULT_BUY
                    total_fee += fee(spot_at(spot_series, exit_ts, spot_px), ef) * MULT_BUY

            if not unsettled and adj["active"]:
                for side in ("C", "P"):
                    l = adj[side]["leg"]
                    px, fts = adj[side]["series"].fill_at(exit_ts)
                    if px is None:
                        m, age = adj[side]["series"].mark_with_age(exit_ts)
                        if m is None or age > MAX_MARK_AGE:
                            unsettled = True; break
                        px = m
                    ef = px * (1 - SLIP)
                    total_pnl += (ef - l["raw"]) * ADJ_MULT
                    total_fee += fee(spot_at(spot_series, exit_ts, spot_px), ef) * ADJ_MULT

            if unsettled:
                skip("UNSETTLED")
                continue

            net = total_pnl - total_fee
            acc.trade(fri, net, total_fee)
            trades.append((fri, net, total_fee))
            adj_flag = "ADJ=Y" if adj["active"] else "ADJ=N"
            print(f"[{tag}] {fri} W1 C={ck}@{cr[1]:.0f} P={pk}@{pr[1]:.0f} "
                  f"W2 C={ck2}@{cr2[1]:.0f} P={pk2}@{pr2[1]:.0f} {adj_flag} "
                  f"pnl=${net:.2f} equity=${acc.eq:.2f}")

        except FetchError as ex:
            print(f"WARNING {fri} {ex}")
            skip("FETCH_FAIL")
            continue

    years = max((b - a).days / 365.25, 0.01)
    summarize(f"[{tag}]", acc, years)
    return acc, trades


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    args = ap.parse_args()
    from datetime import datetime
    a = datetime.strptime(args.start, "%Y-%m-%d").date()
    b = datetime.strptime(args.end, "%Y-%m-%d").date()
    print(f"WINDOW {a} to {b} | strategy=hawk_spread")
    run_hawk_variant(a, b)
