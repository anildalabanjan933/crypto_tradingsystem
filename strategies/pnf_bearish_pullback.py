# strategies/pnf_bearish_pullback.py
#
# PnF Bearish Pullback Strategy
# ─────────────────────────────
# FIRST ENTRY conditions (all must be true):
#   1. SMA10 < SMA20
#   2. Price near SMA10 ±3% OR near SMA20 ±3%
#   3. ADX > 20
#   4. Minimum 2 consecutive rising O bottoms before entry column
#      (entry column = Double Bottom breakdown column, NOT counted)
#   5. Double Bottom breakdown confirmed (second O bottom < first by ≥1 box)
#
# STOP LOSS:
#   SL = top of most recent completed X column + 1 box buffer
#   SL hit when candle high > SL level (fixed, does not trail)
#
# EXIT:
#   Double Top breakout (PnF)  OR  SL hit
#
# RE-ENTRY:
#   1. SMA10 < SMA20 must still be true
#   2. New Double Bottom breakdown required
#   3. Recompute SL fresh from latest X-column top
#   (No proximity check, no ADX check, no pullback check on re-entry)
#
# INDICATORS: SMA10, SMA20, ADX14 — all on PnF column end_levels
# NO Supertrend, NO ATR, NO trendline logic anywhere in this file
# ─────────────────────────────

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple

from strategies.base_strategy import BaseStrategy
from indicators.pnf import PnFChartBuilder


