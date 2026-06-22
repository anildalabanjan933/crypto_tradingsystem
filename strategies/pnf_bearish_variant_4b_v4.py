"""
PnF Bearish Variant 4B - V4 TEST VERSION
Change from V2: Removed trendline projection/slope/break/geometric logic.
Replaced with: Ascending O bottom pullback structure check (min 3 rising O bottoms).
All other logic identical to V2.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple

from strategies.base_strategy import BaseStrategy
from indicators.pnf import PnFChartBuilder
from indicators.supertrend import Supertrend


class PnFBearishVariant4BV4(BaseStrategy):

    def __init__(self, data_dict: Dict, lot_size: int = 1, **kwargs):
        super().__init__(data_dict, lot_size, **kwargs)
        self.box_size_percent     = kwargs.get('box_size_percent',     0.15)
        self.adx_threshold        = kwargs.get('adx_threshold',        20.0)
        self.sma_channel_percent  = kwargs.get('sma_channel_percent',   3.0)
        self.st_period            = kwargs.get('st_period',             10)
        self.st_multiplier        = kwargs.get('st_multiplier',          3.0)
        self.pullback_min_anchors = kwargs.get('pullback_min_anchors',   3)
        self.pnf_builder = PnFChartBuilder(box_size_percent=self.box_size_percent, reverse_boxes=3)
        self.supertrend_calc = Supertrend(period=self.st_period, multiplier=self.st_multiplier)

    @property
    def optimization_params(self) -> Dict:
        return {
            'box_size_percent'     : {'type': 'float', 'min': 0.10, 'max': 0.30, 'step': 0.05, 'default': 0.15},
            'adx_threshold'        : {'type': 'float', 'min': 15.0, 'max': 30.0, 'step': 5.0,  'default': 20.0},
            'sma_channel_percent'  : {'type': 'float', 'min': 1.0,  'max': 5.0,  'step': 1.0,  'default': 3.0},
            'st_period'            : {'type': 'int',   'min': 7,    'max': 14,   'step': 1,    'default': 10},
            'st_multiplier'        : {'type': 'float', 'min': 2.0,  'max': 4.0,  'step': 0.5,  'default': 3.0},
            'pullback_min_anchors' : {'type': 'int',   'min': 2,    'max': 5,    'step': 1,    'default': 3},
        }

    @property
    def required_timeframes(self) -> List[str]:
        return ['1H']

    def get_name(self) -> str:
        return "PnF Bearish Variant 4B [V4 - Ascending Pullback Structure]"

    def get_description(self) -> str:
        return "V4 TEST: Ascending O bottom pullback structure min 3 rising O bottoms. No trendline projection."

    def _check_ascending_pullback(self, columns: List[Dict], col_idx: int, min_anchors: int) -> Tuple[bool, int]:
        """
        Collect all O columns before col_idx in chronological order.
        Walk BACKWARD from the most recent O column.
        Count how many consecutive O bottoms form a strictly rising sequence
        ending at the most recent O before entry.
        STOP as soon as the chain breaks — do not reset and continue.

        Rising = each O bottom is strictly higher than the one before it
        (chronologically forward = each successive O bottom is higher).

        Walking backward: each step must be LOWER than the previous step.
        Stop on first violation.

        Example (chronological):
          O_bottom_1 = 99,000  <- oldest, lowest
          O_bottom_2 = 100,000
          O_bottom_3 = 101,000 <- most recent before entry, highest
        Walking backward: 101,000 -> 100,000 -> 99,000 (each lower, chain intact)
        anchor_count = 3, valid if min_anchors <= 3.
        """
        # Collect O columns before entry in chronological order
        o_cols_before = [
            columns[i] for i in range(col_idx)
            if columns[i]['type'] == 'O'
        ]

        if len(o_cols_before) < min_anchors:
            return False, len(o_cols_before)

        # Walk backward from most recent O before entry
        # Count consecutive rising O bottoms (each step backward must be lower)
        anchor_count = 1
        for k in range(len(o_cols_before) - 1, 0, -1):
            current_bottom  = o_cols_before[k]['end_level']
            previous_bottom = o_cols_before[k - 1]['end_level']
            if previous_bottom < current_bottom:
                # Previous (older) O bottom is lower — chain continues
                anchor_count += 1
            else:
                # Chain broken — stop here
                break

        return anchor_count >= min_anchors, anchor_count

    def generate_signals(self) -> List[Dict]:
        data = self.data_dict.get('1H')
        if data is None or len(data) == 0:
            print("ERROR: No 1H data available.")
            return []
        data = data.copy()
        data.columns = data.columns.str.lower()
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index, unit='s', utc=True)
            data.index = data.index.tz_localize(None)
        elif data.index.tz is not None:
            data.index = data.index.tz_localize(None)
        columns = self.pnf_builder.build_pnf_chart(data)
        if len(columns) < 5:
            print(f"ERROR: Not enough PnF columns ({len(columns)}). Need at least 5.")
            return []
        print(f"  PnF columns built: {len(columns)}")
        sma10_list = self.pnf_builder.calculate_sma(10)
        sma20_list = self.pnf_builder.calculate_sma(20)
        adx_list   = self.pnf_builder.calculate_adx(14)
        st_df = self.supertrend_calc.calculate(data)
        if st_df.index.tz is not None:
            st_df.index = st_df.index.tz_localize(None)
        upper_band_series = st_df['upper_band']
        signals                = []
        in_position            = False
        in_trading_cycle       = False
        had_first_entry        = False
        entry_col_idx          = -1
        sl_activation_col      = -1
        entry_price            = None
        last_double_bottom_col = -1
        dbg_o_cols_seen        = 0
        dbg_pullback_fail      = 0
        dbg_double_bottom_fail = 0
        dbg_adx_fail           = 0
        dbg_sma_fail           = 0
        dbg_passed             = 0
        for col_idx in range(len(columns)):
            col   = columns[col_idx]
            sma10 = sma10_list[col_idx]
            sma20 = sma20_list[col_idx]
            adx   = adx_list[col_idx]
            if sma10 is None or sma20 is None or adx is None:
                continue
            col_end_ts = pd.Timestamp(col['end_timestamp'])
            current_upper_band = upper_band_series.asof(col_end_ts)
            if in_position:
                if col_idx >= sl_activation_col:
                    sl_hit, sl_exit_price, sl_ts = self._check_sl_hit_intracolumn(col, col_idx, upper_band_series, data)
                    if sl_hit:
                        signals.append({'signal_type': 'EXIT', 'exit_type': 'SL_HIT_SUPERTREND', 'price': sl_exit_price, 'sl_price': sl_exit_price, 'column_idx': col_idx, 'timestamp': sl_ts, 'sma10': sma10, 'sma20': sma20, 'adx': adx})
                        in_position            = False
                        entry_col_idx          = -1
                        last_double_bottom_col = -1
                        in_trading_cycle = (sma10 < sma20) if had_first_entry else False
                        continue
                if col['type'] == 'X':
                    columns_slice = columns[:col_idx + 1]
                    dt_found, dt_idx = self.pnf_builder.detect_double_top(columns_slice)
                    if dt_found:
                        exit_price = col['end_level']
                        signals.append({'signal_type': 'EXIT', 'exit_type': 'DOUBLE_TOP', 'price': exit_price, 'sl_price': current_upper_band, 'column_idx': col_idx, 'timestamp': col_end_ts, 'sma10': sma10, 'sma20': sma20, 'adx': adx})
                        in_position            = False
                        entry_col_idx          = -1
                        last_double_bottom_col = -1
                        in_trading_cycle = (sma10 < sma20) if had_first_entry else False
                        continue
                continue
            if col['type'] != 'O':
                continue
            dbg_o_cols_seen += 1
            if in_trading_cycle:
                if not had_first_entry or sma10 >= sma20:
                    dbg_pullback_fail += 1
                    continue
            structure_valid, anchor_count = self._check_ascending_pullback(columns, col_idx, self.pullback_min_anchors)
            if not structure_valid:
                dbg_pullback_fail += 1
                continue
            columns_slice = columns[:col_idx + 1]
            db_found, second_o_idx = self.pnf_builder.detect_double_bottom(columns_slice)
            if not db_found or second_o_idx <= last_double_bottom_col:
                dbg_double_bottom_fail += 1
                continue
            if adx <= self.adx_threshold:
                dbg_adx_fail += 1
                continue
            price = col['end_level']
            if not in_trading_cycle:
                pct        = self.sma_channel_percent / 100.0
                near_sma10 = abs(price - sma10) / sma10 <= pct
                near_sma20 = abs(price - sma20) / sma20 <= pct
                if not (near_sma10 or near_sma20):
                    dbg_sma_fail += 1
                    continue
            dbg_passed += 1
            entry_type = 'FIRST_ENTRY' if not in_trading_cycle else 'RE_ENTRY'
            sl_value = float(current_upper_band) if not pd.isna(current_upper_band) else price * 1.03
            signals.append({'signal_type': 'ENTRY', 'entry_type': entry_type, 'price': price, 'sl_price': sl_value, 'column_idx': col_idx, 'timestamp': col_end_ts, 'sma10': sma10, 'sma20': sma20, 'adx': adx, 'anchor_count': anchor_count})
            in_position            = True
            if entry_type == 'FIRST_ENTRY':
                had_first_entry    = True
            entry_col_idx          = col_idx
            sl_activation_col      = col_idx + 1
            entry_price            = price
            last_double_bottom_col = second_o_idx
        print(f"\n  === SIGNAL FILTER DEBUG [V4 - ASCENDING PULLBACK STRUCTURE] ===")
        print(f"  O columns attempted        : {dbg_o_cols_seen}")
        print(f"  Rejected - Pullback struct : {dbg_pullback_fail}")
        print(f"  Rejected - Double Bottom   : {dbg_double_bottom_fail}")
        print(f"  Rejected - ADX             : {dbg_adx_fail}")
        print(f"  Rejected - SMA proximity   : {dbg_sma_fail}")
        print(f"  Supertrend entry filter    : DISABLED")
        print(f"  Passed all conditions      : {dbg_passed}")
        print(f"  Signals generated          : {len(signals)}")
        print(f"  ================================================\n")
        return signals

    def _check_sl_hit_intracolumn(self, col: Dict, col_idx: int, upper_band_series: pd.Series, data: pd.DataFrame) -> Tuple[bool, float, pd.Timestamp]:
        col_start = pd.Timestamp(col['start_timestamp'])
        col_end   = pd.Timestamp(col['end_timestamp'])
        candles_in_col = data[(data.index >= col_start) & (data.index <= col_end)]
        for candle_ts, candle_row in candles_in_col.iterrows():
            ub_val = upper_band_series.asof(candle_ts)
            if pd.isna(ub_val):
                continue
            if candle_row['high'] > ub_val:
                return True, float(candle_row['high']), candle_ts
        return False, 0.0, pd.Timestamp('NaT')
