# MASTER VALIDATION REPORT
Generated: Sat Oct 10 07:55:54 UTC 2026
Base commit: 7e56b06

## BUG 8 - real_close patch (fill price lag)
```diff
diff --git a/strategies/backtest/renko_smiio_cross_v3_strategy.py b/strategies/backtest/renko_smiio_cross_v3_strategy.py
index 35df150..0435acb 100644
--- a/strategies/backtest/renko_smiio_cross_v3_strategy.py
+++ b/strategies/backtest/renko_smiio_cross_v3_strategy.py
@@ -124,6 +124,7 @@ class RenkoSMIIOCrossV3Strategy(BaseStrategy):
         _max_idx = len(_ts_values) - 1
         _idx_arr[_idx_arr > _max_idx] = _max_idx
         renko_raw['timestamp'] = _ts_values[_idx_arr]
+        renko_raw['real_close'] = closes[_idx_arr]
         return renko_raw
 
     # -----------------------------------------------------------------------
@@ -135,6 +136,7 @@ class RenkoSMIIOCrossV3Strategy(BaseStrategy):
         n = len(df)
 
         closes = df['renko_close'].values
+        real_closes = df['real_close'].values
         box = max(1, round((self.reference_price if self.reference_price else closes[0]) * self.renko_box_pct))
 
         # --- SMIIO (identical calc/params to original S4) ---
@@ -164,7 +166,7 @@ class RenkoSMIIOCrossV3Strategy(BaseStrategy):
             if current_direction == 'long' and smi_cross_down:
                 signals.append({
                     'signal_type': 'EXIT',
-                    'price':       self._apply_slippage(close, 'long', False),
+                    'price':       self._apply_slippage(real_closes[i], 'long', False),
                     'timestamp':   ts,
                     'sl_price':    close - box,
                     'entry_type':  '',
@@ -177,7 +179,7 @@ class RenkoSMIIOCrossV3Strategy(BaseStrategy):
             elif current_direction == 'short' and smi_cross_up:
                 signals.append({
                     'signal_type': 'EXIT',
-                    'price':       self._apply_slippage(close, 'short', False),
+                    'price':       self._apply_slippage(real_closes[i], 'short', False),
                     'timestamp':   ts,
                     'sl_price':    close + box,
                     'entry_type':  '',
@@ -195,7 +197,7 @@ class RenkoSMIIOCrossV3Strategy(BaseStrategy):
                 if smi_cross_up:
                     signals.append({
                         'signal_type': 'ENTRY',
-                        'price':       self._apply_slippage(close, 'long', True),
+                        'price':       self._apply_slippage(real_closes[i], 'long', True),
                         'timestamp':   ts,
                         'sl_price':    close - box * 2,
                         'entry_type':  'SMIIO_CROSS_UP',
@@ -207,7 +209,7 @@ class RenkoSMIIOCrossV3Strategy(BaseStrategy):
                 elif smi_cross_down:
                     signals.append({
                         'signal_type': 'ENTRY',
-                        'price':       self._apply_slippage(close, 'short', True),
+                        'price':       self._apply_slippage(real_closes[i], 'short', True),
                         'timestamp':   ts,
                         'sl_price':    close + box * 2,
                         'entry_type':  'SMIIO_CROSS_DOWN',
diff --git a/strategies/backtest/renko_smiio_supertrend_strategy.py b/strategies/backtest/renko_smiio_supertrend_strategy.py
index d9becd1..b3cb3d1 100644
--- a/strategies/backtest/renko_smiio_supertrend_strategy.py
+++ b/strategies/backtest/renko_smiio_supertrend_strategy.py
@@ -153,6 +153,7 @@ class RenkoSMIIOSupertrendStrategy(BaseStrategy):
         _max_idx = len(_ts_values) - 1
         _idx_arr[_idx_arr > _max_idx] = _max_idx
         renko_raw['timestamp'] = _ts_values[_idx_arr]
+        renko_raw['real_close'] = closes[_idx_arr]
         return renko_raw
 
     # -----------------------------------------------------------------------
@@ -164,6 +165,7 @@ class RenkoSMIIOSupertrendStrategy(BaseStrategy):
         n = len(df)
 
         closes    = df['renko_close'].values
+        real_closes = df['real_close'].values
         renko_dir = df['renko_dir'].values
         current_price = closes[0] if len(closes) > 0 else 100000.0
         box = max(1, round((self.reference_price if self.reference_price else closes[0]) * self.renko_box_pct))
@@ -217,7 +219,7 @@ class RenkoSMIIOSupertrendStrategy(BaseStrategy):
             if current_direction == 'long' and st_flip_red and r_dir == -1:
                 signals.append({
                     'signal_type': 'EXIT',
-                    'price':       self._apply_slippage(close, 'long', False),
+                    'price':       self._apply_slippage(real_closes[i], 'long', False),
                     'timestamp':   ts,
                     'sl_price':    close - box,
                     'entry_type':  '',
@@ -232,7 +234,7 @@ class RenkoSMIIOSupertrendStrategy(BaseStrategy):
             elif current_direction == 'short' and st_flip_green and r_dir == 1:
                 signals.append({
                     'signal_type': 'EXIT',
-                    'price':       self._apply_slippage(close, 'short', False),
+                    'price':       self._apply_slippage(real_closes[i], 'short', False),
                     'timestamp':   ts,
                     'sl_price':    close + box,
                     'entry_type':  '',
@@ -283,7 +285,7 @@ class RenkoSMIIOSupertrendStrategy(BaseStrategy):
                 elif side == 'long' and r_dir == 1:
                     signals.append({
                         'signal_type': 'ENTRY',
-                        'price':       self._apply_slippage(close, 'long', True),
+                        'price':       self._apply_slippage(real_closes[i], 'long', True),
                         'timestamp':   ts,
                         'sl_price':    close - box * 2,
                         'entry_type':  pending['entry_type'],
@@ -297,7 +299,7 @@ class RenkoSMIIOSupertrendStrategy(BaseStrategy):
                 elif side == 'short' and r_dir == -1:
                     signals.append({
                         'signal_type': 'ENTRY',
-                        'price':       self._apply_slippage(close, 'short', True),
+                        'price':       self._apply_slippage(real_closes[i], 'short', True),
                         'timestamp':   ts,
                         'sl_price':    close + box * 2,
                         'entry_type':  pending['entry_type'],
```

