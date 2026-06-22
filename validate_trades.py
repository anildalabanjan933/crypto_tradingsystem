# validate_trades.py
# Full validation script: Renko builder → Supertrend → Swing detector →
# Trendline projector → Signal generator → Trade builder → Validation engine

# =============================================================================
# Section 1: Imports and Configuration
# =============================================================================
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import warnings
warnings.filterwarnings('ignore')

# --- File Paths ---
OHLCV_FILE      = 'data/btc_2h_delta.csv'
REFERENCE_FILE  = 'output/renko_mode1_btcusd_trades.csv'
OUTPUT_FILE     = 'validation_output.csv'
SCRIPT_TRADES   = 'script_trades.csv'

# --- Renko Settings ---
RENKO_BOX       = 200
ANCHOR_OFFSET   = 173          # derived from reference prices: 42773 % 200 = 173

# --- Supertrend Settings ---
ST_ATR_LEN      = 5
ST_FACTOR       = 4.0

# --- Swing Detection ---
SWING_L         = 2
SWING_R         = 2

# --- Trade Settings ---
POSITION_SIZE   = 100          # lots
SLIPPAGE        = 3.0          # $ per side (6 total, matches reference CSV)
COMMISSION_PCT  = 0.0005       # 0.05% taker
CONTRACT_VALUE  = 0.001        # 1 lot = 0.001 BTC (Delta Exchange BTCUSD)

# --- Validation Tolerance ---
SR_TOLERANCE    = 1.0


# =============================================================================
# Section 2: Load and Prepare OHLCV Data + Build Renko Boxes
# =============================================================================
def load_ohlcv(path):
    df = pd.read_csv(path)
    df['datetime'] = pd.to_datetime(df['datetime'], utc=True)
    df = df.sort_values('datetime').reset_index(drop=True)
    # Start from Jan 10 2024 to give Renko builder warmup bars
    df = df[df['datetime'] >= pd.Timestamp('2024-01-10', tz='UTC')].reset_index(drop=True)
    return df


def build_renko(df, box_size, anchor_offset):
    """
    Build Traditional Renko boxes from 2H OHLCV.
    Anchor is seeded from first candle close with the 173-offset grid.
    Each box records the 2H bar index (candle_idx) at which it closed.
    """
    first_close  = df['close'].iloc[0]
    anchor       = (round(first_close / box_size) * box_size) + anchor_offset

    boxes        = []
    current_open = anchor
    direction    = None  # 'up' or 'down'

    for i, row in df.iterrows():
        high  = row['high']
        low   = row['low']
        close = row['close']
        dt    = row['datetime']

        if direction is None:
            if close >= current_open + box_size:
                direction    = 'up'
                box_close_px = current_open + box_size
                boxes.append({'open': current_open, 'close': box_close_px,
                               'direction': direction, 'candle_idx': i, 'datetime': dt})
                current_open = box_close_px
            elif close <= current_open - box_size:
                direction    = 'down'
                box_close_px = current_open - box_size
                boxes.append({'open': current_open, 'close': box_close_px,
                               'direction': direction, 'candle_idx': i, 'datetime': dt})
                current_open = box_close_px
            continue

        while True:
            if direction == 'up':
                if close >= current_open + box_size:
                    box_close_px = current_open + box_size
                    boxes.append({'open': current_open, 'close': box_close_px,
                                  'direction': 'up', 'candle_idx': i, 'datetime': dt})
                    current_open = box_close_px
                elif close <= current_open - box_size:
                    direction    = 'down'
                    box_close_px = current_open - box_size
                    boxes.append({'open': current_open, 'close': box_close_px,
                                  'direction': 'down', 'candle_idx': i, 'datetime': dt})
                    current_open = box_close_px
                else:
                    break
            else:  # direction == 'down'
                if close <= current_open - box_size:
                    box_close_px = current_open - box_size
                    boxes.append({'open': current_open, 'close': box_close_px,
                                  'direction': 'down', 'candle_idx': i, 'datetime': dt})
                    current_open = box_close_px
                elif close >= current_open + box_size:
                    direction    = 'up'
                    box_close_px = current_open + box_size
                    boxes.append({'open': current_open, 'close': box_close_px,
                                  'direction': 'up', 'candle_idx': i, 'datetime': dt})
                    current_open = box_close_px
                else:
                    break

    renko_df = pd.DataFrame(boxes)
    return renko_df


