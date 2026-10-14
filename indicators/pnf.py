"""
Point and Figure (PnF) Chart Builder
Builds PnF charts from 1H OHLCV data
Calculates SMA10, SMA20, ADX, and detects patterns
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional


class PnFChartBuilder:
    """
    Builds Point and Figure (PnF) charts from 1H OHLCV data.

    Features:
    - Dynamic box size (0.15% of current price)
    - 3-box reversal
    - SMA10, SMA20 on column end levels
    - ADX calculation on column High/Low/Close
    - Pattern detection (Double Top, Double Bottom, Trendlines)
    """

    def __init__(self, box_size_percent=0.15, reverse_boxes=3):
        """
        Initialize PnF builder

        Args:
            box_size_percent: Box size as % of price (default 0.15%)
            reverse_boxes: Reversal threshold in boxes (default 3)
        """
        self.box_size_percent = box_size_percent
        self.reverse_boxes = reverse_boxes
        self.columns = []
        self.current_column = None
        self.current_box_size = None

    def build_pnf_chart(self, df: pd.DataFrame) -> List[Dict]:
        """
        Build complete PnF chart from ALL 1H candles.

        IMPORTANT: This processes ALL historical data at once.
        Not candle-by-candle.

        Args:
            df: DataFrame with columns ['open', 'high', 'low', 'close', 'volume']
                Index must be datetime

        Returns:
            List of completed PnF columns with structure:
            {
                'type': 'X' or 'O',
                'start_level': float,
                'end_level': float,
                'start_timestamp': datetime,
                'end_timestamp': datetime,
                'boxes': int,
                'high': float,
                'low': float
            }
        """
        # Normalize column names to lowercase
        df = df.copy()
        df.columns = df.columns.str.lower()

        self.columns = []
        self.current_column = None
        self.current_box_size = None

        # Process ALL candles in order
        for idx, row in df.iterrows():
            close_price = float(row['close'])
            timestamp = idx  # datetime index

            # Initialize first column with first candle
            if self.current_column is None:
                self.current_box_size = close_price * (self.box_size_percent / 100)
                self.current_column = {
                    'type': 'X',  # Start with X column (up)
                    'start_level': close_price,
                    'end_level': close_price,
                    'start_timestamp': timestamp,
                    'end_timestamp': timestamp,
                    'boxes': 0
                }
                continue

            # Recalculate box size dynamically for each candle
            self.current_box_size = close_price * (self.box_size_percent / 100)

            # Calculate how many boxes price moved
            boxes_moved = (close_price - self.current_column['end_level']) / self.current_box_size

            # Process based on current column type
            if self.current_column['type'] == 'X':  # X column (uptrend)
                if boxes_moved >= 1:
                    # Price moved up by 1+ box: add to X column
                    self.current_column['end_level'] = close_price
                    self.current_column['end_timestamp'] = timestamp
                    self.current_column['boxes'] += 1

                elif boxes_moved <= -self.reverse_boxes:
                    # Price moved down by 3+ boxes: reversal
                    # Save reference BEFORE completing, in case complete does nothing
                    prev_end_level = self.current_column['end_level']
                    prev_end_timestamp = self.current_column['end_timestamp']

                    self._complete_column()

                    # Use last completed column if available, else fall back to saved ref
                    if self.columns:
                        ref_end_level = self.columns[-1]['end_level']
                        ref_end_timestamp = self.columns[-1]['end_timestamp']
                    else:
                        ref_end_level = prev_end_level
                        ref_end_timestamp = prev_end_timestamp

                    self.current_column = {
                        'type': 'O',
                        'start_level': ref_end_level,
                        'end_level': close_price,
                        'start_timestamp': ref_end_timestamp,
                        'end_timestamp': timestamp,
                        'boxes': abs(int(boxes_moved))
                    }

            elif self.current_column['type'] == 'O':  # O column (downtrend)
                if boxes_moved <= -1:
                    # Price moved down by 1+ box: add to O column
                    self.current_column['end_level'] = close_price
                    self.current_column['end_timestamp'] = timestamp
                    self.current_column['boxes'] += 1

                elif boxes_moved >= self.reverse_boxes:
                    # Price moved up by 3+ boxes: reversal
                    # Save reference BEFORE completing, in case complete does nothing
                    prev_end_level = self.current_column['end_level']
                    prev_end_timestamp = self.current_column['end_timestamp']

                    self._complete_column()

                    # Use last completed column if available, else fall back to saved ref
                    if self.columns:
                        ref_end_level = self.columns[-1]['end_level']
                        ref_end_timestamp = self.columns[-1]['end_timestamp']
                    else:
                        ref_end_level = prev_end_level
                        ref_end_timestamp = prev_end_timestamp

                    self.current_column = {
                        'type': 'X',
                        'start_level': ref_end_level,
                        'end_level': close_price,
                        'start_timestamp': ref_end_timestamp,
                        'end_timestamp': timestamp,
                        'boxes': int(boxes_moved)
                    }

        # Complete last column if it has boxes
        if self.current_column is not None and self.current_column['boxes'] > 0:
            self._complete_column()

        return self.columns

    def _complete_column(self):
        """Complete current column and add to columns list."""
        if self.current_column is None or self.current_column['boxes'] == 0:
            return

        col = self.current_column.copy()
        col['high'] = max(col['start_level'], col['end_level'])
        col['low'] = min(col['start_level'], col['end_level'])
        self.columns.append(col)

    def calculate_sma(self, period: int) -> List[Optional[float]]:
        """
        Calculate SMA on PnF column end_levels.

        Args:
            period: SMA period (10 or 20)

        Returns:
            List of SMA values (None for first period-1 columns)
        """
        if len(self.columns) < period:
            return [None] * len(self.columns)

        sma_values = [None] * (period - 1)
        end_levels = [col['end_level'] for col in self.columns]

        for i in range(period - 1, len(end_levels)):
            sma = np.mean(end_levels[i - period + 1:i + 1])
            sma_values.append(sma)

        return sma_values

    def calculate_adx(self, period: int = 14) -> List[Optional[float]]:
        """
        Calculate ADX on PnF columns using Pine Script formula.

        Formula:
        - TrueRange = max(high-low, abs(high-prev_close), abs(low-prev_close))
        - DirectionalMovementPlus = high-prev_high if > prev_low-low else 0
        - DirectionalMovementMinus = prev_low-low if > high-prev_high else 0
        - 14-period smoothing applied
        - ADX = SMA(DX, 14)

        Args:
            period: ADX period (default 14)

        Returns:
            List of ADX values (None for first 14 columns)
        """
        if len(self.columns) < 2:
            return [None] * len(self.columns)

        # Step 1: Calculate True Range and Directional Movements
        tr_list = []
        dm_plus_list = []
        dm_minus_list = []

        for i in range(len(self.columns)):
            col = self.columns[i]

            if i == 0:
                # First column
                tr = col['high'] - col['low']
                dm_plus = 0
                dm_minus = 0
            else:
                prev_col = self.columns[i - 1]

                # True Range
                tr = max(
                    col['high'] - col['low'],
                    abs(col['high'] - prev_col['end_level']),
                    abs(col['low'] - prev_col['end_level'])
                )

                # Directional Movements
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

    def detect_double_top(self, columns_slice: List[Dict]) -> Tuple[bool, int]:
        """
        Standard PnF Double Top Breakout.
        Fires when current X top (end_level) > previous X top (end_level).
        No box size threshold applied.
        """
        x_columns = [(i, col) for i, col in enumerate(columns_slice) if col['type'] == 'X']
        if len(x_columns) < 2:
            return False, -1
        first_x_idx, first_x = x_columns[-2]
        second_x_idx, second_x = x_columns[-1]
        if second_x['end_level'] > first_x['end_level']:
            return True, second_x_idx
        return False, -1

    def detect_double_bottom(self, columns_slice: List[Dict]) -> Tuple[bool, int]:
        """
        Standard PnF Double Bottom Breakdown.
        Fires when current O bottom (end_level) < previous O bottom (end_level).
        No box size threshold applied.
        """
        o_columns = [(i, col) for i, col in enumerate(columns_slice) if col['type'] == 'O']
        if len(o_columns) < 2:
            return False, -1
        first_o_idx, first_o = o_columns[-2]
        second_o_idx, second_o = o_columns[-1]
        if second_o['end_level'] < first_o['end_level']:
            return True, second_o_idx
        return False, -1

    def detect_bearish_trendline(self, columns_slice: List[Dict]) -> bool:
        o_columns = [col for col in columns_slice if col['type'] == 'O']
        if len(o_columns) < 2:
            return False
        return o_columns[-1]['end_level'] >= o_columns[-2]['end_level']

    def detect_bullish_trendline(self, columns_slice: List[Dict]) -> bool:
        x_columns = [col for col in columns_slice if col['type'] == 'X']
        if len(x_columns) < 2:
            return False
        return x_columns[-1]['end_level'] <= x_columns[-2]['end_level']

    def detect_lower_low(self, columns_slice: List[Dict]) -> bool:
        o_columns = [col for col in columns_slice if col['type'] == 'O']
        if len(o_columns) < 2:
            return False
        return o_columns[-1]['end_level'] < o_columns[-2]['end_level']

    def detect_higher_high(self, columns_slice: List[Dict]) -> bool:
        x_columns = [col for col in columns_slice if col['type'] == 'X']
        if len(x_columns) < 2:
            return False
        return x_columns[-1]['end_level'] > x_columns[-2]['end_level']

    def get_swing_low(self, columns_slice: List[Dict], lookback: int = 5) -> float:
        if len(columns_slice) < lookback:
            return min([col['low'] for col in columns_slice])
        recent_cols = columns_slice[-lookback:]
        return min([col['low'] for col in recent_cols])

    def get_swing_high(self, columns_slice: List[Dict], lookback: int = 5) -> float:
        if len(columns_slice) < lookback:
            return max([col['high'] for col in columns_slice])
        recent_cols = columns_slice[-lookback:]
        return max([col['high'] for col in recent_cols])
