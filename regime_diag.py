# regime_diag.py - diagnostic only (NOT a strategy). Usage:
#   python regime_diag.py data/btc_1m_delta.csv 2024-01-01 2025-06-30
import sys
import numpy as np
import pandas as pd

path = sys.argv[1]
start = sys.argv[2] if len(sys.argv) > 2 else None
end = sys.argv[3] if len(sys.argv) > 3 else None
COST, BTC = 24.0, 0.1   # $ round trip, position size at 100 lots

df = pd.read_csv(path)
df.columns = [c.strip().lower() for c in df.columns]
if 'date' in df.columns and 'time' in df.columns:
    t = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'].astype(str))
else:
    tcol = next((c for c in ('timestamp', 'datetime', 'time', 'date', 'open_time') if c in df.columns), df.columns[0])
    t = df[tcol]
    t = pd.to_datetime(t, unit='s') if pd.api.types.is_numeric_dtype(t) and t.iloc[0] < 4e9 else \
        pd.to_datetime(t, unit='ms') if pd.api.types.is_numeric_dtype(t) else pd.to_datetime(t)
df.index = t
df = df.sort_index()
if start: df = df[df.index >= start]
if end: df = df[df.index <= end + ' 23:59:59']
print(f"rows={len(df)}  {df.index[0]} -> {df.index[-1]}")

def ac(r, k):
    r = r - r.mean()
    return float((r[k:] * r[:-k]).sum() / (r * r).sum())

def vr(r, q):
    n = len(r); m = r.mean()
    s1 = ((r - m) ** 2).sum() / n
    rq = r.rolling(q).sum().dropna()
    sq = ((rq - q * m) ** 2).sum() / (len(rq) * q)
    v = sq / s1
    z = (v - 1) / np.sqrt(2 * (2 * q - 1) * (q - 1) / (3 * q * n))
    return float(v), float(z)

PER_YR = {'1h': 8766, '4h': 2191.5, '1D': 365.25}
for tf in ('1h', '4h', '1D'):
    c = df['close'].resample(tf).last().dropna()
    r = np.log(c).diff().dropna()
    n = len(r)
    print(f"\n=== {tf}  n={n}  ann.vol={r.std()*np.sqrt(PER_YR[tf])*100:.0f}%  "
          f"mean|move| per 0.1 BTC = ${(c.diff().abs().mean()*BTC):.1f}  "
          f"(= {c.diff().abs().mean()*BTC/COST:.2f}x cost)")
    for k in (1, 2, 3):
        a = ac(r.values, k)
        print(f"  autocorr lag{k}: {a:+.3f}  t={a*np.sqrt(n):+.2f}")
    for q in (2, 4, 8):
        v, z = vr(r, q)
        print(f"  variance ratio q={q}: {v:.3f}  z={z:+.2f}   (>1 trending, <1 mean-reverting)")

c4 = df['close'].resample('4h').last().dropna()
W = 20
er = (c4 - c4.shift(W)).abs() / c4.diff().abs().rolling(W).sum()
er = er.dropna()
print(f"\n=== Trend vs chop (4h, Kaufman efficiency ratio, {W} bars)")
print(f"  median ER={er.median():.2f}  trending(ER>0.30)={100*(er>0.30).mean():.0f}%  "
      f"chop(ER<0.15)={100*(er<0.15).mean():.0f}%  (pure random walk median ER ~0.17)")

print("\n=== Stability by quarter (4h): return %, lag1 autocorr, variance ratio q=4")
r4 = np.log(c4).diff().dropna()
for q, g in r4.groupby(r4.index.to_period('Q')):
    if len(g) > 60:
        print(f"  {q}: ret={100*g.sum():+6.1f}%  ac1={ac(g.values,1):+.3f}  VR4={vr(g,4)[0]:.2f}")

sig = []
for tf in ('1h', '4h', '1D'):
    r = np.log(df['close'].resample(tf).last().dropna()).diff().dropna()
    sig.append(abs(ac(r.values, 1)) * np.sqrt(len(r)) > 2)
    sig += [abs(vr(r, q)[1]) > 2 for q in (2, 4, 8)]
print("\nVERDICT:", "some linear structure detected - see rows with |t| or |z| > 2"
      if any(sig) else "NO statistically significant linear structure at 1h/4h/1D. Simple trend/"
      "mean-reversion rules have no edge to harvest in this window; net = -cost x trades.")