# =============================================================================
# Section 3: Supertrend Calculation (Wilder RMA, ATR=5, Factor=4)
# =============================================================================
def wilder_rma(series, length):
    rma = np.zeros(len(series))
    rma[:] = np.nan
    first_valid = series.first_valid_index()
    if first_valid is None:
        return pd.Series(rma, index=series.index)
    start = series.index.get_loc(first_valid)
    if start + length > len(series):
        return pd.Series(rma, index=series.index)
    rma[start + length - 1] = series.iloc[start:start + length].mean()
    alpha = 1.0 / length
    for j in range(start + length, len(series)):
        rma[j] = alpha * series.iloc[j] + (1 - alpha) * rma[j - 1]
    return pd.Series(rma, index=series.index)


def compute_supertrend(renko_df, atr_len, factor):
    """
    Compute Supertrend on Renko boxes.
    High = max(open, close), Low = min(open, close) for ATR purposes.
    """
    df = renko_df.copy()
    df['high_r'] = df[['open', 'close']].max(axis=1)
    df['low_r']  = df[['open', 'close']].min(axis=1)

    prev_close = df['close'].shift(1)
    tr         = pd.concat([
        df['high_r'] - df['low_r'],
        (df['high_r'] - prev_close).abs(),
        (df['low_r']  - prev_close).abs()
    ], axis=1).max(axis=1)

    atr = wilder_rma(tr, atr_len)

    hl2     = (df['high_r'] + df['low_r']) / 2
    upper_b = hl2 + factor * atr
    lower_b = hl2 - factor * atr

    upper = upper_b.copy()
    lower = lower_b.copy()
    trend = pd.Series(np.nan, index=df.index)

    for i in range(1, len(df)):
        if upper_b.iloc[i] < upper.iloc[i - 1] or df['close'].iloc[i - 1] > upper.iloc[i - 1]:
            upper.iloc[i] = upper_b.iloc[i]
        else:
            upper.iloc[i] = upper.iloc[i - 1]

        if lower_b.iloc[i] > lower.iloc[i - 1] or df['close'].iloc[i - 1] < lower.iloc[i - 1]:
            lower.iloc[i] = lower_b.iloc[i]
        else:
            lower.iloc[i] = lower.iloc[i - 1]

        prev_trend = trend.iloc[i - 1]
        if np.isnan(prev_trend):
            trend.iloc[i] = 1 if df['close'].iloc[i] > upper.iloc[i] else -1
        elif prev_trend == -1 and df['close'].iloc[i] > upper.iloc[i]:
            trend.iloc[i] = 1
        elif prev_trend == 1 and df['close'].iloc[i] < lower.iloc[i]:
            trend.iloc[i] = -1
        else:
            trend.iloc[i] = prev_trend

    df['st_upper'] = upper
    df['st_lower'] = lower
    df['st_trend'] = trend   # 1 = green (bullish), -1 = red (bearish)
    return df


