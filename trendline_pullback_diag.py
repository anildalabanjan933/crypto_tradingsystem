# trendline_pullback_diag.py - DIAGNOSTIC ONLY (not a strategy).
# Compares 2-touch vs 3-touch trendline validation, with/without "near EMA" filter.
# Usage: python3 trendline_pullback_diag.py data/btc_1m_delta.csv 2024-01-01 2025-06-30 [box_pct]
import sys
import numpy as np
import pandas as pd
import math

path = sys.argv[1]
start = sys.argv[2] if len(sys.argv) > 2 else None
end = sys.argv[3] if len(sys.argv) > 3 else None
BOX_PCT = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0025

N_TREND = 5          # bricks to establish a trend
SWING_L = 2          # swing pivot left window
SWING_R = 2          # swing pivot right window
TOUCH_TOL_BOXES = 1.0   # tolerance (in box units) for a point to "touch" the line
EMA_PERIOD = 20
EMA_NEAR_PCT = 0.003    # 0.3% band around EMA counts as "near"

# ---------- load data ----------
df = pd.read_csv(path)
df.columns = [c.strip().lower() for c in df.columns]
if 'date' in df.columns and 'time' in df.columns:
    t = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'].astype(str))
else:
    tcol = next((c for c in ('timestamp','datetime','time','date') if c in df.columns), df.columns[0])
    t = pd.to_datetime(df[tcol])
df.index = t
df = df.sort_index()
if start: df = df[df.index >= start]
if end: df = df[df.index <= end + ' 23:59:59']
closes = df['close'].values
print(f"rows={len(df)}  box_pct={BOX_PCT}  {df.index[0]} -> {df.index[-1]}")

# ---------- build renko bricks (self-contained, same algo as RenkoBuilder) ----------
anchor = closes[0]
box = max(1e-9, anchor * BOX_PCT)
r_open, r_close, r_dir = anchor, anchor, 0
recs = []
for i in range(len(closes)):
    close = closes[i]
    if r_dir >= 0:
        up_t, dn_t = r_open + box, r_open - box*2
    else:
        up_t, dn_t = r_open + box*2, r_open - box
    if close >= up_t:
        n_up = int((close - (r_open+box))/box) if r_dir < 0 else int((close - r_open)/box)
        for _ in range(n_up):
            r_open = r_open if r_dir >= 0 else r_open + box
            r_close = r_open + box
            r_dir = 1
            recs.append((i, r_open, r_close, r_dir, closes[i]))
            r_open = r_close
    elif close <= dn_t:
        n_dn = int(((r_open-box)-close)/box) if r_dir > 0 else int((r_open-close)/box)
        for _ in range(n_dn):
            r_open = r_open if r_dir <= 0 else r_open - box
            r_close = r_open - box
            r_dir = -1
            recs.append((i, r_open, r_close, r_dir, closes[i]))
            r_open = r_close

brk = pd.DataFrame(recs, columns=['bar_index','r_open','r_close','r_dir','real_close'])
n = len(brk)
print(f"bricks built: {n}")
if n < 50:
    print("Too few bricks, aborting."); sys.exit(0)

r_close_arr = brk['r_close'].values
r_dir_arr = brk['r_dir'].values
real_close_arr = brk['real_close'].values

# ---------- EMA on renko_close ----------
ema = pd.Series(r_close_arr).ewm(span=EMA_PERIOD, adjust=False).mean().values

# ---------- swing pivot detection (full history, renko_close as price) ----------
is_sh = np.zeros(n, dtype=bool)
is_sl = np.zeros(n, dtype=bool)
for i in range(SWING_L, n - SWING_R):
    w = r_close_arr[i-SWING_L:i+SWING_R+1]
    c = r_close_arr[i]
    if c == w.max() and np.sum(w == c) == 1:
        is_sh[i+SWING_R] = True
    if c == w.min() and np.sum(w == c) == 1:
        is_sl[i+SWING_R] = True

swing_highs_all = []  # (bar_idx, price) full history, confirmed causally
swing_lows_all = []

def trend_val(points, idx):
    """points: list of (bar_idx, price), oldest first. Project line to idx."""
    if len(points) < 2:
        return None
    (b1,p1),(b2,p2) = points[-2], points[-1]
    if b2 == b1:
        return p2
    slope = (p2-p1)/(b2-b1)
    return p2 + slope*(idx-b2)

