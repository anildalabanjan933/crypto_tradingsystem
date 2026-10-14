# validate_renko_signals.py
# Purpose: Validate Renko signal logic using 2h OHLCV data
# Matches Delta Exchange chart: 2h Renko, Traditional, Box=200

import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════════════
# SETTINGS - match exactly with your Delta chart
# ═══════════════════════════════════════════════════════════════
CSV_PATH     = "data/btc_2h_delta.csv"
RENKO_BOX    = 200
ST_ATR_LEN   = 5
ST_FACTOR    = 4.0
SWING_LEFT   = 2
SWING_RIGHT  = 2
SR_TOLERANCE = 0.5

# ═══════════════════════════════════════════════════════════════
# STEP 1: LOAD DATA
# ═══════════════════════════════════════════════════════════════
def load_data(csv_path):
    df = pd.read_csv(csv_path)
    df.columns = [c.lower().strip() for c in df.columns]

    if 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'], utc=True)
    else:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)

    df = df.sort_values('datetime').reset_index(drop=True)

    before = len(df)
    df = df[df['volume'] > 0].reset_index(drop=True)
    after = len(df)

    df = df[~((df['open'] == df['high']) &
              (df['high'] == df['low'])  &
              (df['low']  == df['close']))].reset_index(drop=True)

    print(f"Loaded {before} bars | Removed {before - after} zero-volume bars")
    print(f"Clean bars: {len(df)} | "
          f"{df['datetime'].iloc[0].strftime('%Y-%m-%d')} to "
          f"{df['datetime'].iloc[-1].strftime('%Y-%m-%d')}")
    return df

# ═══════════════════════════════════════════════════════════════
# STEP 2: RENKO BAR SIMULATION  ← CORE FIX HERE
#
# Traditional Renko rules:
#   - Each bar has a fixed open and close exactly 1 box apart
#   - A new UP bar forms when price >= current_open + box
#     (if already going up) or current_open + 2*box (reversal from down)
#   - A new DOWN bar forms when price <= current_open - box
#     (if already going down) or current_open - 2*box (reversal from up)
#   - After forming a new bar, r_open STEPS FORWARD to the new bar's open
#     so the next bar's threshold is relative to the NEW open, not the old one
#
# The fix: after each new bar, advance r_open by exactly box_size in the
# direction of the new bar. This allows multiple bars to form from a single
# large candle and keeps thresholds moving with price.
# ═══════════════════════════════════════════════════════════════
def simulate_renko(df, box_size=200):
    closes = df['close'].values
    n      = len(closes)

    # We store the renko state at each 2h bar timestamp
    renko_open  = np.zeros(n)
    renko_close = np.zeros(n)
    renko_dir   = np.zeros(n, dtype=int)

    # Seed: first close rounded down to nearest box boundary
    first_close = closes[0]
    r_open  = np.floor(first_close / box_size) * box_size
    r_close = r_open          # direction unknown yet, treat as neutral
    r_dir   = 0               # 0 = not yet established

    for i in range(n):
        close = closes[i]

        # ── Thresholds depend on current direction ──────────────
        # Going up (or neutral): need 1 box above open to continue up
        #                        need 2 boxes below open to reverse down
        # Going down (or neutral): need 1 box below open to continue down
        #                          need 2 boxes above open to reverse up
        if r_dir >= 0:
            up_threshold   = r_open + box_size
            down_threshold = r_open - box_size * 2
        else:
            up_threshold   = r_open + box_size * 2
            down_threshold = r_open - box_size

        if close >= up_threshold:
            # ── New UP bar(s) formed ─────────────────────────────
            # If reversing from down, first step open up by 1 box
            if r_dir < 0:
                r_open = r_open + box_size   # reversal: open of first up bar
            # Now advance open to the highest complete box boundary
            # (handles case where price jumped multiple boxes)
            boxes_up = int((close - r_open) / box_size)
            if boxes_up >= 1:
                r_open  = r_open + (boxes_up - 1) * box_size
                r_close = r_open + box_size
                r_dir   = 1

        elif close <= down_threshold:
            # ── New DOWN bar(s) formed ───────────────────────────
            # If reversing from up, first step open down by 1 box
            if r_dir > 0:
                r_open = r_open - box_size   # reversal: open of first down bar
            # Advance open to the lowest complete box boundary
            boxes_dn = int((r_open - close) / box_size)
            if boxes_dn >= 1:
                r_open  = r_open - (boxes_dn - 1) * box_size
                r_close = r_open - box_size
                r_dir   = -1

        # If neither threshold hit, renko state is unchanged
        renko_open[i]  = r_open
        renko_close[i] = r_close
        renko_dir[i]   = r_dir

    df['renko_open']  = renko_open
    df['renko_close'] = renko_close
    df['renko_dir']   = renko_dir
    df['renko_bull']  = (df['renko_dir'] == 1)
    df['renko_bear']  = (df['renko_dir'] == -1)

    dir_changes = (df['renko_dir'] != df['renko_dir'].shift(1)).sum()
    print(f"Renko: {dir_changes} direction changes | "
          f"Bull bars: {df['renko_bull'].sum()} | "
          f"Bear bars: {df['renko_bear'].sum()}")
    return df

