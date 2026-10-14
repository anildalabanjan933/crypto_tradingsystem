"""
PnF-Based Indicators
All calculations on PnF columns ONLY (not candlesticks)
Compatible with existing backtest engine
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple


class PnFIndicators:
    """
    Calculate all indicators on PnF columns.
    - SMA10, SMA20 on column end_levels
    - ADX on column High/Low/Close
    - Trendlines, Patterns on column sequences
    """

    def __init__(self, box_size_percent: float = 0.15):
        self.box_size_percent = box_size_percent

    # ==================== SMA CALCULATIONS ====================

    def calculate_sma10(self, columns: List[Dict]) -> List[Optional[float]]:
        """
        SMA10 on PnF column end_levels.

        Args:
            columns: List of completed PnF columns

        Returns:
            List of SMA10 values (None for first 9 columns)
        """
        if len(columns) < 10:
            return [None] * len(columns)

        sma_values = [None] * 9
        end_levels = [col['end_level'] for col in columns]

        for i in range(9, len(end_levels)):
            sma = np.mean(end_levels[i - 9:i + 1])
            sma_values.append(sma)

        return sma_values

    def calculate_sma20(self, columns: List[Dict]) -> List[Optional[float]]:
        """
        SMA20 on PnF column end_levels.

        Args:
            columns: List of completed PnF columns

        Returns:
            List of SMA20 values (None for first 19 columns)
        """
        if len(columns) < 20:
            return [None] * len(columns)

        sma_values = [None] * 19
        end_levels = [col['end_level'] for col in columns]

        for i in range(19, len(end_levels)):
            sma = np.mean(end_levels[i - 19:i + 1])
            sma_values.append(sma)

        return sma_values

    # ==================== ADX CALCULATION (Pine Script Formula) ====================

    def calculate_adx(self, columns: List[Dict], period: int = 14) -> List[Optional[float]]:
        """
        ADX on PnF columns using Pine Script formula.

        TrueRange = max(high-low, abs(high-prev_close), abs(low-prev_close))
        DirectionalMovementPlus = high-prev_high if > prev_low-low else 0
        DirectionalMovementMinus = prev_low-low if > high-prev_high else 0
        14-period smoothing applied
        ADX = SMA(DX, 14)

        Args:
            columns: List of completed PnF columns
            period: ADX period (default 14)

        Returns:
            List of ADX values (None for first 13 columns)
        """
        if len(columns) < 2:
            return [None] * len(columns)

        # Step 1: Calculate True Range and Directional Movements
        tr_list = []
        dm_plus_list = []
        dm_minus_list = []

        for i in range(len(columns)):
            col = columns[i]

            if i == 0:
                # First column
                tr = col['high'] - col['low']
                dm_plus = 0
                dm_minus = 0
            else:
                prev_col = columns[i - 1]

                # True Range (Pine Script formula)
                tr = max(
                    col['high'] - col['low'],
                    abs(col['high'] - prev_col['end_level']),
                    abs(col['low'] - prev_col['end_level'])
                )

                # Directional Movements (Pine Script formula)
                up_move = col['high'] - prev_col['high']
                down_move = prev_col['low'] - col['low']

                dm_plus = max(up_move, 0) if up_move > down_move else 0
                dm_minus = max(down_move, 0) if down_move > up_move else 0

            tr_list.append(tr)
            dm_plus_list.append(dm_plus)
            dm_minus_list.append(dm_minus)

        # Step 2: Smoothing (14-period Wilder's smoothing)
        smoothed_tr = []
        smoothed_dm_plus = []
        smoothed_dm_minus = []

        for i in range(len(tr_list)):
            if i == 0:
                s_tr = tr_list[i]
                s_dm_plus = dm_plus_list[i]
                s_dm_minus = dm_minus_list[i]
            else:
                s_tr = smoothed_tr[i - 1] - (smoothed_tr[i - 1] / period) + tr_list[i]
                s_dm_plus = smoothed_dm_plus[i - 1] - (smoothed_dm_plus[i - 1] / period) + dm_plus_list[i]
                s_dm_minus = smoothed_dm_minus[i - 1] - (smoothed_dm_minus[i - 1] / period) + dm_minus_list[i]

            smoothed_tr.append(s_tr)
            smoothed_dm_plus.append(s_dm_plus)
            smoothed_dm_minus.append(s_dm_minus)

        # Step 3: Calculate DI+ and DI-
        di_plus_list = []
        di_minus_list = []
        dx_list = []

        for i in range(len(smoothed_tr)):
            if smoothed_tr[i] != 0:
                di_plus = (smoothed_dm_plus[i] / smoothed_tr[i]) * 100
                di_minus = (smoothed_dm_minus[i] / smoothed_tr[i]) * 100
            else:
                di_plus = 0
                di_minus = 0

            di_plus_list.append(di_plus)
            di_minus_list.append(di_minus)

            # Calculate DX
            di_sum = di_plus + di_minus
            if di_sum != 0:
                dx = abs(di_plus - di_minus) / di_sum * 100
            else:
                dx = 0
            dx_list.append(dx)

        # Step 4: Calculate ADX (SMA of DX)
        adx_values = [None] * (period - 1)
        for i in range(period - 1, len(dx_list)):
            adx = np.mean(dx_list[i - period + 1:i + 1])
            adx_values.append(adx)

        return adx_values

    # ==================== TRENDLINE DETECTION ====================

    def detect_bearish_trendline(self, columns: List[Dict]) -> bool:
        """
        Bearish Trendline (for Bullish 4A entry).

        Descending O sequence breaks when:
        New O >= Previous O

        Args:
            columns: List of completed PnF columns

        Returns:
            True if trendline breaks
        """
        o_columns = [col for col in columns if col['type'] == 'O']

        if len(o_columns) < 2:
            return False

        # Trendline breaks when new O >= previous O
        return o_columns[-1]['end_level'] >= o_columns[-2]['end_level']

    def detect_bullish_trendline(self, columns: List[Dict]) -> bool:
        """
        Bullish Trendline (for Bearish 4B entry).

        Ascending X sequence breaks when:
        New X <= Previous X

        Args:
            columns: List of completed PnF columns

        Returns:
            True if trendline breaks
        """
        x_columns = [col for col in columns if col['type'] == 'X']

        if len(x_columns) < 2:
            return False

        # Trendline breaks when new X <= previous X
        return x_columns[-1]['end_level'] <= x_columns[-2]['end_level']

    # ==================== HIGHER HIGH / LOWER LOW ====================

    def detect_higher_high(self, columns: List[Dict]) -> bool:
        """
        Higher High (for Bearish 4B entry).

        Current X > Previous X

        Args:
            columns: List of completed PnF columns

        Returns:
            True if higher high detected
        """
        x_columns = [col for col in columns if col['type'] == 'X']

        if len(x_columns) < 2:
            return False

        return x_columns[-1]['end_level'] > x_columns[-2]['end_level']

    def detect_lower_low(self, columns: List[Dict]) -> bool:
        """
        Lower Low (for Bullish 4A entry).

        Current O < Previous O

        Args:
            columns: List of completed PnF columns

        Returns:
            True if lower low detected
        """
        o_columns = [col for col in columns if col['type'] == 'O']

        if len(o_columns) < 2:
            return False

        return o_columns[-1]['end_level'] < o_columns[-2]['end_level']

    # ==================== PATTERN DETECTION ====================

    def detect_double_top(self, columns: List[Dict]) -> Tuple[bool, Optional[int]]:
        """
        Double Top Pattern (Bullish 4A entry).

        Pattern:
        1. First X column reaches level
        2. O column reversal (min 3 boxes)
        3. Second X column reaches SAME level as first X
        4. Second X breaks 1 box ABOVE first X
        5. Current column MUST be X type

        Args:
            columns: List of completed PnF columns

        Returns:
            (True/False, column_index of breakout)
        """
        # CRITICAL: Current column must be X type
        if not columns or columns[-1]['type'] != 'X':
            return False, None

        x_columns = [(i, col) for i, col in enumerate(columns) if col['type'] == 'X']

        if len(x_columns) < 2:
            return False, None

        # Get last two X columns
        first_x_idx, first_x = x_columns[-2]
        second_x_idx, second_x = x_columns[-1]

        # CRITICAL: Verify O reversal between X columns
        o_between = any(
            col['type'] == 'O'
            for col in columns[first_x_idx:second_x_idx]
        )
        if not o_between:
            return False, None

        # Calculate box size at second X level
        box_size = second_x['end_level'] * (self.box_size_percent / 100)

        # Check if second X breaks above first X by 1+ box
        if second_x['end_level'] > first_x['end_level'] + box_size:
            return True, second_x_idx

        return False, None

    def detect_double_bottom(self, columns: List[Dict]) -> Tuple[bool, Optional[int]]:
        """
        Double Bottom Pattern (Bearish 4B entry).

        Pattern:
        1. First O column reaches level
        2. X column reversal (min 3 boxes)
        3. Second O column reaches SAME level as first O
        4. Second O breaks 1 box BELOW first O
        5. Current column MUST be O type

        Args:
            columns: List of completed PnF columns

        Returns:
            (True/False, column_index of breakout)
        """
        # CRITICAL: Current column must be O type
        if not columns or columns[-1]['type'] != 'O':
            return False, None

        o_columns = [(i, col) for i, col in enumerate(columns) if col['type'] == 'O']

        if len(o_columns) < 2:
            return False, None

        # Get last two O columns
        first_o_idx, first_o = o_columns[-2]
        second_o_idx, second_o = o_columns[-1]

        # CRITICAL: Verify X reversal between O columns
        x_between = any(
            col['type'] == 'X'
            for col in columns[first_o_idx:second_o_idx]
        )
        if not x_between:
            return False, None

        # Calculate box size at second O level
        box_size = second_o['end_level'] * (self.box_size_percent / 100)

        # Check if second O breaks below first O by 1+ box
        if second_o['end_level'] < first_o['end_level'] - box_size:
            return True, second_o_idx

        return False, None

    # ==================== SWING HIGH/LOW ====================

    def get_swing_high(self, columns: List[Dict], lookback: int = 5) -> float:
        """
        Get highest high from last N PnF columns.

        Args:
            columns: List of completed PnF columns
            lookback: Number of columns to look back (default 5)

        Returns:
            Highest high value
        """
        if len(columns) == 0:
            return 0

        if len(columns) < lookback:
            recent_cols = columns
        else:
            recent_cols = columns[-lookback:]

        return max([col['high'] for col in recent_cols])

    def get_swing_low(self, columns: List[Dict], lookback: int = 5) -> float:
        """
        Get lowest low from last N PnF columns.

        Args:
            columns: List of completed PnF columns
            lookback: Number of columns to look back (default 5)

        Returns:
            Lowest low value
        """
        if len(columns) == 0:
            return 0

        if len(columns) < lookback:
            recent_cols = columns
        else:
            recent_cols = columns[-lookback:]

        return min([col['low'] for col in recent_cols])

    # ==================== SMA CHANNEL CHECK ====================

    def check_sma_channel(self, price: float, sma10: Optional[float],
                          sma20: Optional[float], channel_percent: float = 3.0) -> bool:
        """
        Check if price is within ±channel_percent of SMA10 or SMA20.

        Args:
            price: Current price
            sma10: SMA10 value (or None)
            sma20: SMA20 value (or None)
            channel_percent: Channel width in % (default 3%)

        Returns:
            True if price is in channel
        """
        if sma10 is not None:
            sma10_upper = sma10 * (1 + channel_percent / 100)
            sma10_lower = sma10 * (1 - channel_percent / 100)
            if sma10_lower <= price <= sma10_upper:
                return True

        if sma20 is not None:
            sma20_upper = sma20 * (1 + channel_percent / 100)
            sma20_lower = sma20 * (1 - channel_percent / 100)
            if sma20_lower <= price <= sma20_upper:
                return True

        return False

    # ==================== SMA TREND CHECK ====================

    def check_sma_trend(self, sma10: Optional[float], sma20: Optional[float]) -> bool:
        """
        Check if SMA10 > SMA20 (uptrend in SMA).

        Args:
            sma10: SMA10 value (or None)
            sma20: SMA20 value (or None)

        Returns:
            True if SMA10 > SMA20
        """
        if sma10 is None or sma20 is None:
            return False

        return sma10 > sma20