class PnFBearishPullback(BaseStrategy):
    """
    PnF Bearish Pullback Strategy.
    Completely independent of all 4B variant files.
    SL = previous X-column top + 1 box buffer (fixed, no trail).
    """

    def __init__(self, data_dict: Dict, lot_size: int = 1, **kwargs):
        super().__init__(data_dict, lot_size, **kwargs)

        self.box_size_percent    = kwargs.get('box_size_percent',    0.15)
        self.adx_threshold       = kwargs.get('adx_threshold',       20.0)
        self.sma_channel_percent = kwargs.get('sma_channel_percent',  3.0)
        self.min_rising_anchors  = kwargs.get('min_rising_anchors',   2)
        self.sl_buffer_boxes     = kwargs.get('sl_buffer_boxes',      1.0)

        self.pnf_builder = PnFChartBuilder(
            box_size_percent=self.box_size_percent,
            reverse_boxes=3
        )

    # ── BaseStrategy interface ───────────────────────────────────────────

    @property
    def optimization_params(self) -> Dict:
        return {
            'box_size_percent'   : {'type': 'float', 'min': 0.10, 'max': 0.30,
                                    'step': 0.05, 'default': 0.15},
            'adx_threshold'      : {'type': 'float', 'min': 15.0, 'max': 30.0,
                                    'step': 5.0,  'default': 20.0},
            'sma_channel_percent': {'type': 'float', 'min': 1.0,  'max': 5.0,
                                    'step': 1.0,  'default': 3.0},
            'min_rising_anchors' : {'type': 'int',   'min': 2,    'max': 4,
                                    'step': 1,    'default': 2},
            'sl_buffer_boxes'    : {'type': 'float', 'min': 0.5,  'max': 2.0,
                                    'step': 0.5,  'default': 1.0},
        }

    @property
    def required_timeframes(self) -> List[str]:
        return ['1H']

    def get_name(self) -> str:
        return "PnF Bearish Pullback"

    def get_description(self) -> str:
        return (
            "Bearish pullback strategy: ascending O bottom structure + "
            "Double Bottom breakdown. SL = previous X-column top + 1 box. "
            "No Supertrend, no ATR, no trendline logic."
        )

    # ════════════════════════════════════════════════════════════════════
    # MAIN SIGNAL GENERATION
    # ════════════════════════════════════════════════════════════════════

    def generate_signals(self) -> List[Dict]:

        # ── 1. Load and validate 1H data ─────────────────────────────────
        data = self.data_dict.get('1H')
        if data is None or len(data) == 0:
            print("ERROR: No 1H data available.")
            return []

        data = data.copy()
        data.columns = data.columns.str.lower()

        # ── 2. Ensure DatetimeIndex (tz-naive) ───────────────────────────
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index, unit='s', utc=True)
            data.index = data.index.tz_localize(None)
        elif data.index.tz is not None:
            data.index = data.index.tz_localize(None)

        # ── 3. Build PnF chart ───────────────────────────────────────────
        columns = self.pnf_builder.build_pnf_chart(data)
        if len(columns) < 5:
            print(f"ERROR: Not enough PnF columns ({len(columns)}). Need at least 5.")
            return []

        print(f"  PnF columns built: {len(columns)}")

        # ── 4. Indicators on PnF column end_levels ───────────────────────
        sma10_list = self.pnf_builder.calculate_sma(10)
        sma20_list = self.pnf_builder.calculate_sma(20)
        adx_list   = self.pnf_builder.calculate_adx(14)

        # ── 5. Reset all state ───────────────────────────────────────────
        signals                = []
        in_position            = False
        had_first_entry        = False
        in_trading_cycle       = False
        sl_level               = None
        sl_activation_col      = -1
        last_double_bottom_col = -1

        # ── Debug counters ───────────────────────────────────────────────
        dbg_o_cols_seen        = 0
        dbg_db_fail            = 0
        dbg_pullback_fail      = 0
        dbg_sma_align_fail     = 0
        dbg_sma_proximity_fail = 0
        dbg_adx_fail           = 0
        dbg_sl_fail            = 0
        dbg_passed             = 0

        # ── 6. Main column loop ──────────────────────────────────────────
        for col_idx in range(len(columns)):

            col   = columns[col_idx]
            sma10 = sma10_list[col_idx]
            sma20 = sma20_list[col_idx]
            adx   = adx_list[col_idx]

            if sma10 is None or sma20 is None or adx is None:
                continue

            col_end_ts = pd.Timestamp(col['end_timestamp'])

            # ════════════════════════════════════════════════════════════
            # POSITION MANAGEMENT
            # ════════════════════════════════════════════════════════════
            if in_position:

                # ── SL check (candle-level scan within this column) ──────
                if col_idx >= sl_activation_col:
                    sl_hit, sl_exit_price, sl_ts = self._check_sl_hit_intracolumn(
                        col, data, sl_level
                    )
                    if sl_hit:
                        signals.append({
                            'signal_type' : 'EXIT',
                            'exit_type'   : 'SL_HIT',
                            'price'       : sl_exit_price,
                            'sl_price'    : sl_level,
                            'column_idx'  : col_idx,
                            'timestamp'   : sl_ts,
                            'sma10'       : sma10,
                            'sma20'       : sma20,
                            'adx'         : adx,
                        })
                        in_position            = False
                        sl_level               = None
                        last_double_bottom_col = -1
                        in_trading_cycle       = had_first_entry and (sma10 < sma20)
                        continue

                # ── Double Top exit ──────────────────────────────────────
                if col['type'] == 'X':
                    columns_slice = columns[:col_idx + 1]
                    dt_found, _ = self.pnf_builder.detect_double_top(columns_slice)
                    if dt_found:
                        exit_price = col['end_level']
                        signals.append({
                            'signal_type' : 'EXIT',
                            'exit_type'   : 'DOUBLE_TOP',
                            'price'       : exit_price,
                            'sl_price'    : sl_level,
                            'column_idx'  : col_idx,
                            'timestamp'   : col_end_ts,
                            'sma10'       : sma10,
                            'sma20'       : sma20,
                            'adx'         : adx,
                        })
                        in_position            = False
                        sl_level               = None
                        last_double_bottom_col = -1
                        in_trading_cycle       = had_first_entry and (sma10 < sma20)
                        continue

                continue

            # ════════════════════════════════════════════════════════════
            # ENTRY LOGIC — O columns only
            # ════════════════════════════════════════════════════════════
            if col['type'] != 'O':
                continue

            dbg_o_cols_seen += 1
            columns_slice    = columns[:col_idx + 1]
            price            = col['end_level']

            # ── Double Bottom check (both paths) ─────────────────────────
            db_found, second_o_idx = self.pnf_builder.detect_double_bottom(columns_slice)
            if not db_found or second_o_idx <= last_double_bottom_col:
                dbg_db_fail += 1
                continue

            # ── Ascending pullback structure (both paths) ─────────────────
            if not self._check_ascending_pullback(columns, col_idx):
                dbg_pullback_fail += 1
                continue

            # ════════════════════════════════════════════════════════════
            # FIRST ENTRY — additional filters
            # ════════════════════════════════════════════════════════════
            if not in_trading_cycle:

                # SMA alignment
                if not (sma10 < sma20):
                    dbg_sma_align_fail += 1
                    continue

                # SMA proximity
                if not self._check_sma_proximity(price, sma10, sma20):
                    dbg_sma_proximity_fail += 1
                    continue

                # ADX
                if adx <= self.adx_threshold:
                    dbg_adx_fail += 1
                    continue

            # ════════════════════════════════════════════════════════════
            # RE-ENTRY — SMA alignment only
            # ════════════════════════════════════════════════════════════
            else:
                if not (sma10 < sma20):
                    dbg_sma_align_fail += 1
                    continue

                # Guard: do not re-enter on same DB column
                if col_idx == last_double_bottom_col:
                    continue

            # ── Compute SL from previous X-column top ────────────────────
            sl = self._compute_sl(columns, col_idx, col['box_size'])
            if sl is None:
                dbg_sl_fail += 1
                continue

            # ── All conditions passed — emit entry signal ─────────────────
            dbg_passed += 1
            entry_type  = 'FIRST_ENTRY' if not in_trading_cycle else 'RE_ENTRY'

            signals.append({
                'signal_type' : 'ENTRY',
                'entry_type'  : entry_type,
                'price'       : price,
                'sl_price'    : sl,
                'column_idx'  : col_idx,
                'timestamp'   : col_end_ts,
                'sma10'       : sma10,
                'sma20'       : sma20,
                'adx'         : adx,
            })

            in_position            = True
            had_first_entry        = True
            in_trading_cycle       = True
            sl_level               = sl
            sl_activation_col      = col_idx + 1
            last_double_bottom_col = second_o_idx

        # ── Debug summary ─────────────────────────────────────────────────
        print(f"\n  === SIGNAL FILTER DEBUG [PnF BEARISH PULLBACK] ===")
        print(f"  O columns attempted        : {dbg_o_cols_seen}")
        print(f"  Rejected - Double Bottom   : {dbg_db_fail}")
        print(f"  Rejected - Pullback struct : {dbg_pullback_fail}")
        print(f"  Rejected - SMA alignment   : {dbg_sma_align_fail}")
        print(f"  Rejected - SMA proximity   : {dbg_sma_proximity_fail}")
        print(f"  Rejected - ADX             : {dbg_adx_fail}")
        print(f"  Rejected - No X-col SL     : {dbg_sl_fail}")
        print(f"  Passed all conditions      : {dbg_passed}")
        print(f"  Signals generated          : {len(signals)}")
        print(f"  ==================================================\n")

        return signals

    # ════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ════════════════════════════════════════════════════════════════════

    def _check_ascending_pullback(self, columns: List[Dict], col_idx: int) -> bool:
        """
        Walk backward from the column BEFORE col_idx.
        Count consecutive rising O bottoms (each step back must be lower).
        Entry column (col_idx) is NOT counted as an anchor.
        Require at least self.min_rising_anchors in the unbroken chain.

        Example with min=2:
          Walking back: O_prev=102, O_prev_prev=100
          102 > 100 → rising chain of 2 → PASS
        """
        # Collect O column end_levels before the entry column
        o_bottoms = []
        for i in range(col_idx - 1, -1, -1):
            if columns[i]['type'] == 'O':
                o_bottoms.append(columns[i]['end_level'])

        # o_bottoms[0] = most recent O before entry
        # o_bottoms[1] = one before that
        # Rising chain means: o_bottoms[0] > o_bottoms[1] > o_bottoms[2] ...
        # i.e., walking backward in time each value must be LOWER

        if len(o_bottoms) < self.min_rising_anchors:
            return False

        chain_count = 1
        for i in range(1, len(o_bottoms)):
            if o_bottoms[i] < o_bottoms[i - 1]:
                chain_count += 1
                if chain_count >= self.min_rising_anchors:
                    return True
            else:
                break

        return chain_count >= self.min_rising_anchors

    def _check_sma_proximity(
        self, price: float, sma10: float, sma20: float
    ) -> bool:
        """Price within ±sma_channel_percent of SMA10 OR SMA20."""
        pct        = self.sma_channel_percent / 100.0
        near_sma10 = abs(price - sma10) / sma10 <= pct
        near_sma20 = abs(price - sma20) / sma20 <= pct
        return near_sma10 or near_sma20

    def _compute_sl(
        self,
        columns:   List[Dict],
        col_idx:   int,
        box_size:  float,
    ) -> Optional[float]:
        """
        SL = high of the most recent completed X column before col_idx
             + sl_buffer_boxes * box_size.
        Returns None if no X column exists yet.
        """
        for i in range(col_idx - 1, -1, -1):
            if columns[i]['type'] == 'X':
                x_top = columns[i].get('high', columns[i]['end_level'])
                sl    = x_top + (self.sl_buffer_boxes * box_size)
                return round(sl, 2)
        return None

    def _check_sl_hit_intracolumn(
        self,
        col:      Dict,
        data:     pd.DataFrame,
        sl_level: float,
    ) -> Tuple[bool, float, pd.Timestamp]:
        """
        Scan every 1H candle within this PnF column.
        SHORT SL triggers when candle HIGH > sl_level.
        Exit price = actual candle HIGH at the moment of breach.
        """
        col_start = pd.Timestamp(col['start_timestamp'])
        col_end   = pd.Timestamp(col['end_timestamp'])

        candles_in_col = data[
            (data.index >= col_start) & (data.index <= col_end)
        ]

        for candle_ts, candle_row in candles_in_col.iterrows():
            if candle_row['high'] > sl_level:
                return True, float(candle_row['high']), candle_ts

        return False, 0.0, pd.Timestamp('NaT')