# =============================================================================
# Section 4: Swing High / Swing Low Detection (L=2, R=2, strict pivot)
# =============================================================================
def detect_swings(renko_df):
    """
    Strict pivot: a swing high at index i requires
      close[i-2] < close[i-1] < close[i] > close[i+1] > close[i+2]
    Similarly for swing low.
    """
    closes      = renko_df['close'].values
    n           = len(closes)
    swing_highs = np.full(n, np.nan)
    swing_lows  = np.full(n, np.nan)

    for i in range(SWING_L, n - SWING_R):
        is_sh = all(closes[i] > closes[i - k] for k in range(1, SWING_L + 1)) and \
                all(closes[i] > closes[i + k] for k in range(1, SWING_R + 1))
        if is_sh:
            swing_highs[i] = closes[i]

        is_sl = all(closes[i] < closes[i - k] for k in range(1, SWING_L + 1)) and \
                all(closes[i] < closes[i + k] for k in range(1, SWING_R + 1))
        if is_sl:
            swing_lows[i] = closes[i]

    renko_df = renko_df.copy()
    renko_df['swing_high'] = swing_highs
    renko_df['swing_low']  = swing_lows
    return renko_df


# =============================================================================
# Section 5: Trendline Break Detection
# =============================================================================
def detect_trendline_breaks(renko_df):
    """
    BUY_A  : price breaks above a descending resistance trendline (swing highs)
    BUY_B  : price breaks above a prior swing high (horizontal, min 30 boxes old)
    SELL_A : price breaks below an ascending support trendline (swing lows)
    SELL_B : price breaks below a prior swing low (horizontal, min 30 boxes old)

    Signal fires on the box close that first crosses the trendline/level.
    Rising-edge deduplication: signal is True only on the transition bar.
    Trendline recency limit: anchor swing must be within 50 boxes.
    Horizontal level age: swing high/low must be at least 30 boxes old.
    Horizontal cooldown: no repeat B-type signal within 20 boxes.
    Level consumed: after BUY_B/SELL_B fires, level resets (no re-fire).
    """
    closes      = renko_df['close'].values
    swing_highs = renko_df['swing_high'].values
    swing_lows  = renko_df['swing_low'].values
    n           = len(closes)

    raw_buy_a  = np.zeros(n, dtype=bool)
    raw_buy_b  = np.zeros(n, dtype=bool)
    raw_sell_a = np.zeros(n, dtype=bool)
    raw_sell_b = np.zeros(n, dtype=bool)

    buy_a  = np.zeros(n, dtype=bool)
    buy_b  = np.zeros(n, dtype=bool)
    sell_a = np.zeros(n, dtype=bool)
    sell_b = np.zeros(n, dtype=bool)

    last_sh       = np.nan
    last_sl       = np.nan
    sh_history    = []
    sl_history    = []
    last_buy_b_i  = -999   # cooldown tracker for BUY_B
    last_sell_b_i = -999   # cooldown tracker for SELL_B

    for i in range(n):
        if not np.isnan(swing_highs[i]):
            sh_history.append((i, swing_highs[i]))
            last_sh = swing_highs[i]
        if not np.isnan(swing_lows[i]):
            sl_history.append((i, swing_lows[i]))
            last_sl = swing_lows[i]

        # --- BUY_B: break above last swing high (horizontal) ---
        # Conditions:
        #   1. swing high must be at least 30 boxes old
        #   2. no BUY_B signal fired within last 20 boxes (cooldown)
        #   3. price must close above the level
        if not np.isnan(last_sh) and closes[i] > last_sh:
            sh_age = i - sh_history[-1][0] if sh_history else 0
            cooldown_ok = (i - last_buy_b_i) >= 20
            if sh_age >= 30 and cooldown_ok:
                raw_buy_b[i] = True
                last_buy_b_i = i
                last_sh = np.nan   # consume level so it cannot fire again

        # --- SELL_B: break below last swing low (horizontal) ---
        # Conditions:
        #   1. swing low must be at least 30 boxes old
        #   2. no SELL_B signal fired within last 20 boxes (cooldown)
        #   3. price must close below the level
        if not np.isnan(last_sl) and closes[i] < last_sl:
            sl_age = i - sl_history[-1][0] if sl_history else 0
            cooldown_ok = (i - last_sell_b_i) >= 20
            if sl_age >= 30 and cooldown_ok:
                raw_sell_b[i] = True
                last_sell_b_i = i
                last_sl = np.nan   # consume level so it cannot fire again

        # --- BUY_A: break above descending trendline ---
        # Anchor swing high must be within 50 boxes
        if len(sh_history) >= 2:
            idx1, px1 = sh_history[-2]
            idx2, px2 = sh_history[-1]
            if idx2 > idx1 and px2 < px1 and (i - idx1) <= 50:
                span       = idx2 - idx1
                slope      = (px2 - px1) / span
                tl_val_now = px1 + slope * (i - idx1)
                if closes[i] > tl_val_now:
                    raw_buy_a[i] = True

        # --- SELL_A: break below ascending trendline ---
        # Anchor swing low must be within 50 boxes
        if len(sl_history) >= 2:
            idx1, px1 = sl_history[-2]
            idx2, px2 = sl_history[-1]
            if idx2 > idx1 and px2 > px1 and (i - idx1) <= 50:
                span       = idx2 - idx1
                slope      = (px2 - px1) / span
                tl_val_now = px1 + slope * (i - idx1)
                if closes[i] < tl_val_now:
                    raw_sell_a[i] = True

    # --- Rising-edge deduplication ---
    # Signal is True only on the bar where it transitions False -> True
    for i in range(1, n):
        buy_a[i]  = raw_buy_a[i]  and not raw_buy_a[i-1]
        buy_b[i]  = raw_buy_b[i]  and not raw_buy_b[i-1]
        sell_a[i] = raw_sell_a[i] and not raw_sell_a[i-1]
        sell_b[i] = raw_sell_b[i] and not raw_sell_b[i-1]

    renko_df['buy_a']  = buy_a
    renko_df['buy_b']  = buy_b
    renko_df['sell_a'] = sell_a
    renko_df['sell_b'] = sell_b

    return renko_df