## BUG 9 - renko.py reversal overshoot fix
```diff
diff --git a/indicators/renko.py b/indicators/renko.py
index c689713..f555db5 100644
--- a/indicators/renko.py
+++ b/indicators/renko.py
@@ -91,7 +91,7 @@ class RenkoBuilder:
             return pd.DataFrame(columns=cols)
 
         _anchor = self.reference_price if self.reference_price is not None else closes[0]
-        key = (box, _anchor)
+        key = (box, _anchor, 'v2_fixed_reversal_overshoot')
         cached = RenkoBuilder._cache.get(key)
 
         start_i = 0
@@ -120,7 +120,10 @@ class RenkoBuilder:
                 dn_thresh = r_open - box
 
             if close >= up_thresh:
-                boxes_up = int((close - r_open) / box)
+                if r_dir < 0:
+                    boxes_up = int((close - (r_open + box)) / box)
+                else:
+                    boxes_up = int((close - r_open) / box)
                 for _ in range(boxes_up):
                     r_open = r_open if r_dir >= 0 else r_open + box
                     r_close = r_open + box
@@ -129,7 +132,10 @@ class RenkoBuilder:
                     r_open = r_close
 
             elif close <= dn_thresh:
-                boxes_dn = int((r_open - close) / box)
+                if r_dir > 0:
+                    boxes_dn = int(((r_open - box) - close) / box)
+                else:
+                    boxes_dn = int((r_open - close) / box)
                 for _ in range(boxes_dn):
                     r_open = r_open if r_dir <= 0 else r_open - box
                     r_close = r_open - box
```

