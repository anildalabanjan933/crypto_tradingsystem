# strategies/renko_pattern_breakout_strategy.py
# Strategy: Renko Pattern Breakout
# Entry : Pattern breakout (Renko close only)
# Exit  : Supertrend flip (same brick)
# Max positions: 2 (any combination BB/SS/BS/SB)

import numpy as np
import pandas as pd
from scipy import stats
from strategies.backtest.base_strategy import BaseStrategy
from indicators.renko import RenkoBuilder, SupertrendIndicator
from config.symbol_config import get_renko_box_size


class RenkoPatternBreakoutStrategy(BaseStrategy):

    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        super().__init__(data_dict=data_dict, lot_size=lot_size)

        symbol        = kwargs.get('symbol', 'BTCUSD')
        current_price = kwargs.get('current_price', None)
        self.renko_box            = kwargs.get('renko_box') or get_renko_box_size(symbol, current_price)
        self.lookback_min         = int(kwargs.get('lookback_min', 6))
        self.lookback_max         = int(kwargs.get('lookback_max', 12))
        self.slope_flat_threshold = float(kwargs.get('slope_flat_threshold', 0.1))
        self.st_multiplier        = float(kwargs.get('st_multiplier', 2.0))
        self.st_period            = int(kwargs.get('st_period', 5))

    @property
    def required_timeframes(self):
        return ['2h']

    @property
    def optimization_params(self):
        return {
            'renko_box':            {'default': 200, 'min': 100, 'max': 500, 'step': 50},
            'lookback_min':         {'min': 6,  'max': 10,  'step': 1},
            'lookback_max':         {'min': 8,  'max': 12,  'step': 1},
            'slope_flat_threshold': {'min': 0.05, 'max': 0.2, 'step': 0.05},
        }

    # -----------------------------------------------------------------------
    # Renko DataFrame builder  (same pattern as RenkoSMIIOSupertrend v1.30)
    # -----------------------------------------------------------------------
    def _build_renko_df(self) -> pd.DataFrame:
        df_2h = self._data.get('2h')
        if df_2h is None or len(df_2h) == 0:
            raise ValueError("Requires '2h' timeframe data")

        closes     = df_2h['close'].values
        timestamps = (df_2h.index if isinstance(df_2h.index, pd.DatetimeIndex)
                      else pd.to_datetime(df_2h['timestamp']))

        builder   = RenkoBuilder(box_size=self.renko_box)
        renko_raw = builder.build(closes)
        if renko_raw is None or len(renko_raw) == 0:
            raise ValueError("RenkoBuilder produced no bricks")

        renko_raw['timestamp'] = renko_raw['bar_index'].apply(
            lambda idx: timestamps[idx] if idx < len(timestamps) else timestamps[-1]
        )
        return renko_raw

    # -----------------------------------------------------------------------
    # Pattern detection  (unchanged logic)
    # -----------------------------------------------------------------------
    def _detect_pattern(self, closes, box_size):
        flat_th  = self.slope_flat_threshold
        n_closes = len(closes)

        for window in range(min(self.lookback_min, n_closes), min(self.lookback_max, n_closes) + 1):
            if n_closes < window:
                continue

            segment = closes[-window:]

            up_prices, dn_prices = [], []
            up_indices, dn_indices = [], []
            for j in range(1, len(segment)):
                if segment[j] > segment[j - 1]:
                    up_prices.append(float(segment[j]))
                    up_indices.append(j)
                elif segment[j] < segment[j - 1]:
                    dn_prices.append(float(segment[j]))
                    dn_indices.append(j)

            if len(up_prices) < 1 or len(dn_prices) < 1:
                continue
            if len(up_prices) < 2 and len(dn_prices) < 2:
                continue

            x_up = np.array(up_indices, dtype=float)
            x_dn = np.array(dn_indices, dtype=float)
            y_up = np.array(up_prices)
            y_dn = np.array(dn_prices)

            if len(x_up) >= 2:
                slope_up, intercept_up, r_up, _, _ = stats.linregress(x_up, y_up)
                r2_up = r_up ** 2
            else:
                slope_up     = 0.0
                intercept_up = float(y_up[0])
                r2_up        = 1.0

            if len(x_dn) >= 2:
                slope_dn, intercept_dn, r_dn, _, _ = stats.linregress(x_dn, y_dn)
                r2_dn = r_dn ** 2
            else:
                slope_dn     = 0.0
                intercept_dn = float(y_dn[0])
                r2_dn        = 1.0

            norm_up = slope_up / box_size
            norm_dn = slope_dn / box_size

            if norm_dn > flat_th and norm_up < -flat_th:
                continue

            lower_flat_or_rising  = norm_up >= -flat_th
            upper_flat_or_falling = norm_dn <= flat_th
            lower_rising          = norm_up > flat_th
            upper_falling         = norm_dn < -flat_th

            if not (lower_flat_or_rising and upper_flat_or_falling):
                continue

            if lower_rising and upper_flat_or_falling:
                ptype = 'bull'
            elif upper_falling and lower_flat_or_rising:
                ptype = 'bear'
            elif (abs(norm_up) <= flat_th) and (abs(norm_dn) <= flat_th):
                ptype = 'symmetric'
            else:
                continue

            if ptype == 'bear' and len(dn_prices) >= 2:
                mid = len(dn_prices) // 2
                if float(np.mean(dn_prices[mid:])) >= float(np.mean(dn_prices[:max(1, mid)])):
                    continue
            if ptype == 'bull' and len(up_prices) >= 2:
                mid = len(up_prices) // 2
                if float(np.mean(up_prices[mid:])) <= float(np.mean(up_prices[:max(1, mid)])):
                    continue

            if ptype == 'bull':
                if len(x_up) >= 2 and r2_up < 0.80:
                    continue
                if len(x_dn) >= 2 and r2_dn < 0.65:
                    continue
            elif ptype == 'bear':
                if len(x_dn) >= 2 and r2_dn < 0.80:
                    continue
                if len(x_up) >= 2 and r2_up < 0.65:
                    continue
            else:
                if len(x_up) >= 2 and r2_up < 0.70:
                    continue
                if len(x_dn) >= 2 and r2_dn < 0.70:
                    continue

            if ptype == 'bear' and len(x_dn) >= 2:
                x_start_dn = float(min(dn_indices))
                x_end_dn   = float(max(dn_indices))
                if (slope_dn * x_end_dn + intercept_dn) >= (slope_dn * x_start_dn + intercept_dn):
                    continue

            x_current  = float(window + 1)
            bull_level = slope_dn * x_current + intercept_dn
            bear_level = slope_up * x_current + intercept_up

            x_start = float(min(
                min(up_indices) if up_indices else window,
                min(dn_indices) if dn_indices else window,
            ))
            width_start = abs(
                (slope_dn * x_start + intercept_dn) - (slope_up * x_start + intercept_up)
            )
            width_end = abs(bull_level - bear_level)
            if width_end > width_start * 1.05:
                continue

            price_range = float(np.max(segment) - np.min(segment))
            if price_range < 2.0 * box_size:
                continue

            return (ptype, bull_level, bear_level)

        return None

    # -----------------------------------------------------------------------
    # generate_signals  — MAIN LOGIC
    # -----------------------------------------------------------------------
    def generate_signals(self):
        df = self._build_renko_df()
        if df is None or len(df) == 0:
            return []

        timestamps = df['timestamp'].tolist()
        closes     = df['renko_close'].values.astype(float)
        renko_dir  = df['renko_dir'].values
        n          = len(df)
        box_size   = self.renko_box

        # --- SupertrendIndicator (same as RenkoReversal + RenkoSMIIOSupertrend) ---
        # st_dir: -1 = GREEN (bullish), +1 = RED (bearish)
        st_ind = SupertrendIndicator(
            atr_period=self.st_period,
            factor=self.st_multiplier,
        )
        df_st  = st_ind.calculate(df)
        st_dir = df_st['st_dir'].values

        # --- Initialise state ---
        trades               = []
        open_positions       = []
        cooldown_hours       = 2
        entry_allowed_long   = pd.Timestamp.min
        entry_allowed_short  = pd.Timestamp.min

        # --- Main signal loop ---
        for i in range(n):
            c     = closes[i]
            ts_pd = pd.Timestamp(timestamps[i])
            st    = st_dir[i]

            # ----------------------------------------------------------
            # EXIT: ST flip — same brick (no wait), individual per position
            # ----------------------------------------------------------
            still_open = []
            for pos in open_positions:
                bars_held       = i - pos['entry_bar']
                exit_triggered  = False

                if bars_held < 4:
                    still_open.append(pos)
                    continue

                if pos['direction'] == 'long'  and st == 1:
                    exit_triggered = True
                elif pos['direction'] == 'short' and st == -1:
                    exit_triggered = True

                if exit_triggered:
                    trades.append({
                        'timestamp':      pos['entry_ts'],
                        'exit_timestamp': ts_pd,
                        'signal_type':    'trade',
                        'direction':      pos['direction'],
                        'price':          pos['entry_price'],
                        'exit_price':     c,
                        'entry_type':     'PATTERN_BREAKOUT',
                        'sl_price':       0.0,
                        'exit_reason':    'ST_flip',
                    })
                    new_allowed = ts_pd + pd.Timedelta(hours=cooldown_hours)
                    if pos['direction'] == 'long':
                        entry_allowed_long  = new_allowed
                    else:
                        entry_allowed_short = new_allowed
                else:
                    still_open.append(pos)
            open_positions = still_open

            # ----------------------------------------------------------
            # ENTRY: max 2 positions at a time
            # ----------------------------------------------------------
            if len(open_positions) >= 2:
                continue

            long_allowed  = ts_pd >= entry_allowed_long
            short_allowed = ts_pd >= entry_allowed_short

            if not long_allowed and not short_allowed:
                continue

            # Walk back collecting exactly lookback_max unique bricks
            raw_window   = []
            unique_count = 0
            prev_val     = None
            j            = i - 1
            while j >= 0 and unique_count < self.lookback_max:
                v = closes[j]
                if prev_val is None or v != prev_val:
                    unique_count += 1
                    prev_val = v
                raw_window.insert(0, v)
                j -= 1

            if unique_count < self.lookback_min:
                continue

            # Deduplicate pattern window
            seen = []
            for v in raw_window:
                if not seen or v != seen[-1]:
                    seen.append(v)
            pattern_closes = np.array(seen)

            if len(pattern_closes) < self.lookback_min or len(pattern_closes) > self.lookback_max:
                continue

            result = self._detect_pattern(pattern_closes, box_size)
            if result is None:
                continue

            ptype, bull_level, bear_level = result

            if ptype in ('bull', 'symmetric') and c > bull_level and long_allowed:
                if c < bull_level + 0.3 * box_size:
                    continue
                open_positions.append({
                    'direction':   'long',
                    'entry_price': c,
                    'entry_ts':    ts_pd,
                    'entry_bar':   i,
                })
                entry_allowed_long = ts_pd + pd.Timedelta(hours=cooldown_hours)

            elif ptype in ('bear', 'symmetric') and c < bear_level and short_allowed:
                if c > bear_level - 0.3 * box_size:
                    continue
                open_positions.append({
                    'direction':   'short',
                    'entry_price': c,
                    'entry_ts':    ts_pd,
                    'entry_bar':   i,
                })
                entry_allowed_short = ts_pd + pd.Timedelta(hours=cooldown_hours)

        # --- End-of-data: close remaining positions (respect 4-bar hold) ---
        if open_positions and n > 0:
            last_i  = n - 1
            last_ts = pd.Timestamp(timestamps[last_i])
            last_c  = closes[last_i]
            for pos in open_positions:
                if last_i - pos['entry_bar'] >= 4:
                    trades.append({
                        'timestamp':      pos['entry_ts'],
                        'exit_timestamp': last_ts,
                        'signal_type':    'trade',
                        'direction':      pos['direction'],
                        'price':          pos['entry_price'],
                        'exit_price':     last_c,
                        'entry_type':     'PATTERN_BREAKOUT',
                        'sl_price':       0.0,
                        'exit_reason':    'end_of_data',
                    })

        return trades
