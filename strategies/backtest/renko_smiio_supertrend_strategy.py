# strategies/renko_smiio_supertrend_strategy.py
# Strategy: Renko + SMIIO + Supertrend
# Entry : SMIIO crossover + ST confirmation + 1 brick close in signal direction
# Exit  : ST flip + 1 brick close in exit direction

import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy
from indicators.renko import RenkoBuilder, SupertrendIndicator


# ===========================================================================
# SMIIO INDICATOR
# =====tree /F D:\crypto_trading_system======================================================================
def compute_smiio(closes: np.ndarray, short_len: int = 5, long_len: int = 20, signal_len: int = 5) -> tuple:
    n = len(closes)
    mom     = np.zeros(n)
    abs_mom = np.zeros(n)

    for i in range(1, n):
        mom[i]     = closes[i] - closes[i - 1]
        abs_mom[i] = abs(mom[i])

    def ema(arr, period):
        out = np.zeros(len(arr))
        k   = 2.0 / (period + 1)
        out[0] = arr[0]
        for i in range(1, len(arr)):
            out[i] = arr[i] * k + out[i - 1] * (1 - k)
        return out

    ema1_mom = ema(mom,      short_len)
    ema2_mom = ema(ema1_mom, long_len)
    ema1_abs = ema(abs_mom,  short_len)
    ema2_abs = ema(ema1_abs, long_len)

    smi    = np.where(ema2_abs != 0, ema2_mom / ema2_abs * 100.0, 0.0)
    signal = ema(smi, signal_len)

    return smi, signal