## CODE VERIFICATION (grep proof fixes are live in code used for backtest)
```
94:        key = (box, _anchor, 'v2_fixed_reversal_overshoot')
156:        renko_raw['real_close'] = closes[_idx_arr]
168:        real_closes = df['real_close'].values
222:                    'price':       self._apply_slippage(real_closes[i], 'long', False),
237:                    'price':       self._apply_slippage(real_closes[i], 'short', False),
288:                        'price':       self._apply_slippage(real_closes[i], 'long', True),
302:                        'price':       self._apply_slippage(real_closes[i], 'short', True),
```

## FULL FIXED FILE: indicators/renko.py
```python
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

    def __init__(self, box_size: float = 200.0, reference_price: float = None):
        self.box_size = box_size
        self.reference_price = reference_price

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

        _anchor = self.reference_price if self.reference_price is not None else closes[0]
        key = (box, _anchor, 'v2_fixed_reversal_overshoot')
        cached = RenkoBuilder._cache.get(key)

        start_i = 0
        r_open = _anchor
        r_close = _anchor
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
                if r_dir < 0:
                    boxes_up = int((close - (r_open + box)) / box)
                else:
                    boxes_up = int((close - r_open) / box)
                for _ in range(boxes_up):
                    r_open = r_open if r_dir >= 0 else r_open + box
                    r_close = r_open + box
                    r_dir = 1
                    records.append((i, r_open, r_close, r_dir, max(r_open, r_close), min(r_open, r_close)))
                    r_open = r_close

            elif close <= dn_thresh:
                if r_dir > 0:
                    boxes_dn = int(((r_open - box) - close) / box)
                else:
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
```