# ═══════════════════════════════════════════════════════════════
# STEP 3: SUPERTREND
# Uses actual OHLC high/low for ATR (not renko high/low)
# Uses renko_close for direction decisions (matches Pine Script)
# Direction: -1 = bullish (green), +1 = bearish (red)
# ═══════════════════════════════════════════════════════════════
def compute_supertrend(df, atr_len=5, factor=4.0):
    high  = df['high'].values
    low   = df['low'].values
    close = df['close'].values
    rc    = df['renko_close'].values
    n     = len(df)

    # True Range using actual OHLC
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low,
         np.maximum(np.abs(high - prev_close),
                    np.abs(low  - prev_close)))

    # Wilder's smoothed ATR (RMA) - matches Pine Script ta.atr()
    # RMA: atr[i] = atr[i-1] * (len-1)/len + tr[i] * 1/len
    alpha = 1.0 / atr_len
    atr   = np.zeros(n)
    atr[0] = tr[0]
    for i in range(1, n):
        atr[i] = atr[i-1] * (1 - alpha) + tr[i] * alpha

    hl2 = (high + low) / 2.0

    upper_band = np.zeros(n)
    lower_band = np.zeros(n)
    supertrend = np.zeros(n)
    direction  = np.zeros(n, dtype=int)

    upper_band[0] = hl2[0] + factor * atr[0]
    lower_band[0] = hl2[0] - factor * atr[0]
    direction[0]  = 1          # start bearish until proven otherwise
    supertrend[0] = upper_band[0]

    for i in range(1, n):
        ub_raw = hl2[i] + factor * atr[i]
        lb_raw = hl2[i] - factor * atr[i]

        # Lower band: only allowed to rise (tightens from below)
        # Reset if previous renko_close broke below it
        if lb_raw > lower_band[i-1] or rc[i-1] < lower_band[i-1]:
            lower_band[i] = lb_raw
        else:
            lower_band[i] = lower_band[i-1]

        # Upper band: only allowed to fall (tightens from above)
        # Reset if previous renko_close broke above it
        if ub_raw < upper_band[i-1] or rc[i-1] > upper_band[i-1]:
            upper_band[i] = ub_raw
        else:
            upper_band[i] = upper_band[i-1]

        # Direction flip using renko_close
        if direction[i-1] == 1:
            # Was bearish: flip to bullish if renko_close crosses above upper band
            direction[i] = -1 if rc[i] > upper_band[i] else 1
        else:
            # Was bullish: flip to bearish if renko_close crosses below lower band
            direction[i] = 1 if rc[i] < lower_band[i] else -1

        supertrend[i] = lower_band[i] if direction[i] == -1 else upper_band[i]

    df['st_line']      = supertrend
    df['st_direction'] = direction
    df['st_bull']      = (direction == -1)   # -1 = green = bullish
    df['st_bear']      = (direction ==  1)   # +1 = red   = bearish

    print(f"Supertrend: Bull bars: {df['st_bull'].sum()} | "
          f"Bear bars: {df['st_bear'].sum()}")
    return df

# ═══════════════════════════════════════════════════════════════
# STEP 4: SWING HIGHS / LOWS
# Pivot on renko_close: center bar is strict max/min in window
# Confirmed after swing_right bars have passed
# ═══════════════════════════════════════════════════════════════
def compute_swings(df, left=2, right=2):
    rc = df['renko_close'].values
    n  = len(rc)

    swing_high = np.full(n, np.nan)
    swing_low  = np.full(n, np.nan)

    for i in range(left, n - right):
        window = rc[i - left: i + right + 1]
        center = rc[i]

        if center == np.max(window) and np.sum(window == center) == 1:
            swing_high[i + right] = center   # confirmed at bar i+right

        if center == np.min(window) and np.sum(window == center) == 1:
            swing_low[i + right] = center

    df['swing_high'] = swing_high
    df['swing_low']  = swing_low

    # Carry forward last known swing value
    df['last_swing_high'] = pd.Series(swing_high).ffill().values
    df['last_swing_low']  = pd.Series(swing_low).ffill().values

    print(f"Swings: Highs detected: {int(np.sum(~np.isnan(swing_high)))} | "
          f"Lows detected: {int(np.sum(~np.isnan(swing_low)))}")
    return df

