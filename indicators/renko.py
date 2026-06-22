# indicators/renko.py
# Renko chart builder, Supertrend indicator, and Swing detector
# for BTCUSD 2H Traditional Renko backtest system

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# TRENDLINE PROJECTION UTILITY
# ---------------------------------------------------------------------------

def _trendline_value_at(swings: list, current_bar: int, max_bars: int = 50):
    """
    Project a sloped trendline to the current bar.

    Parameters
    ----------
    swings      : list of (bar_idx, price) tuples, oldest first, max 2 entries
    current_bar : index of the bar we are projecting to
    max_bars    : if the most recent swing is older than this many bars,
                  the trendline is considered stale and None is returned

    Returns
    -------
    float or None
        Projected trendline price at current_bar, or None if invalid/stale.
    """
    if len(swings) < 2:
        return None
    (b1, p1), (b2, p2) = swings[-2], swings[-1]
    if (current_bar - b2) > max_bars:
        return None          # stale trendline, ignore
    if b2 == b1:
        return float(p2)     # vertical edge case
    slope = (p2 - p1) / (b2 - b1)
    return float(p2 + slope * (current_bar - b2))


# ---------------------------------------------------------------------------
# RENKO BUILDER
# ---------------------------------------------------------------------------

class RenkoBuilder:
    """
    Builds Traditional Renko bars from a sequence of close prices.

    Traditional Renko thresholds:
      Up   : renko_open + box_size        (if current dir >= 0, continuation)
             renko_open + box_size * 2    (if current dir <  0, reversal)
      Down : renko_open - box_size        (if current dir <= 0, continuation)
             renko_open - box_size * 2    (if current dir >  0, reversal)

    Multi-box jumps are handled by advancing renko_open by box_size per bar.
    Reversal open steps by 1 box explicitly before counting additional boxes.

    Fields produced per bar
    -----------------------
    renko_open  : open price of current Renko brick
    renko_close : close price of current Renko brick
    renko_dir   : +1 = bullish (green), -1 = bearish (red)
    renko_high  : max(renko_open, renko_close)
    renko_low   : min(renko_open, renko_close)
    """

    def __init__(self, box_size: float = 200.0):
        self.box_size = box_size

    def build(self, closes: np.ndarray) -> pd.DataFrame:
        """
        Build Renko bars from a 1-D array of close prices.

        Returns a DataFrame with columns:
            bar_index, renko_open, renko_close, renko_dir,
            renko_high, renko_low
        where bar_index corresponds to the source candle index.
        """
        box = self.box_size
        records = []

        # Initialise from first close
        r_open = closes[0]
        r_close = closes[0]
        r_dir = 0  # neutral until first brick forms

        for i, close in enumerate(closes):
            if r_dir >= 0:
                up_thresh = r_open + box
                dn_thresh = r_open - box * 2
            else:
                up_thresh = r_open + box * 2
                dn_thresh = r_open - box

            if close >= up_thresh:
                # One or more bullish bricks
                boxes_up = int((close - r_open) / box)
                for _ in range(boxes_up):
                    r_open = r_open if r_dir >= 0 else r_open + box
                    r_close = r_open + box
                    r_dir = 1
                    records.append({
                        'bar_index': i,
                        'renko_open': r_open,
                        'renko_close': r_close,
                        'renko_dir': r_dir,
                        'renko_high': max(r_open, r_close),
                        'renko_low': min(r_open, r_close),
                    })
                    r_open = r_close

            elif close <= dn_thresh:
                # One or more bearish bricks
                boxes_dn = int((r_open - close) / box)
                for _ in range(boxes_dn):
                    r_open = r_open if r_dir <= 0 else r_open - box
                    r_close = r_open - box
                    r_dir = -1
                    records.append({
                        'bar_index': i,
                        'renko_open': r_open,
                        'renko_close': r_close,
                        'renko_dir': r_dir,
                        'renko_high': max(r_open, r_close),
                        'renko_low': min(r_open, r_close),
                    })
                    r_open = r_close

        if not records:
            return pd.DataFrame(columns=[
                'bar_index', 'renko_open', 'renko_close',
                'renko_dir', 'renko_high', 'renko_low'
            ])

        return pd.DataFrame(records).reset_index(drop=True)


# ---------------------------------------------------------------------------
# SUPERTREND INDICATOR
# ---------------------------------------------------------------------------

