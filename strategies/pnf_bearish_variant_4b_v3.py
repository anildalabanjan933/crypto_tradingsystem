"""
PnF Bearish Variant 4B — V3 TEST VERSION
==========================================
Change from V2 (pnf_bearish_variant_4b_v2.py):
  CHANGED: trendline_min_anchors default from 3 to 2
  REASON:  W2 (2025-11-13 20:00) had 2 valid rising O anchors and a confirmed
           trendline break but was blocked by the 3-anchor rule.
           Geometry validation proved 2 anchors are sufficient for a valid break.

All other logic identical to V2:
  - Trendline check (strictly rising O bottoms, geometric projection)
  - Double Bottom
  - ADX > 20
  - SMA proximity (first entry only)
  - Supertrend upper_band SL (trailing, intra-column candle high)
  - Cycle state (FIRST_ENTRY / RE_ENTRY)
  - last_double_bottom_col reset on both exit paths
  - Supertrend entry filter: DISABLED (same as V2)
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple

from strategies.base_strategy import BaseStrategy
from indicators.pnf import PnFChartBuilder
from indicators.supertrend import Supertrend


class PnFBearishVariant4BV3(BaseStrategy):
    """
    V3 TEST — Trendline check with minimum 2 rising O bottoms (relaxed from V2's 3).
    Supertrend entry filter still removed (same as V2).
    """

    def __init__(self, data_dict: Dict, lot_size: int = 1, **kwargs):
        super().__init__(data_dict, lot_size, **kwargs)

        self.box_size_percent      = kwargs.get('box_size_percent',      0.15)
        self.adx_threshold         = kwargs.get('adx_threshold',         20.0)
        self.sma_channel_percent   = kwargs.get('sma_channel_percent',    3.0)
        self.st_period             = kwargs.get('st_period',              10)
        self.st_multiplier         = kwargs.get('st_multiplier',           3.0)
        self.trendline_min_anchors = kwargs.get('trendline_min_anchors',   2)

        self.pnf_builder = PnFChartBuilder(
            box_size_percent=self.box_size_percent,
            reverse_boxes=3
        )
        self.supertrend_calc = Supertrend(
            period=self.st_period,
            multiplier=self.st_multiplier
        )

    @property
    def optimization_params(self) -> Dict:
        return {
            'box_size_percent'     : {'type': 'float', 'min': 0.10, 'max': 0.30,
                                      'step': 0.05, 'default': 0.15},
            'adx_threshold'        : {'type': 'float', 'min': 15.0, 'max': 30.0,
                                      'step': 5.0,  'default': 20.0},
            'sma_channel_percent'  : {'type': 'float', 'min': 1.0,  'max': 5.0,
                                      'step': 1.0,  'default': 3.0},
            'st_period'            : {'type': 'int',   'min': 7,    'max': 14,
                                      'step': 1,    'default': 10},
            'st_multiplier'        : {'type': 'float', 'min': 2.0,  'max': 4.0,
                                      'step': 0.5,  'default': 3.0},
            'trendline_min_anchors': {'type': 'int',   'min': 2,    'max': 4,
                                      'step': 1,    'default': 2},
        }

    @property
    def required_timeframes(self) -> List[str]:
        return ['1H']

    def get_name(self) -> str:
        return "PnF Bearish Variant 4B [V3 - Trendline Min 2 Anchors]"

    def get_description(self) -> str:
        return (
            "V3 TEST: Trendline restored with minimum 2 rising O bottoms. "
            "Supertrend entry filter still removed. "
            "Double Bottom + Trendline Break + ADX + SMA entry."
        )

    # ══════════════════════════════════════════════════════════════════
    # TRENDLINE HELPERS
    # ══════════════════════════════════════════════════════════════════

    def _get_rising_o_anchors(self, columns: List[Dict], col_idx: int) -> List[Tuple]:
        """
        Walk backward from col_idx (exclusive).
        Collect the longest strictly ascending sequence of O column bottoms.
        Strictly ascending means each earlier O bottom is LOWER than the next.

        Returns list of (col_idx, end_level, end_timestamp) in chronological order.
        Returns empty list if fewer than 2 O columns exist before col_idx.
        """
        o_cols_before = [
            (i, columns[i]) for i in range(col_idx)
            if columns[i]['type'] == 'O'
        ]

        if len(o_cols_before) < 2:
            return []

        # Walk backward: build rising sequence
        # Each new entry (going backward) must be LOWER than the current earliest
        sequence = []
        for i, col in reversed(o_cols_before):
            bottom = col['end_level']
            if len(sequence) == 0:
                sequence.insert(0, (i, bottom, col['end_timestamp']))
            elif bottom < sequence[0][1]:
                # This O bottom is lower — extends the rising sequence backward
                sequence.insert(0, (i, bottom, col['end_timestamp']))
            else:
                # Sequence broken — stop
                break

        return sequence  # chronological: oldest (lowest) first

    def _project_trendline(
        self,
        anchors    : List[Tuple],
        target_idx : int
    ) -> Optional[float]:
        """
        Two-point trendline: first anchor to last anchor.
        Project to target_idx using linear interpolation.
        """
        if len(anchors) < 2:
            return None
        x1, y1, _ = anchors[0]
        x2, y2, _ = anchors[-1]
        if x2 == x1:
            return None
        slope = (y2 - y1) / (x2 - x1)
        return y1 + slope * (target_idx - x1)

    def _check_trendline_break(
        self,
        columns    : List[Dict],
        col_idx    : int,
        min_anchors: int
    ) -> Tuple[bool, int, Optional[float]]:
        """
        Returns (break_confirmed, anchor_count, projected_value).

        break_confirmed = True only when:
          1. At least min_anchors strictly rising O bottoms exist before col_idx
          2. Current O end_level < projected trendline value at col_idx

        Returns (False, anchor_count, None) if insufficient anchors.
        Returns (False, anchor_count, projected) if anchors exist but no break.
        Returns (True,  anchor_count, projected) if break confirmed.
        """
        anchors = self._get_rising_o_anchors(columns, col_idx)
        anchor_count = len(anchors)

        if anchor_count < min_anchors:
            return False, anchor_count, None

        projected = self._project_trendline(anchors, col_idx)
        if projected is None:
            return False, anchor_count, None

        current_bottom = columns[col_idx]['end_level']
        break_confirmed = current_bottom < projected

        return break_confirmed, anchor_count, projected

    # ══════════════════════════════════════════════════════════════════
    # MAIN SIGNAL GENERATION
    # ══════════════════════════════════════════════════════════════════

    def generate_signals(self) -> List[Dict]:

        # ── 1. Load and validate 1H data ───────────────────────────────
        data = self.data_dict.get('1H')
        if data is None or len(data) == 0:
            print("ERROR: No 1H data available.")
            return []

        data = data.copy()
        data.columns = data.columns.str.lower()

        # ── 2. Ensure DatetimeIndex (tz-naive) ─────────────────────────
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index, unit='s', utc=True)
            data.index = data.index.tz_localize(None)
        elif data.index.tz is not None:
            data.index = data.index.tz_localize(None)

        # ── 3. Build PnF chart ─────────────────────────────────────────
        columns = self.pnf_builder.build_pnf_chart(data)
        if len(columns) < 5:
            print(f"ERROR: Not enough PnF columns ({len(columns)}). Need at least 5.")
            return []

        print(f"  PnF columns built: {len(columns)}")

        # ── 4. Indicators on PnF column end_levels ─────────────────────
        sma10_list = self.pnf_builder.calculate_sma(10)
        sma20_list = self.pnf_builder.calculate_sma(20)
        adx_list   = self.pnf_builder.calculate_adx(14)

        # ── 5. Supertrend on 1H candlesticks ───────────────────────────
        st_df = self.supertrend_calc.calculate(data)
        if st_df.index.tz is not None:
            st_df.index = st_df.index.tz_localize(None)

        upper_band_series = st_df['upper_band']

        # ── 6. Reset all state ─────────────────────────────────────────
        signals                = []
        in_position            = False
        in_trading_cycle       = False
        had_first_entry        = False
        entry_col_idx          = -1
        sl_activation_col      = -1
        entry_price            = None
        last_double_bottom_col = -1

        # ── Debug counters ─────────────────────────────────────────────
        dbg_o_cols_seen        = 0
        dbg_trendline_fail     = 0
        dbg_double_bottom_fail = 0
        dbg_adx_fail           = 0
        dbg_sma_fail           = 0
        dbg_passed             = 0

        # ── 7. Main column loop ────────────────────────────────────────
        for col_idx in range(len(columns)):

            col   = columns[col_idx]
            sma10 = sma10_list[col_idx]
            sma20 = sma20_list[col_idx]
            adx   = adx_list[col_idx]

            if sma10 is None or sma20 is None or adx is None:
                continue

            col_end_ts = pd.Timestamp(col['end_timestamp'])

            current_upper_band = upper_band_series.asof(col_end_ts)

            # ══════════════════════════════════════════════════════════
            # POSITION MANAGEMENT
            # ══════════════════════════════════════════════════════════
            if in_position:

                # ── SL check ──────────────────────────────────────────
                if col_idx >= sl_activation_col:
                    sl_hit, sl_exit_price, sl_ts = self._check_sl_hit_intracolumn(
                        col, col_idx, upper_band_series, data
                    )
                    if sl_hit:
                        signals.append({
                            'signal_type' : 'EXIT',
                            'exit_type'   : 'SL_HIT_SUPERTREND',
                            'price'       : sl_exit_price,
                            'sl_price'    : sl_exit_price,
                            'column_idx'  : col_idx,
                            'timestamp'   : sl_ts,
                            'sma10'       : sma10,
                            'sma20'       : sma20,
                            'adx'         : adx,
                        })
                        in_position            = False
                        entry_col_idx          = -1
                        last_double_bottom_col = -1

                        if had_first_entry:
                            in_trading_cycle = (sma10 < sma20)
                        else:
                            in_trading_cycle = False
                        continue

                # ── Double Top exit ────────────────────────────────────
                if col['type'] == 'X':
                    columns_slice = columns[:col_idx + 1]
                    dt_found, dt_idx = self.pnf_builder.detect_double_top(columns_slice)
                    if dt_found:
                        exit_price = col['end_level']
                        signals.append({
                            'signal_type' : 'EXIT',
                            'exit_type'   : 'DOUBLE_TOP',
                            'price'       : exit_price,
                            'sl_price'    : current_upper_band,
                            'column_idx'  : col_idx,
                            'timestamp'   : col_end_ts,
                            'sma10'       : sma10,
                            'sma20'       : sma20,
                            'adx'         : adx,
                        })
                        in_position            = False
                        entry_col_idx          = -1
                        last_double_bottom_col = -1

                        if had_first_entry:
                            in_trading_cycle = (sma10 < sma20)
                        else:
                            in_trading_cycle = False
                        continue

                continue

            # ══════════════════════════════════════════════════════════
            # ENTRY LOGIC — O columns only
            # ══════════════════════════════════════════════════════════
            if col['type'] != 'O':
                continue

            dbg_o_cols_seen += 1

            # ── RE-ENTRY gate ──────────────────────────────────────────
            if in_trading_cycle:
                if not had_first_entry or sma10 >= sma20:
                    dbg_trendline_fail += 1
                    continue

            # ── Condition 0: Trendline break (min 2 rising O anchors) ──
            tl_break, anchor_count, projected = self._check_trendline_break(
                columns, col_idx, self.trendline_min_anchors
            )
            if not tl_break:
                dbg_trendline_fail += 1
                continue

            # ── Condition 1: Double Bottom ─────────────────────────────
            columns_slice = columns[:col_idx + 1]
            db_found, second_o_idx = self.pnf_builder.detect_double_bottom(columns_slice)
            if not db_found or second_o_idx <= last_double_bottom_col:
                dbg_double_bottom_fail += 1
                continue

            # ── Condition 2: ADX ───────────────────────────────────────
            if adx <= self.adx_threshold:
                dbg_adx_fail += 1
                continue

            # ── Condition 3: SMA proximity (FIRST_ENTRY only) ──────────
            price = col['end_level']
            if not in_trading_cycle:
                pct        = self.sma_channel_percent / 100.0
                near_sma10 = abs(price - sma10) / sma10 <= pct
                near_sma20 = abs(price - sma20) / sma20 <= pct
                if not (near_sma10 or near_sma20):
                    dbg_sma_fail += 1
                    continue

            # ── All conditions passed ──────────────────────────────────
            dbg_passed += 1
            entry_type  = 'FIRST_ENTRY' if not in_trading_cycle else 'RE_ENTRY'

            sl_value = float(current_upper_band) if not pd.isna(current_upper_band) else price * 1.03

            signals.append({
                'signal_type'   : 'ENTRY',
                'entry_type'    : entry_type,
                'price'         : price,
                'sl_price'      : sl_value,
                'column_idx'    : col_idx,
                'timestamp'     : col_end_ts,
                'sma10'         : sma10,
                'sma20'         : sma20,
                'adx'           : adx,
                'anchor_count'  : anchor_count,
                'tl_projected'  : round(projected, 2) if projected else None,
            })

            in_position            = True
            if entry_type == 'FIRST_ENTRY':
                had_first_entry    = True
            entry_col_idx          = col_idx
            sl_activation_col      = col_idx + 1
            entry_price            = price
            last_double_bottom_col = second_o_idx

        # ── Debug summary ──────────────────────────────────────────────
        print(f"\n  === SIGNAL FILTER DEBUG [V3 - MIN 2 ANCHORS] ===")
        print(f"  O columns attempted      : {dbg_o_cols_seen}")
        print(f"  Rejected - Trendline     : {dbg_trendline_fail}")
        print(f"  Rejected - Double Bottom : {dbg_double_bottom_fail}")
        print(f"  Rejected - ADX           : {dbg_adx_fail}")
        print(f"  Rejected - SMA proximity : {dbg_sma_fail}")
        print(f"  Supertrend entry filter  : DISABLED")
        print(f"  Passed all conditions    : {dbg_passed}")
        print(f"  Signals generated        : {len(signals)}")
        print(f"  ================================================\n")

        return signals

    # ══════════════════════════════════════════════════════════════════
    # SL CHECK — INTRA-COLUMN CANDLE SCAN
    # ══════════════════════════════════════════════════════════════════

    def _check_sl_hit_intracolumn(
        self,
        col               : Dict,
        col_idx           : int,
        upper_band_series : pd.Series,
        data              : pd.DataFrame,
    ) -> Tuple[bool, float, pd.Timestamp]:
        """
        Scan every 1H candle within this PnF column.
        SHORT SL triggers when candle HIGH > Supertrend upper_band.
        Exit price = actual candle HIGH (not SL level).
        """
        col_start = pd.Timestamp(col['start_timestamp'])
        col_end   = pd.Timestamp(col['end_timestamp'])

        candles_in_col = data[
            (data.index >= col_start) & (data.index <= col_end)
        ]

        for candle_ts, candle_row in candles_in_col.iterrows():
            ub_val = upper_band_series.asof(candle_ts)
            if pd.isna(ub_val):
                continue
            if candle_row['high'] > ub_val:
                return True, float(candle_row['high']), candle_ts

        return False, 0.0, pd.Timestamp('NaT')
