# strategies/renko_reversal_strategy.py
# Strategy 2: Renko Reverse at S/R
# Entry: ST FLIP at support/resistance zone
# Exit:  ST flip only (same as Strategy 1)

import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy
from indicators.renko import _trendline_value_at, RenkoBuilder, SupertrendIndicator, SwingDetector


class RenkoReversalStrategy(BaseStrategy):
    """
    Renko Reversal Strategy - Reverse at S/R only.

    Signal Types
    ------------
    BUY  : ST flips red->green + recent low touched support zone + min 2 swing lows + 1 green brick close
    SELL : ST flips green->red + recent high touched resistance zone + min 2 swing highs + 1 red brick close

    S/R Zone Check
    --------------
    At ST flip bar, look back 'sr_lookback' bricks to find the recent low/high.
    Check if that recent low/high touched the S/R level within sr_tolerance boxes.
    This correctly captures: price touched support/resistance BEFORE the ST flip confirmed the bounce.

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
        self.renko_box_pct = kwargs.get('renko_box_pct', 0.0010)
        self.reference_price = kwargs.get('reference_price', None)
        self.renko_timeframe = kwargs.get('renko_timeframe', '30m')
        self.last_exit_ts = None
        self.sr_tolerance = kwargs.get('sr_tolerance', 1.5)   # multiplier of box_size - auto-scales per symbol
        self.sr_lookback  = kwargs.get('sr_lookback', 5)       # bricks to look back for S/R touch before flip
        self.max_tl_bars  = kwargs.get('max_tl_bars', 50)
        self.st_atr_length = kwargs.get('st_atr_length', 10)
        self.st_factor     = kwargs.get('st_factor', 2.0)

        # Slippage (USD per side)
        self.slippage_usd = kwargs.get('slippage_usd', 0.0)

        # Commission rate
        self.commission_pc = kwargs.get('commission_pct', 0.0)

    # ------------------------------------------------------------------
    # ABSTRACT METHOD IMPLEMENTATIONS
    # ------------------------------------------------------------------

    @property
    def optimization_params(self) -> dict:
        return {
            'box_pct': {'default': 0.010, 'min': 0.005, 'max': 0.020, 'step': 0.001},
            'st_atr_len': {'default': 5, 'min': 3, 'max': 14, 'step': 1},
            'st_factor': {'default': 4.0, 'min': 2.0, 'max': 6.0, 'step': 0.5},
            'sr_tolerance': {'default': 1.5, 'min': 0.5, 'max': 3.0, 'step': 0.5},
            'sr_lookback': {'default': 5, 'min': 3, 'max': 10, 'step': 1},
        }

    @property
    def required_timeframes(self) -> list:
        return [self.renko_timeframe]  # CORRECT

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
        df_2h = self._data.get(self.renko_timeframe)
        if df_2h is None or len(df_2h) == 0:
            raise ValueError("RenkoReversalStrategy requires timeframe data in data_dict")

        closes     = df_2h['close'].values
        timestamps = df_2h.index if isinstance(df_2h.index, pd.DatetimeIndex) else pd.to_datetime(df_2h['timestamp'])

        # Build Renko bricks
        current_price = self._data[self.renko_timeframe]['close'].iloc[-1]
        box_size = max(1, round((self.reference_price if self.reference_price else current_price) * self.renko_box_pct))
        builder   = RenkoBuilder(box_size=box_size)
        renko_raw = builder.build(closes)

        if renko_raw is None or len(renko_raw) == 0:
            raise ValueError("RenkoBuilder produced no bricks - check box size or data range")

        # Map timestamps
        renko_raw['timestamp'] = renko_raw['bar_index'].apply(
            lambda idx: timestamps[idx] if idx < len(timestamps) else timestamps[-1]
        )

        # Add Supertrend
        st_indicator = SupertrendIndicator(atr_period=self.st_atr_length, factor=self.st_factor)
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

        S/R zone logic:
        - At ST flip bar, look back sr_lookback bricks
        - Find recent_low  = min renko_close in lookback window (for BUY)
        - Find recent_high = max renko_close in lookback window (for SELL)
        - Check if recent_low touched support zone (within sr_tolerance boxes)
        - Check if recent_high touched resistance zone (within sr_tolerance boxes)
        - This captures: price touched S/R BEFORE the flip confirmed the bounce/rejection
        """
        df = self._build_renko_df()

        # ------------------------------------------------------------------
        # MAIN SIGNAL LOOP
        # ------------------------------------------------------------------
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

        current_price = self._data[self.renko_timeframe]['close'].iloc[-1]
        box      = max(1, round((self.reference_price if self.reference_price else current_price) * self.renko_box_pct))
        max_bars = self.max_tl_bars
        lookback = self.sr_lookback

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
                self.last_exit_ts = ts

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
            # S/R ZONE CHECK
            # Look back sr_lookback bricks to find recent low/high
            # Check if recent low/high touched the S/R level before the flip
            # This is correct because: price touches S/R first, THEN ST flips
            # ----------------------------------------------------------
            sr_zone  = box * self.sr_tolerance   # BTC: 200*1.5=300 USD, ETH: 10*1.5=15 USD
            lb_start = max(0, i - lookback)

            # Recent low = lowest close in lookback window (for BUY support check)
            recent_low  = np.min(renko_close[lb_start:i + 1])
            # Recent high = highest close in lookback window (for SELL resistance check)
            recent_high = np.max(renko_close[lb_start:i + 1])

            # BUY: recent low touched support zone
            # (price came down to support, touched it, then bounced - ST flip confirms bounce)
            near_horizontal_support = (
                not np.isnan(last_sl[i])
                and last_sl[i] - sr_zone <= recent_low <= last_sl[i] + sr_zone
            )
            near_sloped_support = (
                bullish_tl_val is not None
                and bullish_tl_val - sr_zone <= recent_low <= bullish_tl_val + sr_zone
            )
            near_support = near_horizontal_support or near_sloped_support

            # SELL: recent high touched resistance zone
            # (price came up to resistance, touched it, then rejected - ST flip confirms rejection)
            near_horizontal_resistance = (
                not np.isnan(last_sh[i])
                and last_sh[i] - sr_zone <= recent_high <= last_sh[i] + sr_zone
            )
            near_sloped_resistance = (
                bearish_tl_val is not None
                and bearish_tl_val - sr_zone <= recent_high <= bearish_tl_val + sr_zone
            )
            near_resistance = near_horizontal_resistance or near_sloped_resistance

            # ----------------------------------------------------------
            # SIGNAL CONDITIONS
            # ----------------------------------------------------------

            # BUY: ST flips red->green + recent low near support + min 2 swing lows + green brick
            buy = (
                prev_st == 1 and st == -1
                and near_support
                and r_dir == 1
                and len(sl_hist[i]) >= 2
            )

            # SELL: ST flips green->red + recent high near resistance + min 2 swing highs + red brick
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