class SupertrendIndicator:
    """
    Supertrend using Wilder's RMA for ATR.

    ATR formula : atr[i] = atr[i-1] * (1 - 1/period) + tr[i] * (1/period)
    Direction   : -1 = Bullish (GREEN), +1 = Bearish (RED)

    Uses actual renko_high / renko_low for ATR calculation.
    Uses renko_close for direction decisions.
    """

    def __init__(self, atr_period: int = 5, factor: float = 4.0):
        self.atr_period = atr_period
        self.factor = factor

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Supertrend on a Renko DataFrame.

        Input columns required : renko_high, renko_low, renko_close
        Added columns          : atr, st_upper, st_lower, st_dir
            st_dir : -1 = bull (GREEN), +1 = bear (RED)
        """
        n = len(df)
        period = self.atr_period
        factor = self.factor

        high = df['renko_high'].values
        low = df['renko_low'].values
        close = df['renko_close'].values

        # True Range
        tr = np.zeros(n)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1])
            )

        # Wilder's RMA
        atr = np.zeros(n)
        atr[0] = tr[0]
        alpha = 1.0 / period
        for i in range(1, n):
            atr[i] = atr[i - 1] * (1.0 - alpha) + tr[i] * alpha

        # Basic upper / lower bands
        hl2 = (high + low) / 2.0
        basic_upper = hl2 + factor * atr
        basic_lower = hl2 - factor * atr

        # Final bands with carry-forward logic
        final_upper = np.zeros(n)
        final_lower = np.zeros(n)
        final_upper[0] = basic_upper[0]
        final_lower[0] = basic_lower[0]

        for i in range(1, n):
            final_upper[i] = (
                basic_upper[i]
                if basic_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]
                else final_upper[i - 1]
            )
            final_lower[i] = (
                basic_lower[i]
                if basic_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]
                else final_lower[i - 1]
            )

        # Direction : -1 = bull (GREEN), +1 = bear (RED)
        st_dir = np.zeros(n, dtype=int)
        st_dir[0] = -1  # default bullish

        for i in range(1, n):
            if st_dir[i - 1] == 1:
                st_dir[i] = -1 if close[i] > final_upper[i] else 1
            else:
                st_dir[i] = 1 if close[i] < final_lower[i] else -1

        result = df.copy()
        result['atr'] = atr
        result['st_upper'] = final_upper
        result['st_lower'] = final_lower
        result['st_dir'] = st_dir
        return result


# ---------------------------------------------------------------------------
# SWING DETECTOR
# ---------------------------------------------------------------------------

class SwingDetector:
    """
    Detects swing highs and swing lows on Renko bars.

    Rules
    -----
    - Strict pivot : unique max/min in the L+R+1 window
      Formula      : np.sum(window == center) == 1
    - Confirmation : swing confirmed after swing_right bars pass
    - Storage      : last 2 confirmed swing highs as [(bar_idx, price), ...]
                     last 2 confirmed swing lows  as [(bar_idx, price), ...]
                     oldest first in each list
    - Scalars      : last_swing_high and last_swing_low kept for horizontal S/R
    """

    def __init__(self, swing_left: int = 2, swing_right: int = 2):
        self.swing_left = swing_left
        self.swing_right = swing_right

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect swings on a Renko DataFrame that already has st_dir.

        Input columns required : renko_high, renko_low, renko_close, st_dir
        Added columns          :
            is_swing_high  : bool
            is_swing_low   : bool
            last_swing_high: float  (scalar, latest confirmed swing high price)
            last_swing_low : float  (scalar, latest confirmed swing low price)
            swing_highs_hist: object (list of (bar_idx, price), last 2)
            swing_lows_hist : object (list of (bar_idx, price), last 2)
        """
        n = len(df)
        L = self.swing_left
        R = self.swing_right

        high = df['renko_high'].values
        low = df['renko_low'].values

        is_swing_high = np.zeros(n, dtype=bool)
        is_swing_low = np.zeros(n, dtype=bool)

        # Detect pivots - confirmed at bar[i + R]
        for i in range(L, n - R):
            # Swing high
            window_h = high[i - L: i + R + 1]
            center_h = high[i]
            if center_h == window_h.max() and np.sum(window_h == center_h) == 1:
                is_swing_high[i + R] = True  # confirmed at bar i+R

            # Swing low
            window_l = low[i - L: i + R + 1]
            center_l = low[i]
            if center_l == window_l.min() and np.sum(window_l == center_l) == 1:
                is_swing_low[i + R] = True   # confirmed at bar i+R

        # Build running history columns
        last_sh = np.nan
        last_sl = np.nan
        sh_hist = []   # list of (bar_idx, price), max 2, oldest first
        sl_hist = []   # list of (bar_idx, price), max 2, oldest first

        col_last_sh = np.full(n, np.nan)
        col_last_sl = np.full(n, np.nan)
        col_sh_hist = [None] * n
        col_sl_hist = [None] * n

        for i in range(n):
            if is_swing_high[i]:
                # The actual pivot bar is i - R (confirmed R bars ago)
                pivot_bar = i - R if i >= R else i
                pivot_price = high[pivot_bar]
                sh_hist = (sh_hist + [(pivot_bar, pivot_price)])[-2:]
                last_sh = pivot_price

            if is_swing_low[i]:
                pivot_bar = i - R if i >= R else i
                pivot_price = low[pivot_bar]
                sl_hist = (sl_hist + [(pivot_bar, pivot_price)])[-2:]
                last_sl = pivot_price

            col_last_sh[i] = last_sh
            col_last_sl[i] = last_sl
            col_sh_hist[i] = list(sh_hist)   # copy to avoid mutation
            col_sl_hist[i] = list(sl_hist)

        result = df.copy()
        result['is_swing_high'] = is_swing_high
        result['is_swing_low'] = is_swing_low
        result['last_swing_high'] = col_last_sh
        result['last_swing_low'] = col_last_sl
        result['swing_highs_hist'] = col_sh_hist
        result['swing_lows_hist'] = col_sl_hist
        return result