# =============================================================================
# Section 6: Trade Builder
# =============================================================================
def build_trades(renko_df):
    """
    Entry : first Renko box close after trendline break signal
    Exit  : first Renko box close where Supertrend flips
            OR opposite signal (closes current + opens new immediately)
    """
    trades   = []
    position = None
    n        = len(renko_df)

    for i in range(1, n):
        row        = renko_df.iloc[i]
        prev_trend = renko_df['st_trend'].iloc[i - 1]
        curr_trend = renko_df['st_trend'].iloc[i]
        st_flipped = (
            (prev_trend != curr_trend)
            and not np.isnan(prev_trend)
            and not np.isnan(curr_trend)
        )

        entry_px = row['close']
        entry_dt = row['datetime']

        # --- Check exit for open position ---
        if position is not None:
            exit_triggered = False
            exit_reason    = ''

            if st_flipped:
                if position['direction'] == 'LONG' and curr_trend == -1:
                    exit_triggered = True
                    exit_reason    = 'ST_FLIP_RED'
                elif position['direction'] == 'SHORT' and curr_trend == 1:
                    exit_triggered = True
                    exit_reason    = 'ST_FLIP_GREEN'

            if not exit_triggered:
                if position['direction'] == 'LONG' and (row['sell_a'] or row['sell_b']):
                    exit_triggered = True
                    exit_reason    = 'OPP_SIGNAL'
                elif position['direction'] == 'SHORT' and (row['buy_a'] or row['buy_b']):
                    exit_triggered = True
                    exit_reason    = 'OPP_SIGNAL'

            if exit_triggered:
                exit_px = row['close']
                exit_dt = row['datetime']
                pnl     = _calc_pnl(position['direction'], position['entry_px'],
                                    exit_px, POSITION_SIZE)
                trades.append({
                    'direction' : position['direction'],
                    'entry_type': position['entry_type'],
                    'exit_type' : exit_reason,
                    'entry_dt'  : position['entry_dt'],
                    'entry_px'  : position['entry_px'],
                    'exit_dt'   : exit_dt,
                    'exit_px'   : exit_px,
                    'pnl'       : pnl
                })
                position = None

                if exit_reason == 'OPP_SIGNAL':
                    if row['sell_a'] or row['sell_b']:
                        sig_type = 'SELL_A' if row['sell_a'] else 'SELL_B'
                        position = {'direction': 'SHORT', 'entry_type': sig_type,
                                    'entry_px': entry_px, 'entry_dt': entry_dt}
                    elif row['buy_a'] or row['buy_b']:
                        sig_type = 'BUY_A' if row['buy_a'] else 'BUY_B'
                        position = {'direction': 'LONG', 'entry_type': sig_type,
                                    'entry_px': entry_px, 'entry_dt': entry_dt}
                continue

        # --- Check entry if no open position ---
        if position is None:
            if row['buy_a'] or row['buy_b']:
                sig_type = 'BUY_A' if row['buy_a'] else 'BUY_B'
                position = {'direction': 'LONG', 'entry_type': sig_type,
                            'entry_px': entry_px, 'entry_dt': entry_dt}
            elif row['sell_a'] or row['sell_b']:
                sig_type = 'SELL_A' if row['sell_a'] else 'SELL_B'
                position = {'direction': 'SHORT', 'entry_type': sig_type,
                            'entry_px': entry_px, 'entry_dt': entry_dt}

    return pd.DataFrame(trades)


