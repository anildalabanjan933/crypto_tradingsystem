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

    _cache = {}

    def build(self, closes: np.ndarray) -> pd.DataFrame:
        """
        Build Renko bars from a 1-D array of close prices.
        INCREMENTAL: if called again with a longer closes array that is an
        exact extension of a previous call (same box_size), only the NEW
        rows are processed - old bricks are reused unchanged from cache.
        Falls back to a full rebuild automatically if anything does not
        match exactly - output is guaranteed identical to full rebuild.

        Returns a DataFrame with columns:
            bar_index, renko_open, renko_close, renko_dir,
            renko_high, renko_low
        where bar_index corresponds to the source candle index.
        """
        box = self.box_size
        closes = np.asarray(closes)
        n = len(closes)
        cols = ['bar_index', 'renko_open', 'renko_close', 'renko_dir', 'renko_high', 'renko_low']
        if n == 0:
            return pd.DataFrame(columns=cols)

        key = box
        cached = RenkoBuilder._cache.get(key)

        start_i = 0
        r_open = closes[0]
        r_close = closes[0]
        r_dir = 0
        records = []

        if cached is not None:
            c_closes = cached['closes']
            c_n = len(c_closes)
            if n >= c_n and c_n > 0 and np.array_equal(closes[:c_n], c_closes):
                start_i = c_n
                r_open = cached['r_open']
                r_close = cached['r_close']
                r_dir = cached['r_dir']
                records = list(cached['records'])

        for i in range(start_i, n):
            close = closes[i]
            if r_dir >= 0:
                up_thresh = r_open + box
                dn_thresh = r_open - box * 2
            else:
                up_thresh = r_open + box * 2
                dn_thresh = r_open - box

            if close >= up_thresh:
                boxes_up = int((close - r_open) / box)
                for _ in range(boxes_up):
                    r_open = r_open if r_dir >= 0 else r_open + box
                    r_close = r_open + box
                    r_dir = 1
                    records.append((i, r_open, r_close, r_dir, max(r_open, r_close), min(r_open, r_close)))
                    r_open = r_close

            elif close <= dn_thresh:
                boxes_dn = int((r_open - close) / box)
                for _ in range(boxes_dn):
                    r_open = r_open if r_dir <= 0 else r_open - box
                    r_close = r_open - box
                    r_dir = -1
                    records.append((i, r_open, r_close, r_dir, max(r_open, r_close), min(r_open, r_close)))
                    r_open = r_close

        RenkoBuilder._cache[key] = {
            'closes': closes.copy(),
            'r_open': r_open, 'r_close': r_close, 'r_dir': r_dir,
            'records': records,
        }
        if len(RenkoBuilder._cache) > 5:
            RenkoBuilder._cache = {key: RenkoBuilder._cache[key]}

        if not records:
            return pd.DataFrame(columns=cols)

        return pd.DataFrame.from_records(records, columns=cols)


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

    _cache = {}

    def __init__(self, atr_period: int = 5, factor: float = 4.0):
        self.atr_period = atr_period
        self.factor = factor

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        INCREMENTAL: extends from cache if df is an exact extension of a
        previous call (same atr_period+factor). Falls back to full compute
        if anything does not match - output guaranteed identical.
        """
        n = len(df)
        period = self.atr_period
        factor = self.factor
        high = df['renko_high'].values
        low = df['renko_low'].values
        close = df['renko_close'].values
        hl2 = (high + low) / 2.0

        key = (period, factor)
        cached = SupertrendIndicator._cache.get(key)

        tr = np.zeros(n); atr = np.zeros(n)
        final_upper = np.zeros(n); final_lower = np.zeros(n)
        st_dir = np.zeros(n, dtype=int)

        resumed = False
        start_i = 1
        if cached is not None:
            c_n = cached['n']
            if n >= c_n and c_n > 0 and \
               np.array_equal(high[:c_n], cached['high']) and \
               np.array_equal(low[:c_n], cached['low']) and \
               np.array_equal(close[:c_n], cached['close']):
                tr[:c_n] = cached['tr']; atr[:c_n] = cached['atr']
                final_upper[:c_n] = cached['final_upper']
                final_lower[:c_n] = cached['final_lower']
                st_dir[:c_n] = cached['st_dir']
                start_i = c_n
                resumed = True

        if not resumed:
            tr[0] = high[0] - low[0]
            atr[0] = tr[0]
            final_upper[0] = hl2[0] + factor * atr[0]
            final_lower[0] = hl2[0] - factor * atr[0]
            st_dir[0] = -1
            start_i = 1

        alpha = 1.0 / period
        for i in range(start_i, n):
            tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
            atr[i] = atr[i-1] * (1.0 - alpha) + tr[i] * alpha
            b_upper = hl2[i] + factor * atr[i]
            b_lower = hl2[i] - factor * atr[i]
            final_upper[i] = b_upper if b_upper < final_upper[i-1] or close[i-1] > final_upper[i-1] else final_upper[i-1]
            final_lower[i] = b_lower if b_lower > final_lower[i-1] or close[i-1] < final_lower[i-1] else final_lower[i-1]
            if st_dir[i-1] == 1:
                st_dir[i] = -1 if close[i] > final_upper[i] else 1
            else:
                st_dir[i] = 1 if close[i] < final_lower[i] else -1

        SupertrendIndicator._cache[key] = {
            'n': n, 'high': high.copy(), 'low': low.copy(), 'close': close.copy(),
            'tr': tr.copy(), 'atr': atr.copy(),
            'final_upper': final_upper.copy(), 'final_lower': final_lower.copy(),
            'st_dir': st_dir.copy(),
        }
        if len(SupertrendIndicator._cache) > 5:
            SupertrendIndicator._cache = {key: SupertrendIndicator._cache[key]}

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
        renko_close = df['renko_close'].values          # FIXED: use renko_close for pivot prices

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
                pivot_bar   = i - R if i >= R else i
                pivot_price = renko_close[pivot_bar]                 # FIXED: was high[pivot_bar]
                sh_hist = (sh_hist + [(pivot_bar, pivot_price)])[-2:]
                last_sh = pivot_price

            if is_swing_low[i]:
                pivot_bar   = i - R if i >= R else i
                pivot_price = renko_close[pivot_bar]                 # FIXED: was low[pivot_bar]
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