# ===========================================================================
# STRATEGY CLASS
# ===========================================================================
class RenkoSMIIOSupertrendStrategy(BaseStrategy):
    """
    Uses SupertrendIndicator from indicators/renko.py (same as RenkoReversal)
    st_dir: -1 = GREEN (bullish), +1 = RED (bearish)

    Entry Types
    -----------
    BUY_A  : SMIIO crosses up   + ST already GREEN + 1 green brick close
    BUY_B  : ST flips GREEN     + SMIIO already up + 1 green brick close
    SELL_A : SMIIO crosses down + ST already RED   + 1 red brick close
    SELL_B : ST flips RED       + SMIIO already down + 1 red brick close

    Exit
    ----
    ST flip + 1 brick close in exit direction

    Filter Parameters (disabled by default, reserved for future optimization)
    --------------------------------------------------------------------------
    smiio_avoid_entry_above : float  — skip entry if abs(smi) > threshold (0.0 = disabled)
    crossover_distance      : float  — min gap between smi and signal at crossover (0.0 = disabled)
    crossover_count_limit   : int    — block entry if consecutive small crossovers >= N (0 = disabled)
    """

    # -----------------------------------------------------------------------
    # __init__
    # -----------------------------------------------------------------------
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        super().__init__(data_dict=data_dict, lot_size=lot_size)

        symbol        = kwargs.get('symbol', 'BTCUSD')
        current_price = kwargs.get('current_price', None)

        # --- Core strategy parameters ---
        self.renko_box_pct = kwargs.get('renko_box_pct', 0.001)
        self.reference_price = kwargs.get('reference_price', None)
        self.renko_timeframe = kwargs.get('renko_timeframe', '2h')
        self.st_atr_length = kwargs.get('st_atr_length', 5)
        self.st_factor      = kwargs.get('st_factor',      2.0)
        self.smiio_shortlen = kwargs.get('smiio_shortlen', 10)
        self.smiio_longlen  = kwargs.get('smiio_longlen',  20)
        self.smiio_siglen   = kwargs.get('smiio_siglen',   3)
        self.slippage_usd   = kwargs.get('slippage_usd',   0.0)
        self.commission_pct = kwargs.get('commission_pct', 0.0)

        # --- Filter parameters (disabled by default) ---
        # Set value > 0 to activate when optimizing for sideways/ranging markets
        self.smiio_avoid_entry_above = kwargs.get('smiio_avoid_entry_above', 0.0)  # 0.0 = disabled
        self.crossover_distance      = kwargs.get('crossover_distance',      0.0)  # 0.0 = disabled
        self.crossover_count_limit   = kwargs.get('crossover_count_limit',   0)    # 0   = disabled

    # -----------------------------------------------------------------------
    # Abstract method implementations
    # -----------------------------------------------------------------------
    @property
    def optimization_params(self) -> dict:
        return {
            # --- Core parameters (active optimization) ---
            'renko_box_pct': {'default': 0.0020, 'min': 0.0010, 'max': 0.0040, 'step': 0.0005},
            'st_atr_length':  {'default': 5,    'min': 3,    'max': 14,   'step': 1},
            'st_factor':      {'default': 2.0,  'min': 1.0,  'max': 5.0,  'step': 0.5},
            'smiio_shortlen': {'default': 5,    'min': 3,    'max': 10,   'step': 1},
            'smiio_longlen':  {'default': 20,   'min': 10,   'max': 40,   'step': 5},

            # --- Filter parameters (reserved, not in active optimization) ---
            # Uncomment below to include in optimization for sideways market tuning
            # 'smiio_avoid_entry_above': {'default': 0.0, 'min': 0.2, 'max': 0.6, 'step': 0.1},
            # 'crossover_distance':      {'default': 0.0, 'min': 0.1, 'max': 2.5, 'step': 0.1},
            # 'crossover_count_limit':   {'default': 0,   'min': 1,   'max': 3,   'step': 1},
        }

    @property
    def required_timeframes(self) -> list:
        return [self.renko_timeframe]

    # -----------------------------------------------------------------------
    # Slippage helper
    # -----------------------------------------------------------------------
    def _apply_slippage(self, price: float, direction: str, is_entry: bool) -> float:
        slip = self.slippage_usd
        if direction == 'long':
            return price + slip if is_entry else price - slip
        else:
            return price - slip if is_entry else price + slip

    # -----------------------------------------------------------------------
    # Renko DataFrame builder
    # -----------------------------------------------------------------------
    def _build_renko_df(self) -> pd.DataFrame:
        tf = self.renko_timeframe
        df_tf = self._data.get(tf)
        if df_tf is None or len(df_tf) == 0:
            raise ValueError(f"Requires '{tf}' timeframe data")

        closes = df_tf['close'].values
        timestamps = (df_tf.index if isinstance(df_tf.index, pd.DatetimeIndex)
                      else pd.to_datetime(df_tf['timestamp']))

        current_price = closes[0] if len(closes) > 0 else 100000.0
        box_size = max(1, round((self.reference_price if self.reference_price else closes[0]) * self.renko_box_pct))
        builder = RenkoBuilder(box_size=box_size)
        renko_raw = builder.build(closes)
        if renko_raw is None or len(renko_raw) == 0:
            raise ValueError("RenkoBuilder produced no bricks")

        renko_raw['timestamp'] = renko_raw['bar_index'].apply(
            lambda idx: timestamps[idx] if idx < len(timestamps) else timestamps[-1]
        )
        return renko_raw

    # -----------------------------------------------------------------------
    # generate_signals  — MAIN LOGIC
    # -----------------------------------------------------------------------
    def generate_signals(self) -> list:
        df = self._build_renko_df()
        timestamps = df['timestamp'].values
        n = len(df)

        closes    = df['renko_close'].values
        renko_dir = df['renko_dir'].values
        current_price = closes[0] if len(closes) > 0 else 100000.0
        box = max(1, round((self.reference_price if self.reference_price else closes[0]) * self.renko_box_pct))

        # --- SupertrendIndicator ---
        st_ind = SupertrendIndicator(
            atr_period=self.st_atr_length,
            factor=self.st_factor,
        )
        df_st  = st_ind.calculate(df)
        st_dir = df_st['st_dir'].values

        # --- SMIIO ---
        smi, sig = compute_smiio(
            closes,
            short_len=self.smiio_shortlen,
            long_len=self.smiio_longlen,
            signal_len=self.smiio_siglen,
        )

        # --- Signal loop ---
        signals           = []
        current_direction = None
        pending           = None
        pending_set_bar   = -1
        last_exit_ts      = None

        for i in range(1, n):
            ts    = str(pd.Timestamp(timestamps[i]).strftime('%Y-%m-%dT%H:%M:%S'))
            close = closes[i]
            r_dir = renko_dir[i]
            st    = st_dir[i]
            prev_st = st_dir[i - 1]

            smi_cross_up   = smi[i] > sig[i] and smi[i - 1] <= sig[i - 1]
            smi_cross_down = smi[i] < sig[i] and smi[i - 1] >= sig[i - 1]
            st_flip_green  = prev_st == 1  and st == -1
            st_flip_red    = prev_st == -1 and st == 1
            smi_above      = smi[i] > sig[i]
            smi_below      = smi[i] < sig[i]

            # FIX 2: Cancel pending if not confirmed within 1 bar
            if pending is not None and i > pending_set_bar + 1:
                pending = None
                pending_set_bar = -1

            # ----------------------------------------------------------
            # EXIT: ST flip confirmed
            # ----------------------------------------------------------
            if current_direction == 'long' and st_flip_red and r_dir == -1:
                signals.append({
                    'signal_type': 'EXIT',
                    'price':       self._apply_slippage(close, 'long', False),
                    'timestamp':   ts,
                    'sl_price':    close - box,
                    'entry_type':  '',
                    'exit_type':   'ST_FLIP_RED',
                    'direction':   'long',
                })
                current_direction = None
                pending           = None
                pending_set_bar   = -1
                last_exit_ts      = ts

            elif current_direction == 'short' and st_flip_green and r_dir == 1:
                signals.append({
                    'signal_type': 'EXIT',
                    'price':       self._apply_slippage(close, 'short', False),
                    'timestamp':   ts,
                    'sl_price':    close + box,
                    'entry_type':  '',
                    'exit_type':   'ST_FLIP_GREEN',
                    'direction':   'short',
                })
                current_direction = None
                pending           = None
                pending_set_bar   = -1
                last_exit_ts      = ts

            # ----------------------------------------------------------
            # SET PENDING — FIX 1: skip same bar as exit
            #             — FIX 3: single if/elif chain
            # ----------------------------------------------------------
            if current_direction is None:

                if smi_cross_up and st == -1:
                    pending = {'side': 'long', 'entry_type': 'BUY_A'}
                    pending_set_bar = i

                elif st_flip_green and smi_above:
                    pending = {'side': 'long', 'entry_type': 'BUY_B'}
                    pending_set_bar = i

                elif smi_cross_down and st == 1:
                    pending = {'side': 'short', 'entry_type': 'SELL_A'}
                    pending_set_bar = i

                elif st_flip_red and smi_below:
                    pending = {'side': 'short', 'entry_type': 'SELL_B'}
                    pending_set_bar = i

            # ----------------------------------------------------------
            # EXECUTE PENDING
            # ----------------------------------------------------------
            if pending is not None and current_direction is None:
                side = pending['side']

                if side == 'long' and st == 1:
                    pending = None
                    pending_set_bar = -1

                elif side == 'short' and st == -1:
                    pending = None
                    pending_set_bar = -1

                elif side == 'long' and r_dir == 1:
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price':       self._apply_slippage(close, 'long', True),
                        'timestamp':   ts,
                        'sl_price':    close - box * 2,
                        'entry_type':  pending['entry_type'],
                        'exit_type':   '',
                        'direction':   'long',
                    })
                    current_direction = 'long'
                    pending           = None
                    pending_set_bar   = -1

                elif side == 'short' and r_dir == -1:
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price':       self._apply_slippage(close, 'short', True),
                        'timestamp':   ts,
                        'sl_price':    close + box * 2,
                        'entry_type':  pending['entry_type'],
                        'exit_type':   '',
                        'direction':   'short',
                    })
                    current_direction = 'short'
                    pending           = None
                    pending_set_bar   = -1

        return signals