## FULL FIXED FILE: strategies/backtest/renko_smiio_supertrend_strategy.py
```python
# strategies/renko_smiio_supertrend_strategy.py
# Strategy: Renko + SMIIO + Supertrend
# Entry : SMIIO crossover + ST confirmation + 1 brick close in signal direction
# Exit  : ST flip + 1 brick close in exit direction

import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy
from indicators.renko import RenkoBuilder, SupertrendIndicator


# ===========================================================================
# SMIIO INDICATOR
# =====tree /F D:\crypto_trading_system======================================================================
def compute_smiio(closes: np.ndarray, short_len: int = 5, long_len: int = 20, signal_len: int = 5) -> tuple:
    n = len(closes)
    mom     = np.zeros(n)
    abs_mom = np.zeros(n)

    for i in range(1, n):
        mom[i]     = closes[i] - closes[i - 1]
        abs_mom[i] = abs(mom[i])

    def ema(arr, period):
        out = np.zeros(len(arr))
        k   = 2.0 / (period + 1)
        out[0] = arr[0]
        for i in range(1, len(arr)):
            out[i] = arr[i] * k + out[i - 1] * (1 - k)
        return out

    ema1_mom = ema(mom,      short_len)
    ema2_mom = ema(ema1_mom, long_len)
    ema1_abs = ema(abs_mom,  short_len)
    ema2_abs = ema(ema1_abs, long_len)

    smi    = np.where(ema2_abs != 0, ema2_mom / ema2_abs * 100.0, 0.0)
    signal = ema(smi, signal_len)

    return smi, signal


# ===========================================================================
# STRATEGY CLASS
# ===========================================================================
class RenkoSMIIOSupertrendStrategy(BaseStrategy):
    """
    Uses SupertrendIndicator from indicators/renko.py (same as RenkoReversal)
    st_dir: -1 = GREEN (bullish), +1 = RED (bearish)

    Entry Types
    -----------
    BUY_A  : SMIIO crosses up   + ST already GREEN + 1 green brick close
    BUY_B  : ST flips GREEN     + SMIIO already up + 1 green brick close
    SELL_A : SMIIO crosses down + ST already RED   + 1 red brick close
    SELL_B : ST flips RED       + SMIIO already down + 1 red brick close

    Exit
    ----
    ST flip + 1 brick close in exit direction

    Filter Parameters (disabled by default, reserved for future optimization)
    --------------------------------------------------------------------------
    smiio_avoid_entry_above : float  — skip entry if abs(smi) > threshold (0.0 = disabled)
    crossover_distance      : float  — min gap between smi and signal at crossover (0.0 = disabled)
    crossover_count_limit   : int    — block entry if consecutive small crossovers >= N (0 = disabled)
    """

    # -----------------------------------------------------------------------
    # __init__
    # -----------------------------------------------------------------------
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        super().__init__(data_dict=data_dict, lot_size=lot_size)

        symbol        = kwargs.get('symbol', 'BTCUSD')
        current_price = kwargs.get('current_price', None)

        # --- Core strategy parameters ---
        self.renko_box_pct = kwargs.get('renko_box_pct', 0.001)
        self.reference_price = kwargs.get('reference_price', None)
        self.renko_timeframe = kwargs.get('renko_timeframe', '2h')
        self.st_atr_length = kwargs.get('st_atr_length', 5)
        self.st_factor      = kwargs.get('st_factor',      2.0)
        self.smiio_shortlen = kwargs.get('smiio_shortlen', 10)
        self.smiio_longlen  = kwargs.get('smiio_longlen',  20)
        self.smiio_siglen   = kwargs.get('smiio_siglen',   3)
        self.slippage_usd   = kwargs.get('slippage_usd',   0.0)
        self.commission_pct = kwargs.get('commission_pct', 0.0)

        # --- Filter parameters (disabled by default) ---
        # Set value > 0 to activate when optimizing for sideways/ranging markets
        self.smiio_avoid_entry_above = kwargs.get('smiio_avoid_entry_above', 0.0)  # 0.0 = disabled
        self.crossover_distance      = kwargs.get('crossover_distance',      0.0)  # 0.0 = disabled
        self.crossover_count_limit   = kwargs.get('crossover_count_limit',   0)    # 0   = disabled

    # -----------------------------------------------------------------------
    # Abstract method implementations
    # -----------------------------------------------------------------------
    @property
    def optimization_params(self) -> dict:
        return {
            # --- Core parameters (active optimization) ---
            'renko_box_pct': {'default': 0.0020, 'min': 0.0010, 'max': 0.0040, 'step': 0.0005},
            'st_atr_length':  {'default': 5,    'min': 3,    'max': 14,   'step': 1},
            'st_factor':      {'default': 2.0,  'min': 1.0,  'max': 5.0,  'step': 0.5},
            'smiio_shortlen': {'default': 5,    'min': 3,    'max': 10,   'step': 1},
            'smiio_longlen':  {'default': 20,   'min': 10,   'max': 40,   'step': 5},

            # --- Filter parameters (reserved, not in active optimization) ---
            # Uncomment below to include in optimization for sideways market tuning
            # 'smiio_avoid_entry_above': {'default': 0.0, 'min': 0.2, 'max': 0.6, 'step': 0.1},
            # 'crossover_distance':      {'default': 0.0, 'min': 0.1, 'max': 2.5, 'step': 0.1},
            # 'crossover_count_limit':   {'default': 0,   'min': 1,   'max': 3,   'step': 1},
        }

    @property
    def required_timeframes(self) -> list:
        return [self.renko_timeframe]

    # -----------------------------------------------------------------------
    # Slippage helper
    # -----------------------------------------------------------------------
    def _apply_slippage(self, price: float, direction: str, is_entry: bool) -> float:
        slip = self.slippage_usd
        if direction == 'long':
            return price + slip if is_entry else price - slip
        else:
            return price - slip if is_entry else price + slip

    # -----------------------------------------------------------------------
    # Renko DataFrame builder
    # -----------------------------------------------------------------------
    def _build_renko_df(self) -> pd.DataFrame:
        tf = self.renko_timeframe
        df_tf = self._data.get(tf)
        if df_tf is None or len(df_tf) == 0:
            raise ValueError(f"Requires '{tf}' timeframe data")

        closes = df_tf['close'].values
        timestamps = (df_tf.index if isinstance(df_tf.index, pd.DatetimeIndex)
                      else pd.to_datetime(df_tf['timestamp']))

        current_price = closes[0] if len(closes) > 0 else 100000.0
        _anchor = self.reference_price if self.reference_price else closes[0]
        box_size = max(1, round(_anchor * self.renko_box_pct))
        builder = RenkoBuilder(box_size=box_size, reference_price=_anchor)
        renko_raw = builder.build(closes)
        if renko_raw is None or len(renko_raw) == 0:
            raise ValueError("RenkoBuilder produced no bricks")

        _ts_values = timestamps.values if hasattr(timestamps, 'values') else np.asarray(timestamps)
        _idx_arr = renko_raw['bar_index'].values.copy()
        _max_idx = len(_ts_values) - 1
        _idx_arr[_idx_arr > _max_idx] = _max_idx
        renko_raw['timestamp'] = _ts_values[_idx_arr]
        renko_raw['real_close'] = closes[_idx_arr]
        return renko_raw

    # -----------------------------------------------------------------------
    # generate_signals  — MAIN LOGIC
    # -----------------------------------------------------------------------
    def generate_signals(self) -> list:
        df = self._build_renko_df()
        timestamps = df['timestamp'].values
        n = len(df)

        closes    = df['renko_close'].values
        real_closes = df['real_close'].values
        renko_dir = df['renko_dir'].values
        current_price = closes[0] if len(closes) > 0 else 100000.0
        box = max(1, round((self.reference_price if self.reference_price else closes[0]) * self.renko_box_pct))

        # --- SupertrendIndicator ---
        st_ind = SupertrendIndicator(
            atr_period=self.st_atr_length,
            factor=self.st_factor,
        )
        df_st  = st_ind.calculate(df)
        st_dir = df_st['st_dir'].values

        # --- SMIIO ---
        smi, sig = compute_smiio(
            closes,
            short_len=self.smiio_shortlen,
            long_len=self.smiio_longlen,
            signal_len=self.smiio_siglen,
        )

        # --- Signal loop ---
        signals           = []
        current_direction = None
        pending           = None
        pending_set_bar   = -1
        last_exit_ts      = None

        _ts_strings = [pd.Timestamp(t).strftime('%Y-%m-%dT%H:%M:%S') for t in timestamps]
        for i in range(1, n):
            ts    = _ts_strings[i]
            close = closes[i]
            r_dir = renko_dir[i]
            st    = st_dir[i]
            prev_st = st_dir[i - 1]

            smi_cross_up   = smi[i] > sig[i] and smi[i - 1] <= sig[i - 1]
            smi_cross_down = smi[i] < sig[i] and smi[i - 1] >= sig[i - 1]
            st_flip_green  = prev_st == 1  and st == -1
            st_flip_red    = prev_st == -1 and st == 1
            smi_above      = smi[i] > sig[i]
            smi_below      = smi[i] < sig[i]

            # FIX 2: Cancel pending if not confirmed within 1 bar
            if pending is not None and i > pending_set_bar + 1:
                pending = None
                pending_set_bar = -1

            # ----------------------------------------------------------
            # EXIT: ST flip confirmed
            # ----------------------------------------------------------
            if current_direction == 'long' and st_flip_red and r_dir == -1:
                signals.append({
                    'signal_type': 'EXIT',
                    'price':       self._apply_slippage(real_closes[i], 'long', False),
                    'timestamp':   ts,
                    'sl_price':    close - box,
                    'entry_type':  '',
                    'exit_type':   'ST_FLIP_RED',
                    'direction':   'long',
                })
                current_direction = None
                pending           = None
                pending_set_bar   = -1
                last_exit_ts      = ts

            elif current_direction == 'short' and st_flip_green and r_dir == 1:
                signals.append({
                    'signal_type': 'EXIT',
                    'price':       self._apply_slippage(real_closes[i], 'short', False),
                    'timestamp':   ts,
                    'sl_price':    close + box,
                    'entry_type':  '',
                    'exit_type':   'ST_FLIP_GREEN',
                    'direction':   'short',
                })
                current_direction = None
                pending           = None
                pending_set_bar   = -1
                last_exit_ts      = ts

            # ----------------------------------------------------------
            # SET PENDING — FIX 1: skip same bar as exit
            #             — FIX 3: single if/elif chain
            # ----------------------------------------------------------
            if current_direction is None:

                if smi_cross_up and st == -1:
                    pending = {'side': 'long', 'entry_type': 'BUY_A'}
                    pending_set_bar = i

                elif st_flip_green and smi_above:
                    pending = {'side': 'long', 'entry_type': 'BUY_B'}
                    pending_set_bar = i

                elif smi_cross_down and st == 1:
                    pending = {'side': 'short', 'entry_type': 'SELL_A'}
                    pending_set_bar = i

                elif st_flip_red and smi_below:
                    pending = {'side': 'short', 'entry_type': 'SELL_B'}
                    pending_set_bar = i

            # ----------------------------------------------------------
            # EXECUTE PENDING
            # ----------------------------------------------------------
            if pending is not None and current_direction is None:
                side = pending['side']

                if side == 'long' and st == 1:
                    pending = None
                    pending_set_bar = -1

                elif side == 'short' and st == -1:
                    pending = None
                    pending_set_bar = -1

                elif side == 'long' and r_dir == 1:
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price':       self._apply_slippage(real_closes[i], 'long', True),
                        'timestamp':   ts,
                        'sl_price':    close - box * 2,
                        'entry_type':  pending['entry_type'],
                        'exit_type':   '',
                        'direction':   'long',
                    })
                    current_direction = 'long'
                    pending           = None
                    pending_set_bar   = -1

                elif side == 'short' and r_dir == -1:
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price':       self._apply_slippage(real_closes[i], 'short', True),
                        'timestamp':   ts,
                        'sl_price':    close + box * 2,
                        'entry_type':  pending['entry_type'],
                        'exit_type':   '',
                        'direction':   'short',
                    })
                    current_direction = 'short'
                    pending           = None
                    pending_set_bar   = -1

        return signals
```

