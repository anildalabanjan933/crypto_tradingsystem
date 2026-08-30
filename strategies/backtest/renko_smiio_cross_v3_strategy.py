# strategies/backtest/renko_smiio_cross_v3_strategy.py
# TEST VARIANT (S4V3) of S4 - Renko + SMIIO CROSSOVER ONLY (no brick-direction, no Supertrend)
# Entry LONG  : SMIIO crosses ABOVE Signal
# Exit  LONG  : SMIIO crosses BELOW Signal
# Entry SHORT : SMIIO crosses BELOW Signal
# Exit  SHORT : SMIIO crosses ABOVE Signal
# Renko is still used for underlying brick construction/price series only -
# brick DIRECTION is NOT used as a trade-decision input.
# ISOLATED FILE - does not modify original S4 or S4V2 in any way.

import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy
from indicators.renko import RenkoBuilder


# ===========================================================================
# SMIIO INDICATOR (identical to original S4)
# ===========================================================================
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
class RenkoSMIIOCrossV3Strategy(BaseStrategy):
    """
    TEST VARIANT (S4V3) of RenkoSMIIOSupertrendStrategy (S4).

    ONLY CHANGE: trade decision = SMIIO/Signal crossover alone.
    Renko brick direction and Supertrend are NOT used for entry/exit.
    BUY_A/BUY_B/SELL_A/SELL_B confirmation logic is removed.

    LONG  Entry = SMIIO crosses ABOVE Signal
    LONG  Exit  = SMIIO crosses BELOW Signal
    SHORT Entry = SMIIO crosses BELOW Signal
    SHORT Exit  = SMIIO crosses ABOVE Signal

    No same-bar exit -> new entry (same protection as original S4).
    """

    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        super().__init__(data_dict=data_dict, lot_size=lot_size)

        # --- Core strategy parameters (identical source/meaning as original S4) ---
        self.renko_box_pct   = kwargs.get('renko_box_pct', 0.001)
        self.reference_price = kwargs.get('reference_price', None)
        self.renko_timeframe = kwargs.get('renko_timeframe', '2h')
        self.smiio_shortlen  = kwargs.get('smiio_shortlen', 10)
        self.smiio_longlen   = kwargs.get('smiio_longlen',  20)
        self.smiio_siglen    = kwargs.get('smiio_siglen',   3)
        self.slippage_usd    = kwargs.get('slippage_usd',   0.0)
        self.commission_pct  = kwargs.get('commission_pct', 0.0)

    # -----------------------------------------------------------------------
    @property
    def optimization_params(self) -> dict:
        return {
            'renko_box_pct':  {'default': 0.0020, 'min': 0.0010, 'max': 0.0040, 'step': 0.0005},
            'smiio_shortlen': {'default': 10,   'min': 3,    'max': 20,   'step': 1},
            'smiio_longlen':  {'default': 20,   'min': 10,   'max': 40,   'step': 5},
            'smiio_siglen':   {'default': 3,    'min': 2,    'max': 9,    'step': 1},
        }

    @property
    def required_timeframes(self) -> list:
        return [self.renko_timeframe]

    # -----------------------------------------------------------------------
    def _apply_slippage(self, price: float, direction: str, is_entry: bool) -> float:
        slip = self.slippage_usd
        if direction == 'long':
            return price + slip if is_entry else price - slip
        else:
            return price - slip if is_entry else price + slip

    # -----------------------------------------------------------------------
    # Renko DataFrame builder - IDENTICAL to original S4
    # -----------------------------------------------------------------------
    def _build_renko_df(self) -> pd.DataFrame:
        tf = self.renko_timeframe
        df_tf = self._data.get(tf)
        if df_tf is None or len(df_tf) == 0:
            raise ValueError(f"Requires '{tf}' timeframe data")

        closes = df_tf['close'].values
        timestamps = (df_tf.index if isinstance(df_tf.index, pd.DatetimeIndex)
                      else pd.to_datetime(df_tf['timestamp']))

        box_size = max(1, round((self.reference_price if self.reference_price else closes[0]) * self.renko_box_pct))
        builder = RenkoBuilder(box_size=box_size)
        renko_raw = builder.build(closes)
        if renko_raw is None or len(renko_raw) == 0:
            raise ValueError("RenkoBuilder produced no bricks")

        _ts_values = timestamps.values if hasattr(timestamps, 'values') else np.asarray(timestamps)
        _idx_arr = renko_raw['bar_index'].values.copy()
        _max_idx = len(_ts_values) - 1
        _idx_arr[_idx_arr > _max_idx] = _max_idx
        renko_raw['timestamp'] = _ts_values[_idx_arr]
        return renko_raw

    # -----------------------------------------------------------------------
    # generate_signals - MAIN LOGIC (SMIIO CROSSOVER ONLY)
    # -----------------------------------------------------------------------
    def generate_signals(self) -> list:
        df = self._build_renko_df()
        timestamps = df['timestamp'].values
        n = len(df)

        closes = df['renko_close'].values
        box = max(1, round((self.reference_price if self.reference_price else closes[0]) * self.renko_box_pct))

        # --- SMIIO (identical calc/params to original S4) ---
        smi, sig = compute_smiio(
            closes,
            short_len=self.smiio_shortlen,
            long_len=self.smiio_longlen,
            signal_len=self.smiio_siglen,
        )

        signals = []
        current_direction = None

        _ts_strings = [pd.Timestamp(t).strftime('%Y-%m-%dT%H:%M:%S') for t in timestamps]
        for i in range(1, n):
            ts    = _ts_strings[i]
            close = closes[i]

            smi_cross_up   = smi[i] > sig[i] and smi[i - 1] <= sig[i - 1]
            smi_cross_down = smi[i] < sig[i] and smi[i - 1] >= sig[i - 1]

            just_exited = False

            # ----------------------------------------------------------
            # EXIT: pure SMIIO/Signal crossover only
            # ----------------------------------------------------------
            if current_direction == 'long' and smi_cross_down:
                signals.append({
                    'signal_type': 'EXIT',
                    'price':       self._apply_slippage(close, 'long', False),
                    'timestamp':   ts,
                    'sl_price':    close - box,
                    'entry_type':  '',
                    'exit_type':   'SMIIO_CROSS_DOWN',
                    'direction':   'long',
                })
                current_direction = None
                just_exited = True

            elif current_direction == 'short' and smi_cross_up:
                signals.append({
                    'signal_type': 'EXIT',
                    'price':       self._apply_slippage(close, 'short', False),
                    'timestamp':   ts,
                    'sl_price':    close + box,
                    'entry_type':  '',
                    'exit_type':   'SMIIO_CROSS_UP',
                    'direction':   'short',
                })
                current_direction = None
                just_exited = True

            # ----------------------------------------------------------
            # ENTRY: pure SMIIO/Signal crossover only
            # No same-bar exit -> new entry (skip if we just exited this bar)
            # ----------------------------------------------------------
            if current_direction is None and not just_exited:
                if smi_cross_up:
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price':       self._apply_slippage(close, 'long', True),
                        'timestamp':   ts,
                        'sl_price':    close - box * 2,
                        'entry_type':  'SMIIO_CROSS_UP',
                        'exit_type':   '',
                        'direction':   'long',
                    })
                    current_direction = 'long'

                elif smi_cross_down:
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price':       self._apply_slippage(close, 'short', True),
                        'timestamp':   ts,
                        'sl_price':    close + box * 2,
                        'entry_type':  'SMIIO_CROSS_DOWN',
                        'exit_type':   '',
                        'direction':   'short',
                    })
                    current_direction = 'short'

        return signals