def _calc_pnl(direction, entry_px, exit_px, size):
    """
    Calculate net PnL for a trade.

    Formula:
        raw PnL    = price_move * CONTRACT_VALUE * size
        slippage   = $3 per side * 2 sides = $6 flat total (NOT per lot)
        commission = 0.05% * notional on entry + 0.05% * notional on exit

    Example (LONG, entry=42000, exit=43000, size=100 lots):
        raw      = (43000 - 42000) * 0.001 * 100 = $100
        slippage = $6 flat
        comm     = 42000*0.001*0.0005*100 + 43000*0.001*0.0005*100 = $2.10 + $2.15 = $4.25
        net      = $100 - $6 - $4.25 = $89.75
    """
    slip_total = SLIPPAGE * 2                                         # $6 flat total (NOT per lot)
    comm_entry = entry_px * CONTRACT_VALUE * COMMISSION_PCT * size    # 0.05% on entry notional
    comm_exit  = exit_px  * CONTRACT_VALUE * COMMISSION_PCT * size    # 0.05% on exit notional
    if direction == 'LONG':
        raw = (exit_px - entry_px) * CONTRACT_VALUE * size
    else:
        raw = (entry_px - exit_px) * CONTRACT_VALUE * size
    return raw - slip_total - comm_entry - comm_exit

# =============================================================================
# Section 7: Load Reference Trades
# =============================================================================
def load_reference(path):
    df = pd.read_csv(path)
    df['entry_datetime'] = pd.to_datetime(df['entry_datetime'], utc=True)
    df['exit_datetime']  = pd.to_datetime(df['exit_datetime'],  utc=True)
    return df


