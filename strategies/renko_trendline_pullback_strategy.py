# strategies/renko_trendline_pullback_strategy.py
# Strategy: Renko Trendline Pullback
# Entry: Price pulls back to trendline (ascending/descending/horizontal) + 1 box close in direction
# Exit:  ST flip only (same as Strategy 1)

import numpy as np
import pandas as pd
from strategies.base_strategy import BaseStrategy
from indicators.renko import _trendline_value_at, RenkoBuilder, SupertrendIndicator, SwingDetector


class RenkoTrendlinePullbackStrategy(BaseStrategy):
    """
    Renko Trendline Pullback Strategy.

    Entry Logic
    -----------
    BUY  : Valid bullish trendline exists (min 2 renko box LOW touches)
           + renko box LOW touches trendline again (within 1 box tolerance)
           + 1 full green renko box closes
           ST direction does NOT matter for entry

    SELL : Valid bearish trendline exists (min 2 renko box HIGH touches)
           + renko box HIGH touches trendline again (within 1 box tolerance)
           + 1 full red renko box closes
           ST direction does NOT matter for entry

    Trendline Validation
    --------------------
    - Bullish  : min 2 renko box LOWS touch ascending/horizontal line
    - Bearish  : min 2 renko box HIGHS touch descending/horizontal line
    - Touch    : renko box HIGH or LOW within 1 box size of trendline

    Trendline Invalidation
    ----------------------
    - Bullish  : 1 full red box closes BELOW trendline = invalidated
    - Bearish  : 1 full green box closes ABOVE trendline = invalidated
    - After invalidation: no more entries until 2 new swing points form

    Exit Logic
    ----------
    LONG  EXIT : ST flips RED   + 1 full red box close
    SHORT EXIT : ST flips GREEN + 1 full green box close

    Position Management
    -------------------
    Max 2 open positions (any combination: 2 buys, 2 sells, 1 buy + 1 sell)
    """

    # ------------------------------------------------------------------
    # __init__()
    # ------------------------------------------------------------------
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        super().__init__(
            data_dict=data_dict,
            lot_size=lot_size
        )

        # Renko settings
        self.renko_box     = kwargs.get('renko_box', 200.0)
        self.max_tl_bars   = kwargs.get('max_tl_bars', 50)
        self.max_positions = kwargs.get('max_positions', 2)

        # Slippage and commission
        self.slippage_usd  = kwargs.get('slippage_usd', 0.0)
        self.commission_pc = kwargs.get('commission_pct', 0.0)

    # ------------------------------------------------------------------
    # ABSTRACT METHOD IMPLEMENTATIONS
    # ------------------------------------------------------------------

    @property
    def optimization_params(self) -> dict:
        return {
            'box_pct'      : {'default': 0.010, 'min': 0.005, 'max': 0.020, 'step': 0.001},
            'st_atr_len'   : {'default': 5,     'min': 3,     'max': 14,    'step': 1},
            'st_factor'    : {'default': 4.0,   'min': 2.0,   'max': 6.0,   'step': 0.5},
            'max_positions': {'default': 2,      'min': 1,     'max': 2,     'step': 1},
        }

    @property
    def required_timeframes(self) -> list:
        return ['2H']

    # ------------------------------------------------------------------
    # SLIPPAGE HELPER
    # ------------------------------------------------------------------

    def _apply_slippage(self, price: float, direction: str, is_entry: bool) -> float:
        slip = self.slippage_usd
        if direction == 'long':
            return price + slip if is_entry else price - slip
        else:
            return price - slip if is_entry else price + slip

    # ------------------------------------------------------------------
    # RENKO DF BUILDER
    # ------------------------------------------------------------------

    def _build_renko_df(self) -> pd.DataFrame:
        df_2h = self._data.get('2H')
        if df_2h is None or len(df_2h) == 0:
            raise ValueError("RenkoTrendlinePullbackStrategy requires '2H' timeframe data")

        closes     = df_2h['close'].values
        timestamps = df_2h.index if isinstance(df_2h.index, pd.DatetimeIndex) else pd.to_datetime(df_2h['timestamp'])

        # Build Renko bricks
        builder   = RenkoBuilder(box_size=self.renko_box)
        renko_raw = builder.build(closes)

        if renko_raw is None or len(renko_raw) == 0:
            raise ValueError("RenkoBuilder produced no bricks - check box size or data range")

        # Map timestamps
        renko_raw['timestamp'] = renko_raw['bar_index'].apply(
            lambda idx: timestamps[idx] if idx < len(timestamps) else timestamps[-1]
        )

        # Add Supertrend
        st_indicator = SupertrendIndicator(atr_period=5, factor=4.0)
        renko_st     = st_indicator.calculate(renko_raw)

        # Add Swing detection
        swing_detector = SwingDetector(swing_left=2, swing_right=2)
        renko_df       = swing_detector.detect(renko_st)

        return renko_df

    # ------------------------------------------------------------------
    # TRENDLINE TOUCH CHECK
    # ------------------------------------------------------------------

    def _trendline_touched(self, box_edge: float, tl_value: float, box_size: float) -> bool:
        """
        Check if renko box HIGH or LOW touched the trendline.
        Touch = within 1 box size of the trendline.

        Parameters
        ----------
        box_edge  : renko_low (for bullish) or renko_high (for bearish)
        tl_value  : projected trendline price at current bar
        box_size  : renko box size (tolerance = 1 box)
        """
        return abs(box_edge - tl_value) <= box_size

    # ------------------------------------------------------------------
    # TRENDLINE INVALIDATION CHECK
    # ------------------------------------------------------------------

    def _bullish_tl_broken(self, renko_close: float, renko_dir: int, tl_value: float) -> bool:
        """
        Bullish trendline invalidated when 1 full red box closes BELOW trendline.
        """
        return renko_dir == -1 and renko_close < tl_value

    def _bearish_tl_broken(self, renko_close: float, renko_dir: int, tl_value: float) -> bool:
        """
        Bearish trendline invalidated when 1 full green box closes ABOVE trendline.
        """
        return renko_dir == 1 and renko_close > tl_value

    # ------------------------------------------------------------------
    # SIGNAL GENERATION
    # ------------------------------------------------------------------

    def generate_signals(self) -> list:
        """
        Generate BUY/SELL signals based on trendline pullback logic.

        Entry logic (renko chart truth only):
        - BUY  : renko box LOW touches bullish trendline (within 1 box)
                 + min 2 swing lows confirmed on trendline
                 + 1 full green renko box closes
                 + trendline not invalidated
                 + max positions not reached

        - SELL : renko box HIGH touches bearish trendline (within 1 box)
                 + min 2 swing highs confirmed on trendline
                 + 1 full red renko box closes
                 + trendline not invalidated
                 + max positions not reached

        Exit logic:
        - LONG  EXIT : ST flips RED   + 1 full red box close
        - SHORT EXIT : ST flips GREEN + 1 full green box close
        """
        df = self._build_renko_df()

        n           = len(df)
        renko_close = df['renko_close'].values
        renko_dir   = df['renko_dir'].values
        renko_high  = df['renko_high'].values
        renko_low   = df['renko_low'].values
        st_dir      = df['st_dir'].values
        sh_hist     = df['swing_highs_hist'].tolist()
        sl_hist     = df['swing_lows_hist'].tolist()
        timestamps  = df['timestamp'].values

        box      = self.renko_box
        max_bars = self.max_tl_bars

        # ------------------------------------------------------------------
        # TRENDLINE INVALIDATION STATE TRACKING
        # ------------------------------------------------------------------
        bullish_tl_invalid = False  # True when bullish trendline is broken
        bearish_tl_invalid = False  # True when bearish trendline is broken
        bullish_invalid_bar = -1  # bar index when bullish TL was invalidated
        bearish_invalid_bar = -1  # bar index when bearish TL was invalidated
        sl_pivot_bar_at_invalid = -1  # pivot bar index of last sl swing at invalidation
        sh_pivot_bar_at_invalid = -1  # pivot bar index of last sh swing at invalidation
        new_sl_count_after_invalid = 0  # count of new sl swings after invalidation
        new_sh_count_after_invalid = 0  # count of new sh swings after invalidation

        # ------------------------------------------------------------------
        # POSITION TRACKING
        # ------------------------------------------------------------------
        open_positions = []   # list of dicts: {'direction': 'long'/'short', 'entry_price': float}

        signals  = []
        prev_st  = st_dir[0]
        prev_buy  = False
        prev_sell = False

        for i in range(1, n):
            ts      = str(pd.Timestamp(timestamps[i]).strftime('%Y-%m-%dT%H:%M:%S'))
            r_close = renko_close[i]
            r_dir   = renko_dir[i]
            r_high  = renko_high[i]
            r_low   = renko_low[i]
            st      = st_dir[i]

            # ----------------------------------------------------------
            # TRENDLINE VALUES AT CURRENT BAR
            # ----------------------------------------------------------
            bullish_tl_val = _trendline_value_at(sl_hist[i], i, max_bars)
            bearish_tl_val = _trendline_value_at(sh_hist[i], i, max_bars)

            # ----------------------------------------------------------
            # TRENDLINE INVALIDATION RESET
            # When 2 new swing lows form after invalidation = new bullish trendline valid
            # When 2 new swing highs form after invalidation = new bearish trendline valid
            # ----------------------------------------------------------
            current_sl_list = sl_hist[i]  # list of (bar_idx, price), max 2 entries
            current_sh_list = sh_hist[i]  # list of (bar_idx, price), max 2 entries

            # Get the most recent swing bar index at current bar
            current_sl_pivot_bar = current_sl_list[-1][0] if len(current_sl_list) >= 1 else -1
            current_sh_pivot_bar = current_sh_list[-1][0] if len(current_sh_list) >= 1 else -1

            if bullish_tl_invalid and bullish_invalid_bar >= 0:
                if current_sl_pivot_bar > sl_pivot_bar_at_invalid:
                    # A new swing low formed after invalidation
                    new_sl_count_after_invalid += 1
                    sl_pivot_bar_at_invalid = current_sl_pivot_bar  # advance tracker
                    if new_sl_count_after_invalid >= 2:
                        bullish_tl_invalid = False
                        bullish_invalid_bar = -1
                        sl_pivot_bar_at_invalid = -1
                        new_sl_count_after_invalid = 0

            if bearish_tl_invalid and bearish_invalid_bar >= 0:
                if current_sh_pivot_bar > sh_pivot_bar_at_invalid:
                    # A new swing high formed after invalidation
                    new_sh_count_after_invalid += 1
                    sh_pivot_bar_at_invalid = current_sh_pivot_bar  # advance tracker
                    if new_sh_count_after_invalid >= 2:
                        bearish_tl_invalid = False
                        bearish_invalid_bar = -1
                        sh_pivot_bar_at_invalid = -1
                        new_sh_count_after_invalid = 0

            # ----------------------------------------------------------
            # CHECK TRENDLINE INVALIDATION AT CURRENT BAR
            # ----------------------------------------------------------
            if bullish_tl_val is not None and not bullish_tl_invalid:
                if self._bullish_tl_broken(r_close, r_dir, bullish_tl_val):
                    bullish_tl_invalid = True
                    bullish_invalid_bar = i
                    sl_pivot_bar_at_invalid = current_sl_pivot_bar  # snapshot pivot bar
                    new_sl_count_after_invalid = 0  # reset counter

            if bearish_tl_val is not None and not bearish_tl_invalid:
                if self._bearish_tl_broken(r_close, r_dir, bearish_tl_val):
                    bearish_tl_invalid = True
                    bearish_invalid_bar = i
                    sh_pivot_bar_at_invalid = current_sh_pivot_bar  # snapshot pivot bar
                    new_sh_count_after_invalid = 0  # reset counter

            # ----------------------------------------------------------
            # EXIT: ST flip only
            # Check all open positions for exit condition
            # ----------------------------------------------------------
            positions_to_close = []

            for pos in open_positions:
                # LONG EXIT: ST flips green->red + 1 red box close
                if pos['direction'] == 'long' and prev_st == -1 and st == 1 and r_dir == -1:
                    exit_price = self._apply_slippage(r_close, 'long', is_entry=False)
                    signals.append({
                        'signal_type': 'EXIT',
                        'price'      : exit_price,
                        'timestamp'  : ts,
                        'sl_price'   : r_close - box,
                        'entry_type' : '',
                        'exit_type'  : 'ST_FLIP_RED',
                        'direction'  : 'long',
                    })
                    positions_to_close.append(pos)

                # SHORT EXIT: ST flips red->green + 1 green box close
                elif pos['direction'] == 'short' and prev_st == 1 and st == -1 and r_dir == 1:
                    exit_price = self._apply_slippage(r_close, 'short', is_entry=False)
                    signals.append({
                        'signal_type': 'EXIT',
                        'price'      : exit_price,
                        'timestamp'  : ts,
                        'sl_price'   : r_close + box,
                        'entry_type' : '',
                        'exit_type'  : 'ST_FLIP_GREEN',
                        'direction'  : 'short',
                    })
                    positions_to_close.append(pos)

            # Remove closed positions
            for pos in positions_to_close:
                open_positions.remove(pos)

            # ----------------------------------------------------------
            # ENTRY CONDITIONS (renko chart truth only)
            # No ST condition for entry
            # ----------------------------------------------------------

            # BUY ENTRY CONDITIONS
            # - Valid bullish trendline exists (min 2 swing lows)
            # - Trendline not invalidated
            # - renko box LOW touches trendline (within 1 box)
            # - 1 full green renko box closes
            # - Max positions not reached
            buy = False
            if (
                bullish_tl_val is not None
                and not bullish_tl_invalid
                and len(sl_hist[i]) >= 2
                and self._trendline_touched(r_low, bullish_tl_val, box)
                and r_dir == 1
                and len(open_positions) < self.max_positions
            ):
                buy = True

            # SELL ENTRY CONDITIONS
            # - Valid bearish trendline exists (min 2 swing highs)
            # - Trendline not invalidated
            # - renko box HIGH touches trendline (within 1 box)
            # - 1 full red renko box closes
            # - Max positions not reached
            sell = False
            if (
                bearish_tl_val is not None
                and not bearish_tl_invalid
                and len(sh_hist[i]) >= 2
                and self._trendline_touched(r_high, bearish_tl_val, box)
                and r_dir == -1
                and len(open_positions) < self.max_positions
            ):
                sell = True

            # ----------------------------------------------------------
            # RISING EDGE DEDUP
            # ----------------------------------------------------------
            buy_edge  = buy  and not prev_buy
            sell_edge = sell and not prev_sell

            # ----------------------------------------------------------
            # ENTRY SIGNALS
            # ----------------------------------------------------------
            if buy_edge and len(open_positions) < self.max_positions:
                entry_price = self._apply_slippage(r_close, 'long', is_entry=True)
                signals.append({
                    'signal_type': 'ENTRY',
                    'price'      : entry_price,
                    'timestamp'  : ts,
                    'sl_price'   : r_close - box * 2,
                    'entry_type' : 'BUY',
                    'exit_type'  : '',
                    'direction'  : 'long',
                })
                open_positions.append({'direction': 'long', 'entry_price': entry_price})

            if sell_edge and len(open_positions) < self.max_positions:
                entry_price = self._apply_slippage(r_close, 'short', is_entry=True)
                signals.append({
                    'signal_type': 'ENTRY',
                    'price'      : entry_price,
                    'timestamp'  : ts,
                    'sl_price'   : r_close + box * 2,
                    'entry_type' : 'SELL',
                    'exit_type'  : '',
                    'direction'  : 'short',
                })
                open_positions.append({'direction': 'short', 'entry_price': entry_price})

            # ----------------------------------------------------------
            # UPDATE PREVIOUS FLAGS
            # ----------------------------------------------------------
            prev_buy  = buy
            prev_sell = sell
            prev_st   = st

        return signals