# ═══════════════════════════════════════════════════════════════
# STEP 5: TRENDLINE BREAKOUT
# bearish_tl = last swing high (acts as resistance)
# bullish_tl = last swing low  (acts as support)
#
# BO-BUY:  renko_close crosses ABOVE last swing high + ST is bullish
# BO-SELL: renko_close crosses BELOW last swing low  + ST is bearish
# ═══════════════════════════════════════════════════════════════
def compute_trendline_breakout(df):
    rc      = df['renko_close'].values
    tl_bear = df['last_swing_high'].values   # resistance
    tl_bull = df['last_swing_low'].values    # support
    st_bull = df['st_bull'].values
    st_bear = df['st_bear'].values
    n = len(rc)

    bo_buy  = np.zeros(n, dtype=bool)
    bo_sell = np.zeros(n, dtype=bool)

    for i in range(1, n):
        # Need valid trendline values on both bars
        if np.isnan(tl_bear[i]) or np.isnan(tl_bear[i-1]):
            continue
        if np.isnan(tl_bull[i]) or np.isnan(tl_bull[i-1]):
            continue

        # Crossover above resistance trendline
        cross_above = (rc[i-1] <= tl_bear[i-1]) and (rc[i] > tl_bear[i])
        # Crossunder below support trendline
        cross_below = (rc[i-1] >= tl_bull[i-1]) and (rc[i] < tl_bull[i])

        bo_buy[i]  = cross_above and st_bull[i]
        bo_sell[i] = cross_below and st_bear[i]

    df['bo_buy']  = bo_buy
    df['bo_sell'] = bo_sell

    print(f"Trendline breakouts: BO-BUY: {bo_buy.sum()} | BO-SELL: {bo_sell.sum()}")
    return df

# ═══════════════════════════════════════════════════════════════
# STEP 6: S/R REVERSAL
# near_support    = renko_close within tolerance% of last swing low
# near_resistance = renko_close within tolerance% of last swing high
#
# REV-BUY:  near support  + renko is bullish + ST is bullish
# REV-SELL: near resistance + renko is bearish + ST is bearish
# ═══════════════════════════════════════════════════════════════
def compute_sr_reversal(df, tolerance_pct=0.5):
    tol  = tolerance_pct / 100.0
    rc   = df['renko_close'].values
    lsh  = df['last_swing_high'].values
    lsl  = df['last_swing_low'].values
    rb   = df['renko_bull'].values
    rbe  = df['renko_bear'].values
    stb  = df['st_bull'].values
    stbr = df['st_bear'].values
    n    = len(rc)

    rev_buy  = np.zeros(n, dtype=bool)
    rev_sell = np.zeros(n, dtype=bool)

    for i in range(n):
        if not np.isnan(lsl[i]) and lsl[i] > 0:
            near_support = abs(rc[i] - lsl[i]) / lsl[i] <= tol
            rev_buy[i]   = near_support and rb[i] and stb[i]

        if not np.isnan(lsh[i]) and lsh[i] > 0:
            near_resistance = abs(rc[i] - lsh[i]) / lsh[i] <= tol
            rev_sell[i]     = near_resistance and rbe[i] and stbr[i]

    df['rev_buy']  = rev_buy
    df['rev_sell'] = rev_sell

    print(f"S/R reversals: REV-BUY: {rev_buy.sum()} | REV-SELL: {rev_sell.sum()}")
    return df

# ═══════════════════════════════════════════════════════════════
# STEP 7: COMBINED SIGNALS WITH DEDUP
# Fire only on the FIRST bar a signal becomes true
# Prevents repeated signals while condition stays active
# ═══════════════════════════════════════════════════════════════
def compute_signals(df):
    bo_buy   = df['bo_buy'].values
    bo_sell  = df['bo_sell'].values
    rev_buy  = df['rev_buy'].values
    rev_sell = df['rev_sell'].values
    n = len(df)

    raw_buy  = bo_buy  | rev_buy
    raw_sell = bo_sell | rev_sell

    buy_signal  = np.zeros(n, dtype=bool)
    sell_signal = np.zeros(n, dtype=bool)

    for i in range(1, n):
        # Rising edge: true now, false on previous bar
        buy_signal[i]  = raw_buy[i]  and not raw_buy[i-1]
        sell_signal[i] = raw_sell[i] and not raw_sell[i-1]

    df['buy_signal']  = buy_signal
    df['sell_signal'] = sell_signal

    print(f"Final signals: BUY: {buy_signal.sum()} | SELL: {sell_signal.sum()} | "
          f"Total: {buy_signal.sum() + sell_signal.sum()}")
    return df