## FULL FIXED FILE: strategies/backtest/renko_smiio_cross_v3_strategy.py
```python
# strategies/backtest/renko_smiio_cross_v3_strategy.py
# TEST VARIANT (S4V3) of S4 - Renko + SMIIO CROSSOVER ONLY (no brick-direction, no Supertrend)
# Entry LONG  : SMIIO crosses ABOVE Signal
# Exit  LONG  : SMIIO crosses BELOW Signal
# Entry SHORT : SMIIO crosses BELOW Signal
# Exit  SHORT : SMIIO crosses ABOVE Signal
# Renko is still used for underlying brick construction/price series only -
# brick DIRECTION is NOT used as a trade-decision input.
# ISOLATED FILE - does not modify original S4 or S4V2 in any way.

import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy
from indicators.renko import RenkoBuilder


# ===========================================================================
# SMIIO INDICATOR (identical to original S4)
# ===========================================================================
def compute_smiio(closes: np.ndarray, short_len: int = 5, long_len: int = 20, signal_len: int = 5) -> tuple:
    n = len(closes)
    mom     = np.zeros(n)
    abs_mom = np.zeros(n)

    for i in range(1, n):
        mom[i]     = closes[i] - closes[i - 1]
        abs_mom[i] = abs(mom[i])

    def ema(arr, period):
        out = np.zeros(len(arr))
        k   = 2.0 / (period + 1)
        out[0] = arr[0]
        for i in range(1, len(arr)):
            out[i] = arr[i] * k + out[i - 1] * (1 - k)
        return out

    ema1_mom = ema(mom,      short_len)
    ema2_mom = ema(ema1_mom, long_len)
    ema1_abs = ema(abs_mom,  short_len)
    ema2_abs = ema(ema1_abs, long_len)

    smi    = np.where(ema2_abs != 0, ema2_mom / ema2_abs * 100.0, 0.0)
    signal = ema(smi, signal_len)

    return smi, signal


# ===========================================================================
# STRATEGY CLASS
# ===========================================================================
class RenkoSMIIOCrossV3Strategy(BaseStrategy):
    """
    TEST VARIANT (S4V3) of RenkoSMIIOSupertrendStrategy (S4).

    ONLY CHANGE: trade decision = SMIIO/Signal crossover alone.
    Renko brick direction and Supertrend are NOT used for entry/exit.
    BUY_A/BUY_B/SELL_A/SELL_B confirmation logic is removed.

    LONG  Entry = SMIIO crosses ABOVE Signal
    LONG  Exit  = SMIIO crosses BELOW Signal
    SHORT Entry = SMIIO crosses BELOW Signal
    SHORT Exit  = SMIIO crosses ABOVE Signal

    No same-bar exit -> new entry (same protection as original S4).
    """

    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        super().__init__(data_dict=data_dict, lot_size=lot_size)

        # --- Core strategy parameters (identical source/meaning as original S4) ---
        self.renko_box_pct   = kwargs.get('renko_box_pct', 0.001)
        self.reference_price = kwargs.get('reference_price', None)
        self.renko_timeframe = kwargs.get('renko_timeframe', '2h')
        self.smiio_shortlen  = kwargs.get('smiio_shortlen', 10)
        self.smiio_longlen   = kwargs.get('smiio_longlen',  20)
        self.smiio_siglen    = kwargs.get('smiio_siglen',   3)
        self.slippage_usd    = kwargs.get('slippage_usd',   0.0)
        self.commission_pct  = kwargs.get('commission_pct', 0.0)

    # -----------------------------------------------------------------------
    @property
    def optimization_params(self) -> dict:
        return {
            'renko_box_pct':  {'default': 0.0020, 'min': 0.0010, 'max': 0.0040, 'step': 0.0005},
            'smiio_shortlen': {'default': 10,   'min': 3,    'max': 20,   'step': 1},
            'smiio_longlen':  {'default': 20,   'min': 10,   'max': 40,   'step': 5},
            'smiio_siglen':   {'default': 3,    'min': 2,    'max': 9,    'step': 1},
        }

    @property
    def required_timeframes(self) -> list:
        return [self.renko_timeframe]

    # -----------------------------------------------------------------------
    def _apply_slippage(self, price: float, direction: str, is_entry: bool) -> float:
        slip = self.slippage_usd
        if direction == 'long':
            return price + slip if is_entry else price - slip
        else:
            return price - slip if is_entry else price + slip

    # -----------------------------------------------------------------------
    # Renko DataFrame builder - IDENTICAL to original S4
    # -----------------------------------------------------------------------
    def _build_renko_df(self) -> pd.DataFrame:
        tf = self.renko_timeframe
        df_tf = self._data.get(tf)
        if df_tf is None or len(df_tf) == 0:
            raise ValueError(f"Requires '{tf}' timeframe data")

        closes = df_tf['close'].values
        timestamps = (df_tf.index if isinstance(df_tf.index, pd.DatetimeIndex)
                      else pd.to_datetime(df_tf['timestamp']))

        _anchor = self.reference_price if self.reference_price else closes[0]
        box_size = max(1, round(_anchor * self.renko_box_pct))
        builder = RenkoBuilder(box_size=box_size, reference_price=_anchor)
        renko_raw = builder.build(closes)
        if renko_raw is None or len(renko_raw) == 0:
            raise ValueError("RenkoBuilder produced no bricks")

        _ts_values = timestamps.values if hasattr(timestamps, 'values') else np.asarray(timestamps)
        _idx_arr = renko_raw['bar_index'].values.copy()
        _max_idx = len(_ts_values) - 1
        _idx_arr[_idx_arr > _max_idx] = _max_idx
        renko_raw['timestamp'] = _ts_values[_idx_arr]
        renko_raw['real_close'] = closes[_idx_arr]
        return renko_raw

    # -----------------------------------------------------------------------
    # generate_signals - MAIN LOGIC (SMIIO CROSSOVER ONLY)
    # -----------------------------------------------------------------------
    def generate_signals(self) -> list:
        df = self._build_renko_df()
        timestamps = df['timestamp'].values
        n = len(df)

        closes = df['renko_close'].values
        real_closes = df['real_close'].values
        box = max(1, round((self.reference_price if self.reference_price else closes[0]) * self.renko_box_pct))

        # --- SMIIO (identical calc/params to original S4) ---
        smi, sig = compute_smiio(
            closes,
            short_len=self.smiio_shortlen,
            long_len=self.smiio_longlen,
            signal_len=self.smiio_siglen,
        )

        signals = []
        current_direction = None

        _ts_strings = [pd.Timestamp(t).strftime('%Y-%m-%dT%H:%M:%S') for t in timestamps]
        for i in range(1, n):
            ts    = _ts_strings[i]
            close = closes[i]

            smi_cross_up   = smi[i] > sig[i] and smi[i - 1] <= sig[i - 1]
            smi_cross_down = smi[i] < sig[i] and smi[i - 1] >= sig[i - 1]

            just_exited = False

            # ----------------------------------------------------------
            # EXIT: pure SMIIO/Signal crossover only
            # ----------------------------------------------------------
            if current_direction == 'long' and smi_cross_down:
                signals.append({
                    'signal_type': 'EXIT',
                    'price':       self._apply_slippage(real_closes[i], 'long', False),
                    'timestamp':   ts,
                    'sl_price':    close - box,
                    'entry_type':  '',
                    'exit_type':   'SMIIO_CROSS_DOWN',
                    'direction':   'long',
                })
                current_direction = None
                just_exited = True

            elif current_direction == 'short' and smi_cross_up:
                signals.append({
                    'signal_type': 'EXIT',
                    'price':       self._apply_slippage(real_closes[i], 'short', False),
                    'timestamp':   ts,
                    'sl_price':    close + box,
                    'entry_type':  '',
                    'exit_type':   'SMIIO_CROSS_UP',
                    'direction':   'short',
                })
                current_direction = None
                just_exited = True

            # ----------------------------------------------------------
            # ENTRY: pure SMIIO/Signal crossover only
            # No same-bar exit -> new entry (skip if we just exited this bar)
            # ----------------------------------------------------------
            if current_direction is None and not just_exited:
                if smi_cross_up:
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price':       self._apply_slippage(real_closes[i], 'long', True),
                        'timestamp':   ts,
                        'sl_price':    close - box * 2,
                        'entry_type':  'SMIIO_CROSS_UP',
                        'exit_type':   '',
                        'direction':   'long',
                    })
                    current_direction = 'long'

                elif smi_cross_down:
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price':       self._apply_slippage(real_closes[i], 'short', True),
                        'timestamp':   ts,
                        'sl_price':    close + box * 2,
                        'entry_type':  'SMIIO_CROSS_DOWN',
                        'exit_type':   '',
                        'direction':   'short',
                    })
                    current_direction = 'short'

        return signals
```

