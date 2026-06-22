# engine/signal_executor.py
# Responsibility: Detect BUY_A, BUY_B, SELL_A, SELL_B signals from live Renko+Supertrend data
# Mirrors validate_trades.py signal logic exactly

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SignalState:
    """Tracks all signal generation state across bars."""

    # Trendline anchors
    swing_highs:        list = field(default_factory=list)   # (box_idx, price)
    swing_lows:         list = field(default_factory=list)   # (box_idx, price)

    # Horizontal levels
    last_swing_high:    float = np.nan
    last_swing_low:     float = np.nan
    swing_high_age:     int   = 0
    swing_low_age:      int   = 0

    # Cooldown counters
    buy_b_cooldown:     int   = 0
    sell_b_cooldown:    int   = 0

    # Level consumption flags
    buy_b_level_active: bool  = False
    sell_b_level_active:bool  = False

    # Previous bar signal flags (for rising-edge detection)
    prev_buy_a:         bool  = False
    prev_buy_b:         bool  = False
    prev_sell_a:        bool  = False
    prev_sell_b:        bool  = False

    # Supertrend previous value
    prev_st_bull:       Optional[bool] = None


class SignalExecutor:
    """
    Detects trading signals from a rolling window of Renko boxes.

    Signal types
    ------------
    BUY_A  : Trendline break upward (descending resistance broken)
    BUY_B  : Horizontal swing-high break upward
    SELL_A : Trendline break downward (ascending support broken)
    SELL_B : Horizontal swing-low break downward

    Parameters
    ----------
    swing_l         : int   Left bars for pivot detection (default 2)
    swing_r         : int   Right bars for pivot detection (default 2)
    sr_tolerance    : float Price tolerance for trendline touch (default 1.0)
    min_age_horiz   : int   Minimum box age for horizontal levels (default 30)
    cooldown_boxes  : int   Cooldown between B-type signals (default 20)
    anchor_lookback : int   Max boxes back for trendline anchor (default 50)
    """

    def __init__(
        self,
        swing_l:         int   = 2,
        swing_r:         int   = 2,
        sr_tolerance:    float = 1.0,
        min_age_horiz:   int   = 30,
        cooldown_boxes:  int   = 20,
        anchor_lookback: int   = 50
    ):
        self.swing_l         = swing_l
        self.swing_r         = swing_r
        self.sr_tolerance    = sr_tolerance
        self.min_age_horiz   = min_age_horiz
        self.cooldown_boxes  = cooldown_boxes
        self.anchor_lookback = anchor_lookback
        self.state           = SignalState()

    def reset(self):
        """Reset all state (call when restarting live loop)."""
        self.state = SignalState()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def update(self, renko_boxes: pd.DataFrame, st_bull_series: pd.Series) -> dict:
        """
        Process the latest closed Renko box and return any new signals.

        Parameters
        ----------
        renko_boxes   : DataFrame with columns [renko_open, renko_high, renko_low,
                        renko_close, renko_dir, box_idx]
                        Last row = most recently CLOSED box
        st_bull_series: Boolean Series aligned to renko_boxes
                        True = bullish ST (st_dir == -1)

        Returns
        -------
        dict: {
            "BUY_A":       bool,
            "BUY_B":       bool,
            "SELL_A":      bool,
            "SELL_B":      bool,
            "st_flip_bull": bool,
            "st_flip_bear": bool
        }
        """
        signals = {
            "BUY_A":        False,
            "BUY_B":        False,
            "SELL_A":       False,
            "SELL_B":       False,
            "st_flip_bull": False,
            "st_flip_bear": False
        }

        n = len(renko_boxes)
        min_bars = self.swing_l + self.swing_r + 1
        if n < min_bars:
            return signals

        # Use renko_close, renko_high, renko_low columns
        closes  = renko_boxes["renko_close"].values
        highs   = renko_boxes["renko_high"].values
        lows    = renko_boxes["renko_low"].values
        cur_idx = n - 1

        st_bull = st_bull_series.iloc[-1]

        # --- Supertrend flip detection ---
        if self.state.prev_st_bull is not None:
            if not self.state.prev_st_bull and st_bull:
                signals["st_flip_bull"] = True
            elif self.state.prev_st_bull and not st_bull:
                signals["st_flip_bear"] = True
        self.state.prev_st_bull = st_bull

        # --- Update swing pivots ---
        self._update_swings(renko_boxes, cur_idx)

        # --- Increment ages and cooldowns ---
        self.state.swing_high_age  += 1
        self.state.swing_low_age   += 1
        if self.state.buy_b_cooldown  > 0: self.state.buy_b_cooldown  -= 1
        if self.state.sell_b_cooldown > 0: self.state.sell_b_cooldown -= 1

        cur_close = closes[cur_idx]

        # --- BUY_A: descending trendline break ---
        raw_buy_a  = self._check_trendline_break(
            renko_boxes, cur_idx, direction="up"
        )
        buy_a_edge = raw_buy_a and not self.state.prev_buy_a
        if buy_a_edge:
            signals["BUY_A"] = True

        # --- SELL_A: ascending trendline break ---
        raw_sell_a  = self._check_trendline_break(
            renko_boxes, cur_idx, direction="down"
        )
        sell_a_edge = raw_sell_a and not self.state.prev_sell_a
        if sell_a_edge:
            signals["SELL_A"] = True

        # --- BUY_B: horizontal swing-high break ---
        raw_buy_b = False
        if (
            not np.isnan(self.state.last_swing_high)
            and self.state.swing_high_age >= self.min_age_horiz
            and self.state.buy_b_cooldown == 0
            and self.state.buy_b_level_active
        ):
            if cur_close > self.state.last_swing_high:
                raw_buy_b = True

        buy_b_edge = raw_buy_b and not self.state.prev_buy_b
        if buy_b_edge:
            signals["BUY_B"] = True
            self.state.buy_b_cooldown     = self.cooldown_boxes
            self.state.buy_b_level_active = False   # consume level

        # --- SELL_B: horizontal swing-low break ---
        raw_sell_b = False
        if (
            not np.isnan(self.state.last_swing_low)
            and self.state.swing_low_age >= self.min_age_horiz
            and self.state.sell_b_cooldown == 0
            and self.state.sell_b_level_active
        ):
            if cur_close < self.state.last_swing_low:
                raw_sell_b = True

        sell_b_edge = raw_sell_b and not self.state.prev_sell_b
        if sell_b_edge:
            signals["SELL_B"] = True
            self.state.sell_b_cooldown     = self.cooldown_boxes
            self.state.sell_b_level_active = False  # consume level

        # --- Store previous flags for next bar rising-edge detection ---
        self.state.prev_buy_a  = raw_buy_a
        self.state.prev_buy_b  = raw_buy_b
        self.state.prev_sell_a = raw_sell_a
        self.state.prev_sell_b = raw_sell_b

        return signals

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_swings(self, boxes: pd.DataFrame, cur_idx: int):
        """Detect new pivot highs/lows and update horizontal levels."""
        L = self.swing_l
        R = self.swing_r
        pivot_idx = cur_idx - R   # pivot candidate is R bars back

        if pivot_idx < L:
            return

        highs = boxes["renko_high"].values
        lows  = boxes["renko_low"].values

        pivot_high = highs[pivot_idx]
        pivot_low  = lows[pivot_idx]

        # Check strict pivot high
        left_highs  = highs[pivot_idx - L : pivot_idx]
        right_highs = highs[pivot_idx + 1 : pivot_idx + R + 1]
        if (
            len(left_highs)  == L
            and len(right_highs) == R
            and all(pivot_high > h for h in left_highs)
            and all(pivot_high > h for h in right_highs)
        ):
            self.state.swing_highs.append((pivot_idx, pivot_high))
            self.state.last_swing_high    = pivot_high
            self.state.swing_high_age     = R
            self.state.buy_b_level_active = True

        # Check strict pivot low
        left_lows  = lows[pivot_idx - L : pivot_idx]
        right_lows = lows[pivot_idx + 1 : pivot_idx + R + 1]
        if (
            len(left_lows)  == L
            and len(right_lows) == R
            and all(pivot_low < l for l in left_lows)
            and all(pivot_low < l for l in right_lows)
        ):
            self.state.swing_lows.append((pivot_idx, pivot_low))
            self.state.last_swing_low      = pivot_low
            self.state.swing_low_age       = R
            self.state.sell_b_level_active = True

    def _check_trendline_break(
        self, boxes: pd.DataFrame, cur_idx: int, direction: str
    ) -> bool:
        """
        Check if current close breaks a trendline.

        direction="up"   -> descending resistance trendline (BUY_A)
        direction="down" -> ascending support trendline (SELL_A)
        """
        closes    = boxes["renko_close"].values
        cur_close = closes[cur_idx]

        lookback_start = max(0, cur_idx - self.anchor_lookback)

        if direction == "up":
            # Find two recent swing highs to form descending resistance
            pivots = [
                (idx, price)
                for (idx, price) in self.state.swing_highs
                if lookback_start <= idx < cur_idx
            ]
            if len(pivots) < 2:
                return False
            p1, p2 = pivots[-2], pivots[-1]
            if p2[0] == p1[0]:
                return False
            slope = (p2[1] - p1[1]) / (p2[0] - p1[0])
            if slope >= 0:
                return False   # not descending
            trendline_val = p2[1] + slope * (cur_idx - p2[0])
            return cur_close > trendline_val - self.sr_tolerance

        else:  # direction == "down"
            # Find two recent swing lows to form ascending support
            pivots = [
                (idx, price)
                for (idx, price) in self.state.swing_lows
                if lookback_start <= idx < cur_idx
            ]
            if len(pivots) < 2:
                return False
            p1, p2 = pivots[-2], pivots[-1]
            if p2[0] == p1[0]:
                return False
            slope = (p2[1] - p1[1]) / (p2[0] - p1[0])
            if slope <= 0:
                return False   # not ascending
            trendline_val = p2[1] + slope * (cur_idx - p2[0])
            return cur_close < trendline_val + self.sr_tolerance
