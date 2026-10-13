# funding_oi_diag.py - diagnostic only. Tests if funding rate / OI (lagged 1 bar)
# predict forward 1h/4h/1D price returns. Usage:
#   python funding_oi_diag.py data/btc_1m_delta.csv data/funding_btcusd_1h.csv data/oi_btcusd_1h.csv
import sys
import numpy as np
import pandas as pd

price_path, funding_path, oi_path = sys.argv[1], sys.argv[2], sys.argv[3]

# --- load price, build 1h/4h/1D close series ---
pdf = pd.read_csv(price_path)
pdf.columns = [c.strip().lower() for c in pdf.columns]
t = pd.to_datetime(pdf['date'].astype(str) + ' ' + pdf['time'].astype(str))
pdf.index = t
pdf = pdf.sort_index()

# --- load funding/oi (time = unix seconds) ---
def load_feature(path, name):
    df = pd.read_csv(path)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df = df.set_index('time').sort_index()
    return df['close'].rename(name)

funding = load_feature(funding_path, 'funding')
oi = load_feature(oi_path, 'oi')

def tstat_corr(x, y):
    m = (~x.isna()) & (~y.isna())
    x, y = x[m], y[m]
    n = len(x)
    if n < 30:
        return np.nan, np.nan, n
    r = np.corrcoef(x, y)[0, 1]
    t = r * np.sqrt((n - 2) / (1 - r ** 2 + 1e-12))
    return r, t, n

for tf, label in (('1h', '1h'), ('4h', '4h'), ('1D', '1D')):
    c = pdf['close'].resample(tf).last().dropna()
    fwd_ret = c.shift(-1) / c - 1  # forward return over next bar

    f_lag = funding.resample(tf).last().reindex(c.index).shift(0)  # funding known AT bar close (lag applied via fwd_ret already being next bar)
    oi_chg = oi.resample(tf).last().pct_change().reindex(c.index)

    print(f"\n=== {label}  n={len(c)} ===")
    r, t, n = tstat_corr(f_lag, fwd_ret)
    print(f"  funding_rate(lag0) vs fwd_return : r={r:+.4f}  t={t:+.2f}  n={n}")
    r, t, n = tstat_corr(oi_chg, fwd_ret)
    print(f"  oi_pct_change(lag0) vs fwd_return: r={r:+.4f}  t={t:+.2f}  n={n}")

    # extreme funding regime: does |funding| above its 90th pct predict bigger reversal?
    f_abs = f_lag.abs()
    thresh = f_abs.quantile(0.90)
    extreme = f_abs > thresh
    if extreme.sum() > 20:
        print(f"  extreme funding (>90th pct, n={extreme.sum()}): "
              f"mean fwd_ret={fwd_ret[extreme].mean()*100:+.3f}%  "
              f"vs normal mean={fwd_ret[~extreme].mean()*100:+.3f}%")

print("\nVERDICT: |t| > 2 on any row above = statistically significant predictive signal.")
print("If all |t| < 2, funding/OI (at this lag/resolution) carry no linear forward-return signal either.")