# ═══════════════════════════════════════════════════════════════
# STEP 8: PRINT SIGNAL TABLE
# ═══════════════════════════════════════════════════════════════
def print_signals(df):
    signals = []

    for i, row in df.iterrows():
        if row['buy_signal'] or row['sell_signal']:
            is_buy = row['buy_signal']

            if is_buy:
                sig_parts = []
                if row['bo_buy']:  sig_parts.append('BO-BUY')
                if row['rev_buy']: sig_parts.append('REV-BUY')
                label = 'BUY  (' + '/'.join(sig_parts) + ')'
            else:
                sig_parts = []
                if row['bo_sell']:  sig_parts.append('BO-SELL')
                if row['rev_sell']: sig_parts.append('REV-SELL')
                label = 'SELL (' + '/'.join(sig_parts) + ')'

            lsh_val = row['last_swing_high']
            lsl_val = row['last_swing_low']

            signals.append({
                'date'   : row['datetime'].strftime('%Y-%m-%d %H:%M'),
                'signal' : label,
                'close'  : row['close'],
                'renko_c': round(row['renko_close'], 1),
                'r_dir'  : row['renko_dir'],
                'st_bull': row['st_bull'],
                'last_sh': round(lsh_val, 1) if not np.isnan(lsh_val) else 'nan',
                'last_sl': round(lsl_val, 1) if not np.isnan(lsl_val) else 'nan',
            })

    print("\n" + "=" * 100)
    print(f"{'DATE':<18} {'SIGNAL':<26} {'CLOSE':>10} {'RENKO_C':>10} "
          f"{'R_DIR':>6} {'ST_BULL':>8} {'LAST_SH':>10} {'LAST_SL':>10}")
    print("=" * 100)

    for s in signals:
        print(f"{s['date']:<18} {s['signal']:<26} {s['close']:>10.1f} "
              f"{s['renko_c']:>10.1f} {s['r_dir']:>6} "
              f"{str(s['st_bull']):>8} {str(s['last_sh']):>10} {str(s['last_sl']):>10}")

    print("=" * 100)
    buy_count  = sum(1 for s in signals if 'BUY'  in s['signal'])
    sell_count = sum(1 for s in signals if 'SELL' in s['signal'])
    print(f"Total: {len(signals)} | BUY: {buy_count} | SELL: {sell_count}")

    return signals

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 100)
    print("RENKO SIGNAL VALIDATOR - 2h Data")
    print(f"Settings: box={RENKO_BOX}, ST({ST_ATR_LEN},{ST_FACTOR}), "
          f"Swing({SWING_LEFT}/{SWING_RIGHT}), SR_tol={SR_TOLERANCE}%")
    print("=" * 100)

    df = load_data(CSV_PATH)
    df = simulate_renko(df, box_size=RENKO_BOX)
    df = compute_supertrend(df, atr_len=ST_ATR_LEN, factor=ST_FACTOR)
    df = compute_swings(df, left=SWING_LEFT, right=SWING_RIGHT)
    df = compute_trendline_breakout(df)
    df = compute_sr_reversal(df, tolerance_pct=SR_TOLERANCE)
    df = compute_signals(df)

    signals = print_signals(df)

    # Save full debug CSV for visual inspection
    debug_cols = [
        'datetime', 'close', 'high', 'low',
        'renko_open', 'renko_close', 'renko_dir',
        'renko_bull', 'renko_bear',
        'st_bull', 'st_bear', 'st_line',
        'swing_high', 'swing_low',
        'last_swing_high', 'last_swing_low',
        'bo_buy', 'bo_sell', 'rev_buy', 'rev_sell',
        'buy_signal', 'sell_signal'
    ]
    df[debug_cols].to_csv("output/renko_signal_debug.csv", index=False)
    print("\nDebug CSV saved: output/renko_signal_debug.csv")
    print("Open CSV and verify renko_close is stepping by 200 with each direction change")