def touches_within_tol(points, tol_price):
    """Check if 3rd-most-recent point lies within tol of line from last 2."""
    if len(points) < 3:
        return False
    (b1,p1),(b2,p2) = points[-2], points[-1]
    b0,p0 = points[-3]
    if b2 == b1:
        return abs(p0-p2) <= tol_price
    slope = (p2-p1)/(b2-b1)
    proj = p2 + slope*(b0-b2)
    return abs(p0-proj) <= tol_price

tol_price = box * TOUCH_TOL_BOXES

def run_variant(require_3touch, require_near_ema):
    trades = []
    trend_dir = 0
    run_count = 0
    position = None  # (direction, entry_idx, entry_price)
    local_highs, local_lows = [], []

    for i in range(n):
        if is_sh[i]:
            local_highs = (local_highs + [(i, r_close_arr[i])])[-6:]
        if is_sl[i]:
            local_lows = (local_lows + [(i, r_close_arr[i])])[-6:]

        d = r_dir_arr[i]
        if trend_dir == 0:
            trend_dir = d; run_count = 1
        elif d == trend_dir:
            run_count += 1
        else:
            if run_count >= N_TREND:
                pass  # established trend now in pullback
            run_count = 1
            trend_dir_pullback_opposite = True

        established = run_count >= N_TREND or (trend_dir != 0)
        # manage exit first
        if position is not None:
            pdir, eidx, eprice = position
            if d == -pdir:
                xprice = real_close_arr[i]
                bps = ((xprice - eprice)/eprice)*1e4*(1 if pdir==1 else -1)
                trades.append(bps)
                position = None

        if position is None and trend_dir != 0:
            if trend_dir == 1 and d == -1:
                pts = local_highs
            elif trend_dir == -1 and d == 1:
                pts = local_lows
            else:
                pts = None

            if pts is not None and len(pts) >= 2:
                valid = True
                if require_3touch:
                    valid = touches_within_tol(pts, tol_price)
                if valid:
                    line_val = trend_val(pts, i)
                    if line_val is not None:
                        broke_up = trend_dir == 1 and r_close_arr[i] > line_val
                        broke_dn = trend_dir == -1 and r_close_arr[i] < line_val
                        if broke_up or broke_dn:
                            near_ema_ok = True
                            if require_near_ema:
                                near_ema_ok = abs(r_close_arr[i]-ema[i])/max(ema[i],1e-9) <= EMA_NEAR_PCT
                            if near_ema_ok:
                                position = (trend_dir, i, real_close_arr[i])

        if trend_dir == 0 or d != trend_dir:
            if d != trend_dir and trend_dir != 0:
                pass
        if d == trend_dir:
            pass
        else:
            trend_dir = trend_dir if run_count < N_TREND else trend_dir
        if run_count == 1 and d != trend_dir:
            trend_dir = trend_dir
        if i > 0 and d == r_dir_arr[i-1]:
            pass
        trend_dir = trend_dir if trend_dir != 0 else d

    return trades

def report(name, trades):
    n_t = len(trades)
    if n_t < 10:
        print(f"{name:28s}  n={n_t:5d}  (too few trades to assess)")
        return
    arr = np.array(trades)
    mean_bps = arr.mean()
    win_rate = (arr > 0).mean()*100
    se = arr.std(ddof=1)/math.sqrt(n_t)
    t = mean_bps/se if se > 0 else 0.0
    print(f"{name:28s}  n={n_t:5d}  mean={mean_bps:7.2f}bps  win%={win_rate:5.1f}  t={t:+.2f}  "
          f"{'SIG' if abs(t) > 2 else '---'}")

print("\n=== TRENDLINE PULLBACK-BREAK: 2-touch vs 3-touch, with/without near-EMA filter ===")
report("2-touch, no EMA filter",      run_variant(False, False))
report("2-touch, WITH near-EMA",      run_variant(False, True))
report("3-touch, no EMA filter",      run_variant(True,  False))
report("3-touch, WITH near-EMA",      run_variant(True,  True))

print("\nNote: mean bps needs to clear ~30-40bps net of cost (~$20-28/trade on ~100 lot) to be worth building as a strategy.")
print("t with |t|>2 is a rough significance flag only, not a holdout test.")