## POST-FIX BACKTEST RESULT - S4 BTCUSD (report: output/backtest_report_RenkoSMIIOSupertrendStrategy_BTCUSD_20261010_074702.html)
Total Trades: 4126 | Winning: 1037 | Losing: 3089 | Win Rate: 25.13% | Loss Rate: 74.87%
Profit Factor: 0.51 | Total PnL: -8,519,147.20 INR | Expectancy: -2,064.75 INR
Avg Profit/Win: 7,682.24 INR | Avg Loss/Loss: -5,078.98 INR
Max Profit/Trade: 54,340.44 INR | Max Loss/Trade: -43,011.36 INR
Max Drawdown: -101.96% (-8,564,737.44 INR) over 980 days (2024-02-02 to 2026-10-09)
Return/MaxDD: 0.99 | Reward:Risk: 1.51 | Sharpe Ratio: -3.87
Max Win Streak: 6 | Max Loss Streak: 25 | Avg Trade Duration: 0.24 days

## STATUS
Both bugs confirmed fixed and verified live in code used for this backtest (see grep proof above).
Post-fix backtest on S4/BTCUSD is deep-negative (not a bug - previous positive-looking results were from phantom bricks + stale fill prices).
S4V2 and S4V3 share the same fixed files - pending their own backtest runs for full validation.