# =============================================================================
# Section 8: Validation Engine
# =============================================================================
def validate(ref_df, script_df, renko_df):
    """
    For each reference trade, find the closest script trade by entry datetime
    (filtered to same direction) and apply validation rules.

    Verdict:
      VALID    - all checks pass
      INVALID  - a rule is clearly violated
      DOUBTFUL - rule cannot be verified at 2H resolution
    """
    results = []

    for _, ref in ref_df.iterrows():
        ref_entry_dt = ref['entry_datetime']
        ref_exit_dt  = ref['exit_datetime']
        ref_entry_px = float(ref['entry_price'])
        ref_exit_px  = float(ref['exit_price'])
        ref_dir      = ref['direction']     # LONG / SHORT
        ref_sig      = ref['entry_type']    # BUY_A / BUY_B / SELL_A / SELL_B

        verdict = 'DOUBTFUL'
        reason  = []

        # --- Rule 1: Entry price must be on the 173-offset Renko grid ---
        entry_on_box = abs((ref_entry_px - ANCHOR_OFFSET) % RENKO_BOX) < 1
        if not entry_on_box:
            reason.append(f'Entry {ref_entry_px} not on 173-offset grid')
            verdict = 'INVALID'

        # --- Rule 2: Match to nearest script trade (same direction first) ---
        if not script_df.empty:
            same_dir = script_df[script_df['direction'] == ref_dir]
            if same_dir.empty:
                same_dir = script_df   # fallback to all if no direction match
            time_diffs = (same_dir['entry_dt'] - ref_entry_dt).abs()
            best_idx   = time_diffs.idxmin()
            best_match = same_dir.loc[best_idx]
            dt_gap_hrs = time_diffs[best_idx].total_seconds() / 3600

            if dt_gap_hrs > 48:
                reason.append(f'No script trade within 48h (gap={dt_gap_hrs:.1f}h)')
                verdict = 'INVALID'
            else:
                # Direction match
                if best_match['direction'] != ref_dir:
                    reason.append(
                        f"Direction mismatch: script={best_match['direction']} ref={ref_dir}"
                    )
                    verdict = 'INVALID'

                # Signal type match
                if best_match['entry_type'] != ref_sig:
                    reason.append(
                        f"Signal mismatch: script={best_match['entry_type']} ref={ref_sig}"
                    )
                    if verdict != 'INVALID':
                        verdict = 'DOUBTFUL'

                # Entry price proximity
                # Within 1 box = VALID, within 3 boxes = DOUBTFUL, beyond = INVALID
                px_gap = abs(best_match['entry_px'] - ref_entry_px)
                if px_gap > RENKO_BOX * 3:
                    reason.append(f'Entry price gap {px_gap:.0f} > 3 boxes')
                    verdict = 'INVALID'
                elif px_gap > RENKO_BOX:
                    reason.append(f'Entry price gap {px_gap:.0f} > 1 box (timing offset)')
                    if verdict != 'INVALID':
                        verdict = 'DOUBTFUL'

        # --- Rule 3: Exit type check ---
        ref_exit_type = ref['exit_type']
        if ref_exit_type not in ('ST_FLIP_GREEN', 'ST_FLIP_RED'):
            reason.append(f'Unexpected exit type: {ref_exit_type}')
            if verdict != 'INVALID':
                verdict = 'DOUBTFUL'

        # --- Final verdict ---
        if not reason:
            verdict = 'VALID'

        results.append({
            'trade_number': ref['trade_number'],
            'direction'   : ref_dir,
            'entry_type'  : ref_sig,
            'entry_dt'    : ref_entry_dt,
            'entry_px'    : ref_entry_px,
            'exit_dt'     : ref_exit_dt,
            'exit_px'     : ref_exit_px,
            'verdict'     : verdict,
            'reason'      : '; '.join(reason) if reason else 'All checks passed'
        })

    return pd.DataFrame(results)


# =============================================================================
# Section 9: Performance Report
# =============================================================================
def print_report(script_df, val_df):
    print('\n' + '=' * 60)
    print('BACKTEST VALIDATION REPORT')
    print('=' * 60)

    if not script_df.empty:
        total   = len(script_df)
        wins    = (script_df['pnl'] > 0).sum()
        losses  = (script_df['pnl'] <= 0).sum()
        win_pct = wins / total * 100 if total else 0
        gross_p = script_df[script_df['pnl'] > 0]['pnl'].sum()
        gross_l = script_df[script_df['pnl'] <= 0]['pnl'].abs().sum()
        pf      = gross_p / gross_l if gross_l else float('inf')
        net_pnl = script_df['pnl'].sum()

        print(f'Script Trades  : {total}')
        print(f'Win Rate       : {win_pct:.2f}%')
        print(f'Profit Factor  : {pf:.2f}')
        print(f'Net PnL        : ${net_pnl:,.2f}')
        print(f'Gross Profit   : ${gross_p:,.2f}')
        print(f'Gross Loss     : ${gross_l:,.2f}')

    print('\n--- Validation Summary ---')
    if not val_df.empty:
        counts = val_df['verdict'].value_counts()
        for v in ['VALID', 'DOUBTFUL', 'INVALID']:
            print(f'  {v:10s}: {counts.get(v, 0)}')

    print('=' * 60 + '\n')


