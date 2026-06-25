# strategies/renko_reversal_strategy.py
# Strategy 2: Renko Reverse at S/R
# Entry: ST FLIP at support/resistance zone
# Exit:  ST flip only (same as Strategy 1)

import numpy as np
import pandas as pd
from strategies.base_strategy import BaseStrategy
from indicators.renko import _trendline_value_at, RenkoBuilder, SupertrendIndicator, SwingDetector


class RenkoReversalStrategy(BaseStrategy):
    """
    Renko Reversal Strategy - Reverse at S/R only.

    Signal Types
    ------------
    BUY  : ST flips red->green + price near support (horizontal OR ascending TL) + min 2 swing lows + 1 green brick close
    SELL : ST flips green->red + price near resistance (horizontal OR descending TL) + min 2 swing highs + 1 red brick close

    Exit
    ----
    ST flip only (same as Strategy 1)
    GREEN->RED exits LONG (1 red brick close)
    RED->GREEN exits SHORT (1 green brick close)
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
        self.renko_box    = kwargs.get('renko_box', 200.0)
        self.sr_tolerance = kwargs.get('sr_tolerance', 5.0)
        self.max_tl_bars  = kwargs.get('max_tl_bars', 50)

        # Slippage (USD per side)
        self.slippage_usd = kwargs.get('slippage_usd', 0.0)

        # Commission rate
        self.commission_pc = kwargs.get('commission_pct', 0.0)

    # ------------------------------------------------------------------
    # ABSTRACT METHOD IMPLEMENTATIONS
    # ------------------------------------------------------------------

    @property
    def required_timeframes(self) -> list:
        return ['2H']

    @property
    def optimization_params(self) -> dict:
        return {
            'renko_box'    : {'default': 200,  'min': 100,  'max': 500,  'step': 50},
            'st_atr_len'   : {'default': 5,    'min': 3,    'max': 14,   'step': 1},
            'st_factor'    : {'default': 4.0,  'min': 2.0,  'max': 6.0,  'step': 0.5},
            'sr_tolerance' : {'default': 0.5,  'min': 0.25, 'max': 2.0,  'step': 0.25},
        }

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
            raise ValueError("RenkoReversalStrategy requires '2H' timeframe data in data_dict")

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
    # SIGNAL GENERATION
    # ------------------------------------------------------------------

    def generate_signals(self) -> list:
        """
        Generate BUY/SELL signals based on ST flip at S/R zone.
        """
        df = self._build_renko_df()

        # DEBUG
        print(f"DEBUG: Total bricks = {len(df)}")
        st_dir_temp = df['st_dir'].values
        print(f"DEBUG: ST dir counts = {pd.Series(st_dir_temp).value_counts().to_dict()}")
        print(f"DEBUG: ST flips red->green = {sum(1 for i in range(1, len(st_dir_temp)) if st_dir_temp[i - 1] == 1 and st_dir_temp[i] == -1)}")
        print(f"DEBUG: ST flips green->red = {sum(1 for i in range(1, len(st_dir_temp)) if st_dir_temp[i - 1] == -1 and st_dir_temp[i] == 1)}")

        # DEBUG S/R check at flip points
        last_sh_temp = df['last_swing_high'].values
        last_sl_temp = df['last_swing_low'].values
        sl_hist_temp = df['swing_lows_hist'].tolist()
        sh_hist_temp = df['swing_highs_hist'].tolist()
        rc_temp      = df['renko_close'].values
        rd_temp      = df['renko_dir'].values
        box_temp     = self.renko_box
        tol_temp     = self.sr_tolerance

        for i in range(1, len(st_dir_temp)):
            if st_dir_temp[i-1] == 1 and st_dir_temp[i] == -1 and rd_temp[i] == 1:
                close_t  = rc_temp[i]
                near_h   = not np.isnan(last_sl_temp[i]) and abs(close_t - last_sl_temp[i]) <= box_temp * tol_temp
                btl      = _trendline_value_at(sl_hist_temp[i], i, self.max_tl_bars)
                near_s   = btl is not None and abs(close_t - btl) <= box_temp * tol_temp
                n_swings = len(sl_hist_temp[i])
                print(f"  BUY flip i={i} close={close_t:.0f} last_sl={last_sl_temp[i]:.0f} near_h={near_h} btl={btl} near_s={near_s} swings={n_swings}")

        signals = []
        n = len(df)

        renko_close = df['renko_close'].values
        renko_dir   = df['renko_dir'].values
        st_dir      = df['st_dir'].values
        last_sh     = df['last_swing_high'].values
        last_sl     = df['last_swing_low'].values
        sh_hist     = df['swing_highs_hist'].tolist()
        sl_hist     = df['swing_lows_hist'].tolist()
        timestamps  = df['timestamp'].values

        box      = self.renko_box
        tol      = self.sr_tolerance
        max_bars = self.max_tl_bars

        current_direction = None
        prev_st_dir       = st_dir[0]

        prev_buy  = False
        prev_sell = False

        for i in range(1, n):
            ts    = str(pd.Timestamp(timestamps[i]).strftime('%Y-%m-%dT%H:%M:%S'))
            close = renko_close[i]
            r_dir = renko_dir[i]
            st    = st_dir[i]
            prev_st = prev_st_dir

            # ----------------------------------------------------------
            # TRENDLINE VALUES AT CURRENT BAR
            # ----------------------------------------------------------
            bearish_tl_val = _trendline_value_at(sh_hist[i], i, max_bars)
            bullish_tl_val = _trendline_value_at(sl_hist[i], i, max_bars)

            # ----------------------------------------------------------
            # EXIT: ST flip only
            # ----------------------------------------------------------
            # LONG EXIT: ST flips green->red + 1 red brick close
            if current_direction == 'long' and prev_st == -1 and st == 1 and r_dir == -1:
                exit_price = self._apply_slippage(close, 'long', is_entry=False)
                signals.append({
                    'signal_type' : 'EXIT',
                    'price'       : exit_price,
                    'timestamp'   : ts,
                    'sl_price'    : close - box,
                    'entry_type'  : '',
                    'exit_type'   : 'ST_FLIP_RED',
                    'direction'   : 'long',
                })
                current_direction = None

            # SHORT EXIT: ST flips red->green + 1 green brick close
            elif current_direction == 'short' and prev_st == 1 and st == -1 and r_dir == 1:
                exit_price = self._apply_slippage(close, 'short', is_entry=False)
                signals.append({
                    'signal_type' : 'EXIT',
                    'price'       : exit_price,
                    'timestamp'   : ts,
                    'sl_price'    : close + box,
                    'entry_type'  : '',
                    'exit_type'   : 'ST_FLIP_GREEN',
                    'direction'   : 'short',
                })
                current_direction = None

            # ----------------------------------------------------------
            # SUPPORT / RESISTANCE ZONE CHECK
            # ----------------------------------------------------------
            near_horizontal_support = (
                not np.isnan(last_sl[i])
                and abs(close - last_sl[i]) <= box * tol
            )
            near_sloped_support = (
                bullish_tl_val is not None
                and abs(close - bullish_tl_val) <= box * tol
            )
            near_support = near_horizontal_support or near_sloped_support

            near_horizontal_resistance = (
                not np.isnan(last_sh[i])
                and abs(close - last_sh[i]) <= box * tol
            )
            near_sloped_resistance = (
                bearish_tl_val is not None
                and abs(close - bearish_tl_val) <= box * tol
            )
            near_resistance = near_horizontal_resistance or near_sloped_resistance

            # ----------------------------------------------------------
            # SIGNAL CONDITIONS
            # ----------------------------------------------------------

            # BUY: ST flips red->green + near support + min 2 swing lows + green brick
            buy = (
                prev_st == 1 and st == -1
                and near_support
                and r_dir == 1
                and len(sl_hist[i]) >= 2
            )

            # SELL: ST flips green->red + near resistance + min 2 swing highs + red brick
            sell = (
                prev_st == -1 and st == 1
                and near_resistance
                and r_dir == -1
                and len(sh_hist[i]) >= 2
            )

            # ----------------------------------------------------------
            # RISING EDGE DEDUP
            # ----------------------------------------------------------
            buy_edge  = buy  and not prev_buy
            sell_edge = sell and not prev_sell

            # ----------------------------------------------------------
            # ENTRY SIGNALS
            # ----------------------------------------------------------
            if buy_edge and current_direction != 'long':
                entry_price = self._apply_slippage(close, 'long', is_entry=True)
                signals.append({
                    'signal_type' : 'ENTRY',
                    'price'       : entry_price,
                    'timestamp'   : ts,
                    'sl_price'    : close - box * 2,
                    'entry_type'  : 'BUY',
                    'exit_type'   : '',
                    'direction'   : 'long',
                })
                current_direction = 'long'

            elif sell_edge and current_direction != 'short':
                entry_price = self._apply_slippage(close, 'short', is_entry=True)
                signals.append({
                    'signal_type' : 'ENTRY',
                    'price'       : entry_price,
                    'timestamp'   : ts,
                    'sl_price'    : close + box * 2,
                    'entry_type'  : 'SELL',
                    'exit_type'   : '',
                    'direction'   : 'short',
                })
                current_direction = 'short'

            # ----------------------------------------------------------
            # UPDATE PREVIOUS FLAGS
            # ----------------------------------------------------------
            prev_buy    = buy
            prev_sell   = sell
            prev_st_dir = st

        return signals

