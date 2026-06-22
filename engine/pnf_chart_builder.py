import pandas as pd
import numpy as np
from typing import List, Dict, Tuple


class PnFChartBuilder:
    """
    Builds Point and Figure (PnF) charts from 1H OHLCV data.
    Calculates SMA10, SMA20, ADX, and detects patterns.
    """

    def __init__(self, box_size_percent=0.15, reverse_boxes=3):
        self.box_size_percent = box_size_percent
        self.reverse_boxes = reverse_boxes
        self.columns = []
        self.current_column = None
        self.current_box_size = None

    def build_pnf_chart(self, df: pd.DataFrame) -> List[Dict]:
        """
        Build PnF chart from 1H close prices.

        Args:
            df: DataFrame with OHLCV data (must have 'close' column)

        Returns:
            List of completed PnF columns
        """
        self.columns = []
        self.current_column = None
        self.current_box_size = None

        for idx, row in df.iterrows():
            close_price = float(row['close'])
            timestamp = row.name if hasattr(row.name, 'timestamp') else idx

            # Initialize first column
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

            # Recalculate box size dynamically
            self.current_box_size = close_price * (self.box_size_percent / 100)

            # Calculate boxes moved
            boxes_moved = (close_price - self.current_column['end_level']) / self.current_box_size

            # Process based on current column type
            if self.current_column['type'] == 'X':  # X column (up)
                if boxes_moved >= 1:
                    # Add box to X column
                    self.current_column['end_level'] = close_price
                    self.current_column['end_timestamp'] = timestamp
                    self.current_column['boxes'] += 1

                elif boxes_moved <= -self.reverse_boxes:
                    # Reversal: complete X column and start O column
                    self._complete_column()
                    self.current_column = {
                        'type': 'O',
                        'start_level': self.columns[-1]['end_level'],
                        'end_level': close_price,
                        'start_timestamp': self.columns[-1]['end_timestamp'],
                        'end_timestamp': timestamp,
                        'boxes': abs(int(boxes_moved))
                    }

            elif self.current_column['type'] == 'O':  # O column (down)
                if boxes_moved <= -1:
                    # Add box to O column
                    self.current_column['end_level'] = close_price
                    self.current_column['end_timestamp'] = timestamp
                    self.current_column['boxes'] += 1

                elif boxes_moved >= self.reverse_boxes:
                    # Reversal: complete O column and start X column
                    self._complete_column()
                    self.current_column = {
                        'type': 'X',
                        'start_level': self.columns[-1]['end_level'],
                        'end_level': close_price,
                        'start_timestamp': self.columns[-1]['end_timestamp'],
                        'end_timestamp': timestamp,
                        'boxes': int(boxes_moved)
                    }

        # Complete last column if exists
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

    def calculate_sma(self, period: int) -> List[float]:
        """Calculate SMA on PnF column end_levels."""
        if len(self.columns) < period:
            return [None] * len(self.columns)

        sma_values = [None] * (period - 1)
        end_levels = [col['end_level'] for col in self.columns]

        for i in range(period - 1, len(end_levels)):
            sma = np.mean(end_levels[i - period + 1:i + 1])
            sma_values.append(sma)

        return sma_values

    def calculate_adx(self, period: int = 14) -> List[float]:
        """
        Calculate ADX on PnF columns using Pine Script formula.

        Returns:
            List of ADX values (None for first 14 columns)
        """
        if len(self.columns) < 2:
            return [None] * len(self.columns)

        # Calculate True Range and Directional Movements
        tr_list = []
        dm_plus_list = []
        dm_minus_list = []

        for i in range(len(self.columns)):
            col = self.columns[i]

            if i == 0:
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

        # Smoothing (14-period)
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

        # Calculate DI+ and DI-
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

        # Calculate ADX (SMA of DX)
        adx_values = [None] * (period - 1)
        for i in range(period - 1, len(dx_list)):
            adx = np.mean(dx_list[i - period + 1:i + 1])
            adx_values.append(adx)

        return adx_values

    def detect_double_top(self) -> Tuple[bool, int]:
        """
        Detect Double Top pattern (4A entry signal).
        Second X breaks ABOVE first X by at least 1 box.

        Returns:
            (pattern_detected, column_index)
        """
        x_columns = [(i, col) for i, col in enumerate(self.columns) if col['type'] == 'X']

        if len(x_columns) < 2:
            return False, -1

        # Check last two X columns
        first_x_idx, first_x = x_columns[-2]
        second_x_idx, second_x = x_columns[-1]

        # Second X must break above first X by at least 1 box
        box_size = second_x['end_level'] * (self.box_size_percent / 100)
        if second_x['end_level'] > first_x['end_level'] + box_size:
            return True, second_x_idx

        return False, -1

    def detect_double_bottom(self) -> Tuple[bool, int]:
        """
        Detect Double Bottom pattern (4B entry signal).
        Second O breaks BELOW first O by at least 1 box.

        Returns:
            (pattern_detected, column_index)
        """
        o_columns = [(i, col) for i, col in enumerate(self.columns) if col['type'] == 'O']

        if len(o_columns) < 2:
            return False, -1

        # Check last two O columns
        first_o_idx, first_o = o_columns[-2]
        second_o_idx, second_o = o_columns[-1]

        # Second O must break below first O by at least 1 box
        box_size = second_o['end_level'] * (self.box_size_percent / 100)
        if second_o['end_level'] < first_o['end_level'] - box_size:
            return True, second_o_idx

        return False, -1

    def detect_bearish_trendline(self) -> bool:
        """
        Detect Bearish Trendline (4A entry signal).
        Descending O sequence breaks (new O >= previous O).

        Returns:
            True if trendline breaks
        """
        o_columns = [col for col in self.columns if col['type'] == 'O']

        if len(o_columns) < 2:
            return False

        # Check if last O breaks the descending sequence
        if o_columns[-1]['end_level'] >= o_columns[-2]['end_level']:
            return True

        return False

    def detect_bullish_trendline(self) -> bool:
        """
        Detect Bullish Trendline (4B entry signal).
        Ascending X sequence breaks (new X <= previous X).

        Returns:
            True if trendline breaks
        """
        x_columns = [col for col in self.columns if col['type'] == 'X']

        if len(x_columns) < 2:
            return False

        # Check if last X breaks the ascending sequence
        if x_columns[-1]['end_level'] <= x_columns[-2]['end_level']:
            return True

        return False

    def detect_lower_low(self) -> bool:
        """
        Detect Lower Low (4A entry signal).
        Current O < previous O.

        Returns:
            True if lower low detected
        """
        o_columns = [col for col in self.columns if col['type'] == 'O']

        if len(o_columns) < 2:
            return False

        return o_columns[-1]['end_level'] < o_columns[-2]['end_level']

    def detect_higher_high(self) -> bool:
        """
        Detect Higher High (4B entry signal).
        Current X > previous X.

        Returns:
            True if higher high detected
        """
        x_columns = [col for col in self.columns if col['type'] == 'X']

        if len(x_columns) < 2:
            return False

        return x_columns[-1]['end_level'] > x_columns[-2]['end_level']

    def get_swing_low(self, lookback: int = 5) -> float:
        """Get lowest low from last N boxes before entry."""
        if len(self.columns) < lookback:
            return min([col['low'] for col in self.columns])

        recent_cols = self.columns[-lookback:]
        return min([col['low'] for col in recent_cols])

    def get_swing_high(self, lookback: int = 5) -> float:
        """Get highest high from last N boxes before entry."""
        if len(self.columns) < lookback:
            return max([col['high'] for col in self.columns])

        recent_cols = self.columns[-lookback:]
        return max([col['high'] for col in recent_cols])