# =============================================================================
# Section 10: Main Entry Point
# =============================================================================
def main():
    print('Loading OHLCV data...')
    ohlcv_df = load_ohlcv(OHLCV_FILE)
    print(f'  Loaded {len(ohlcv_df)} bars from '
          f'{ohlcv_df["datetime"].iloc[0]} to {ohlcv_df["datetime"].iloc[-1]}')

    print('Building Renko boxes...')
    renko_df = build_renko(ohlcv_df, RENKO_BOX, ANCHOR_OFFSET)
    print(f'  Built {len(renko_df)} Renko boxes')

    print('Computing Supertrend...')
    renko_df = compute_supertrend(renko_df, ST_ATR_LEN, ST_FACTOR)

    print('Detecting swings...')
    renko_df = detect_swings(renko_df)

    print('Detecting trendline breaks...')
    renko_df = detect_trendline_breaks(renko_df)

    buy_a_count  = renko_df['buy_a'].sum()
    buy_b_count  = renko_df['buy_b'].sum()
    sell_a_count = renko_df['sell_a'].sum()
    sell_b_count = renko_df['sell_b'].sum()
    print(f'  Signals -> BUY_A:{buy_a_count}  BUY_B:{buy_b_count}  '
          f'SELL_A:{sell_a_count}  SELL_B:{sell_b_count}')

    print('Building script trades...')
    script_df = build_trades(renko_df)
    print(f'  Generated {len(script_df)} trades')
    script_df.to_csv(SCRIPT_TRADES, index=False)
    print(f'  Saved to {SCRIPT_TRADES}')

    print('Loading reference trades...')
    ref_df = load_reference(REFERENCE_FILE)
    print(f'  Loaded {len(ref_df)} reference trades')

    print('Running validation...')
    val_df = validate(ref_df, script_df, renko_df)
    val_df.to_csv(OUTPUT_FILE, index=False)
    print(f'  Saved to {OUTPUT_FILE}')

    print_report(script_df, val_df)

    # =========================================================================
    # DIAGNOSTIC BLOCK
    # =========================================================================
    invalid = val_df[val_df['verdict'] == 'INVALID']
    print(f"\nTotal INVALID: {len(invalid)}")

    print("\nReason breakdown:")
    print(invalid['reason'].value_counts().to_string())

    print("\nFirst 10 INVALID trades:")
    print(invalid[['trade_number', 'entry_px', 'verdict', 'reason']].head(10).to_string())

    print("\nScript trades entry_type distribution:")
    print(script_df['entry_type'].value_counts().to_string())

    print("\nReference trades entry_type distribution:")
    ref_check = pd.read_csv(REFERENCE_FILE)
    print(ref_check['entry_type'].value_counts().to_string())

    print("\nScript trades direction distribution:")
    print(script_df['direction'].value_counts().to_string())

    print("\nReference trades direction distribution:")
    print(ref_check['direction'].value_counts().to_string())

    print("\nScript trade count by month:")
    script_df['entry_dt'] = pd.to_datetime(script_df['entry_dt'], utc=True)
    print(script_df.groupby(script_df['entry_dt'].dt.to_period('M')).size().to_string())

    print("\nReference trade count by month:")
    ref_check['entry_datetime'] = pd.to_datetime(ref_check['entry_datetime'], utc=True)
    print(ref_check.groupby(ref_check['entry_datetime'].dt.to_period('M')).size().to_string())
    # =========================================================================
    # END DIAGNOSTIC BLOCK
    # =========================================================================


if __name__ == '__main__':
    main()
