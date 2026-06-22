# strategies/renko_options_strategy.py
# Renko Options Strategy - 3 modes
# Inherits from base_strategy.py
# Signal logic: 4 types (BUY_A, BUY_B, SELL_A, SELL_B)
# Exit: Supertrend flip ONLY

import numpy as np
import pandas as pd
from strategies.base_strategy import BaseStrategy
from indicators.renko import _trendline_value_at


class RenkoOptionsStrategy(BaseStrategy):
    """
    Renko-based options strategy with 3 selectable modes.

    Modes
    -----
    1 : Momentum Hedged   - Future + Short OTM1 + Long OTM4
    2 : Future + DTE-0    - Future + daily DTE-0 income
    3 : Deep ITM Covered  - Deep ITM option + daily DTE-0 sells

    Signal Types
    ------------
    BUY_A  : Bearish trendline breakout above + ST GREEN + green brick
    BUY_B  : Near bullish sloped TL OR near horizontal support + ST GREEN + green brick
    SELL_A : Bullish trendline breakout below + ST RED + red brick
    SELL_B : Near bearish sloped TL OR near horizontal resistance + ST RED + red brick

    Exit
    ----
    Supertrend flip ONLY (independent of trendline conditions)
    GREEN -> RED exits LONG
    RED -> GREEN exits SHORT
    """

    def __init__(self, config: dict):
        # BaseStrategy requires data_dict and lot_size
        # We pass empty data_dict because renko_df is passed directly
        # to generate_signals() - we do not use self._data here
        super().__init__(
            data_dict = {},
            lot_size  = config.get('future_lots', 100)
        )

        # Strategy mode
        self.mode = config.get('mode', 1)

        # Renko settings
        self.renko_box   = config.get('renko_box', 200.0)
        self.sr_tolerance = config.get('sr_tolerance', 0.5)
        self.max_tl_bars  = config.get('max_tl_bars', 50)

        # Position sizing
        self.future_lots = config.get('future_lots', 100)
        self.option_lots = config.get('option_lots', 1)

        # Slippage (USD per side)
        self.slippage_usd = config.get('slippage_usd', 0.0)

        # Options parameters (Mode 1)
        self.otm1_premium  = config.get('otm1_premium', 1.0)
        self.otm4_premium  = config.get('otm4_premium', 1.0)
        self.trade_dte     = config.get('trade_dte', 7)
        self.decay_pct     = config.get('decay_pct', 80.0)

        # Options parameters (Mode 2 / 3)
        self.dte0_daily_premium = config.get('dte0_daily_premium', 1.0)
        self.deep_itm_premium   = config.get('deep_itm_premium', 1.0)

        # Commission rate
        self.commission_pc = config.get('commission_pct', 0.0)

    # ------------------------------------------------------------------
    # ABSTRACT METHOD IMPLEMENTATIONS (required by BaseStrategy)
    # ------------------------------------------------------------------

    @property
    def required_timeframes(self) -> list:
        """Renko strategy builds its own bars from 2H CSV - no timeframe needed."""
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
    # OPTIONS P&L HELPERS
    # ------------------------------------------------------------------

    def _theta_decay_exit_premium(self, entry_premium: float, hold_days: int) -> float:
        decay_ratio  = min(hold_days / max(self.trade_dte, 1), 1.0)
        return entry_premium - (entry_premium * (self.decay_pct / 100.0) * decay_ratio)

    def _calc_options_pnl(self, direction: str, hold_days: int) -> float:
        commission_per_leg = self.commission_pc / 100.0

        if self.mode == 1:
            otm1_exit  = self._theta_decay_exit_premium(self.otm1_premium, hold_days)
            otm1_pnl   = (self.otm1_premium - otm1_exit) * self.option_lots
            otm1_comm  = (self.otm1_premium + otm1_exit) * commission_per_leg * self.option_lots

            otm4_exit  = self._theta_decay_exit_premium(self.otm4_premium, hold_days)
            otm4_pnl   = (otm4_exit - self.otm4_premium) * self.option_lots
            otm4_comm  = (self.otm4_premium + otm4_exit) * commission_per_leg * self.option_lots

            return otm1_pnl + otm4_pnl - otm1_comm - otm4_comm

        elif self.mode == 2:
            daily_income = self.dte0_daily_premium * hold_days * self.option_lots
            comm         = self.dte0_daily_premium * commission_per_leg * hold_days * self.option_lots
            return daily_income - comm

        elif self.mode == 3:
            daily_income = self.dte0_daily_premium * hold_days * self.option_lots
            comm         = self.dte0_daily_premium * commission_per_leg * hold_days * self.option_lots
            return daily_income - comm

        return 0.0

    # ------------------------------------------------------------------
    # SIGNAL GENERATION
    # ------------------------------------------------------------------

    def generate_signals(self, df: pd.DataFrame = None) -> list:
        """
        Generate trading signals from a prepared Renko DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Renko DataFrame with columns:
            renko_close, renko_dir, st_dir,
            last_swing_high, last_swing_low,
            swing_highs_hist, swing_lows_hist,
            timestamp

        Returns
        -------
        List of signal dicts compatible with TradeBuilder.
        """
        # If called with no args (BaseStrategy compatibility), use stored data
        if df is None:
            raise ValueError(
                "RenkoOptionsStrategy.generate_signals() requires a renko_df argument. "
                "Call as: strategy.generate_signals(renko_df)"
            )

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

        prev_buy_a  = False
        prev_buy_b  = False
        prev_sell_a = False
        prev_sell_b = False

        for i in range(1, n):
            ts    = str(pd.Timestamp(timestamps[i]).strftime('%Y-%m-%dT%H:%M:%S'))
            close = renko_close[i]
            r_dir = renko_dir[i]
            st    = st_dir[i]
            prev_st = prev_st_dir

            # ----------------------------------------------------------
            # EXIT: Supertrend flip ONLY
            # ----------------------------------------------------------
            if current_direction == 'long' and prev_st == -1 and st == 1:
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

            elif current_direction == 'short' and prev_st == 1 and st == -1:
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
            # TRENDLINE VALUES AT CURRENT BAR
            # ----------------------------------------------------------
            bearish_tl_val  = _trendline_value_at(sh_hist[i],     i,     max_bars)
            bullish_tl_val  = _trendline_value_at(sl_hist[i],     i,     max_bars)
            bearish_tl_prev = _trendline_value_at(sh_hist[i - 1], i - 1, max_bars)
            bullish_tl_prev = _trendline_value_at(sl_hist[i - 1], i - 1, max_bars)
            prev_close      = renko_close[i - 1]

            # ----------------------------------------------------------
            # SIGNAL CONDITIONS
            # ----------------------------------------------------------

            # BUY_A: close crosses ABOVE bearish trendline + ST GREEN + green brick
            buy_a = (
                bearish_tl_val  is not None
                and bearish_tl_prev is not None
                and close      >  bearish_tl_val
                and prev_close <= bearish_tl_prev
                and st    == -1
                and r_dir ==  1
            )

            # BUY_B: near bullish sloped TL OR near horizontal support
            #        + ST GREEN + green brick + min 2 swing lows
            near_horizontal_support = (
                not np.isnan(last_sl[i])
                and abs(close - last_sl[i]) <= box * tol
            )
            near_sloped_support = (
                bullish_tl_val is not None
                and abs(close - bullish_tl_val) <= box * tol
            )
            buy_b = (
                (near_horizontal_support or near_sloped_support)
                and st    == -1
                and r_dir ==  1
                and len(sl_hist[i]) >= 2
            )

            # SELL_A: close crosses BELOW bullish trendline + ST RED + red brick
            sell_a = (
                bullish_tl_val  is not None
                and bullish_tl_prev is not None
                and close      <  bullish_tl_val
                and prev_close >= bullish_tl_prev
                and st    ==  1
                and r_dir == -1
            )

            # SELL_B: near bearish sloped TL OR near horizontal resistance
            #         + ST RED + red brick + min 2 swing highs
            near_horizontal_resistance = (
                not np.isnan(last_sh[i])
                and abs(close - last_sh[i]) <= box * tol
            )
            near_sloped_resistance = (
                bearish_tl_val is not None
                and abs(close - bearish_tl_val) <= box * tol
            )
            sell_b = (
                (near_horizontal_resistance or near_sloped_resistance)
                and st    ==  1
                and r_dir == -1
                and len(sh_hist[i]) >= 2
            )

            # ----------------------------------------------------------
            # RISING EDGE DEDUP
            # ----------------------------------------------------------
            buy_a_edge  = buy_a  and not prev_buy_a
            buy_b_edge  = buy_b  and not prev_buy_b
            sell_a_edge = sell_a and not prev_sell_a
            sell_b_edge = sell_b and not prev_sell_b

            # ----------------------------------------------------------
            # ENTRY SIGNALS
            # ----------------------------------------------------------
            if (buy_a_edge or buy_b_edge) and current_direction != 'long':
                entry_type  = 'BUY_A' if buy_a_edge else 'BUY_B'
                entry_price = self._apply_slippage(close, 'long', is_entry=True)
                signals.append({
                    'signal_type' : 'ENTRY',
                    'price'       : entry_price,
                    'timestamp'   : ts,
                    'sl_price'    : close - box * 2,
                    'entry_type'  : entry_type,
                    'exit_type'   : '',
                    'direction'   : 'long',
                })
                current_direction = 'long'

            elif (sell_a_edge or sell_b_edge) and current_direction != 'short':
                entry_type  = 'SELL_A' if sell_a_edge else 'SELL_B'
                entry_price = self._apply_slippage(close, 'short', is_entry=True)
                signals.append({
                    'signal_type' : 'ENTRY',
                    'price'       : entry_price,
                    'timestamp'   : ts,
                    'sl_price'    : close + box * 2,
                    'entry_type'  : entry_type,
                    'exit_type'   : '',
                    'direction'   : 'short',
                })
                current_direction = 'short'

            # ----------------------------------------------------------
            # UPDATE PREVIOUS FLAGS
            # ----------------------------------------------------------
            prev_buy_a  = buy_a
            prev_buy_b  = buy_b
            prev_sell_a = sell_a
            prev_sell_b = sell_b
            prev_st_dir = st

        return signals

    # ------------------------------------------------------------------
    # OPTIONS P&L ACCESSOR
    # ------------------------------------------------------------------

    def get_options_pnl(self, direction: str, hold_days: int) -> float:
        return self._calc_options_pnl(direction, hold_days)
