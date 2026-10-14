# candle_scan_diag.py - DIAGNOSTIC ONLY (not a strategy).
# Usage: python candle_scan_diag.py data/btc_1m_delta.csv 2024-01-01 2025-06-30
import sys, math
import numpy as np
import pandas as pd

path = sys.argv[1]
start = sys.argv[2] if len(sys.argv) > 2 else None
end = sys.argv[3] if len(sys.argv) > 3 else None
MIN_BPS, ALPHA, MIN_N = 30.0, 0.05, 30

df = pd.read_csv(path)
df.columns = [c.strip().lower() for c in df.columns]
tcol = next((c for c in ('timestamp', 'datetime', 'time', 'date', 'open_time') if c in df.columns), df.columns[0])
t = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'].astype(str)) if 'date' in df.columns and 'time' in df.columns else df[tcol]
if pd.api.types.is_numeric_dtype(t):
    t = pd.to_datetime(t, unit='s' if t.iloc[0] < 4e9 else 'ms')
else:
    t = pd.to_datetime(t)
df.index = t
df = df.sort_index()
if start: df = df[df.index >= start]
if end: df = df[df.index <= end + ' 23:59:59']
print(f"rows={len(df)}  {df.index[0]} -> {df.index[-1]}")

def patterns(o, h, l, c):
    rng = np.maximum(h - l, 1e-9)
    body = np.abs(c - o)
    up, dn = c > o, c < o
    uw = h - np.maximum(o, c)
    lw = np.minimum(o, c) - l
    s = lambda x, k: pd.Series(x).shift(k).fillna(False).values
    po, ph, pl, pc = (pd.Series(x).shift(1).values for x in (o, h, l, c))
    pup, pdn = s(up, 1), s(dn, 1)
    pbody = pd.Series(body).shift(1).values
    P = {}
    P['bull_engulf'] = (up & pdn & (c >= po) & (o <= pc)) * 1
    P['bear_engulf'] = (dn & pup & (c <= po) & (o >= pc)) * -1
    P['bull_harami'] = (up & pdn & (c < po) & (o > pc) & (body < pbody)) * 1
    P['bear_harami'] = (dn & pup & (c > po) & (o < pc) & (body < pbody)) * -1
    P['hammer'] = ((lw >= 2 * body) & (lw >= .6 * rng) & (c >= l + .66 * rng)) * 1
    P['shooting_star'] = ((uw >= 2 * body) & (uw >= .6 * rng) & (c <= l + .34 * rng)) * -1
    P['bull_pin_follow'] = ((lw >= .6 * rng) & (c >= o)) * 1
    P['bear_pin_follow'] = ((uw >= .6 * rng) & (c <= o)) * -1
    doji = body <= .1 * rng
    run3dn = s(dn, 1) & s(dn, 2) & s(dn, 3); run3up = s(up, 1) & s(up, 2) & s(up, 3)
    P['doji_rev_long'] = (doji & run3dn) * 1
    P['doji_rev_short'] = (doji & run3up) * -1
    inside = (h < ph) & (l > pl)
    P['inside_cont'] = (inside * np.where(pup, 1, np.where(pdn, -1, 0)))
    P['inside_rev'] = -P['inside_cont']
    P['outside_up'] = ((h > ph) & (l < pl) & up) * 1
    P['outside_dn'] = ((h > ph) & (l < pl) & dn) * -1
    pc2, po2 = pd.Series(c).shift(2).values, pd.Series(o).shift(2).values
    pbody2 = pd.Series(body).shift(2).values
    P['morning_star'] = (s(dn, 2) & (pd.Series(body).shift(1).values < .5 * pbody2) & up & (c > (po2 + pc2) / 2)) * 1
    P['evening_star'] = (s(up, 2) & (pd.Series(body).shift(1).values < .5 * pbody2) & dn & (c < (po2 + pc2) / 2)) * -1
    P['three_soldiers'] = (up & pup & s(up, 2) & (c > pc) & (pc > pc2)) * 1
    P['three_crows'] = (dn & pdn & s(dn, 2) & (c < pc) & (pc < pc2)) * -1
    P['marubozu_up'] = (up & (body >= .9 * rng)) * 1
    P['marubozu_dn'] = (dn & (body >= .9 * rng)) * -1
    P['tweezer_bottom'] = ((np.abs(l - pl) <= .02 * rng) & pdn & up) * 1
    P['tweezer_top'] = ((np.abs(h - ph) <= .02 * rng) & pup & dn) * -1
    P['piercing'] = (up & pdn & (o < pc) & (c > (po + pc) / 2) & (c < po)) * 1
    P['dark_cloud'] = (dn & pup & (o > pc) & (c < (po + pc) / 2) & (c > po)) * -1
    return {k: np.nan_to_num(np.asarray(v, dtype=float)).astype(int) for k, v in P.items()}

def pval(z):
    return math.erfc(abs(z) / math.sqrt(2))

rows = []
for tf in ('30min', '1h', '2h', '4h', '1D'):
    b = df.resample(tf).agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    o, h, l, c = (b[x].values for x in ('open', 'high', 'low', 'close'))
    lc = np.log(c)
    for name, side in patterns(o, h, l, c).items():
        for hz in (1, 2, 3, 4):
            fwd = np.full(len(c), np.nan)
            fwd[:-hz] = (lc[hz:] - lc[:-hz]) * 1e4
            m = (side != 0) & np.isfinite(fwd)
            n = int(m.sum())
            if n < MIN_N:
                continue
            x = fwd[m] * side[m]
            n_eff = max(n / hz, 2)
            se = x.std(ddof=1) / math.sqrt(n_eff)
            z = x.mean() / se if se > 0 else 0.0
            rows.append((tf, name, hz, n, x.mean(), z, pval(z)))

res = pd.DataFrame(rows, columns=['tf', 'pattern', 'h_bars', 'n', 'mean_bps', 'z', 'p'])
M = len(res)
bonf = ALPHA / M
res['bonf_sig'] = res['p'] < bonf
res['clears_30bps'] = res['mean_bps'].abs() >= MIN_BPS
print(f"\ntests run (pattern x tf x horizon, n>={MIN_N}): {M}")
print(f"uncorrected p<0.05: {(res.p < .05).sum()}  (expected by luck alone ~{M*.05:.0f})")
print(f"Bonferroni threshold: p < {bonf:.2e}")
print("\nTOP 12 by p-value:")
print(res.sort_values('p').head(12).to_string(index=False, float_format=lambda v: f"{v:.4g}"))
print(f"\nlargest |mean| anywhere: {res.mean_bps.abs().max():.1f} bps  "
      f"(tests with |mean|>=30bps: {int(res.clears_30bps.sum())}, "
      f"of which median n = {res[res.clears_30bps].n.median() if res.clears_30bps.any() else 0})")
both = res[res.bonf_sig & res.clears_30bps]
print(f"\nSURVIVED Bonferroni AND >=30 bps: {len(both)}")
if len(both):
    print(both.to_string(index=False, float_format=lambda v: f"{v:.4g}"))
print("\nVERDICT:", "YES - candidates found; re-test them on the holdout before anything else."
      if len(both) else "NO pattern survives multiple-testing correction AND clears 30 bps.")
