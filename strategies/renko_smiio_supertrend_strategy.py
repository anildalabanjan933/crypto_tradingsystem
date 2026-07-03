# strategies/renko_smiio_supertrend_strategy.py
# Strategy: Renko + SMIIO + Supertrend
# Entry : SMIIO crossover + ST confirmation + 1 brick close in signal direction
# Exit  : ST flip + 1 brick close in exit direction

import numpy as np
import pandas as pd
from strategies.base_strategy import BaseStrategy
from indicators.renko import RenkoBuilder, SupertrendIndicator
from config.symbol_config import get_renko_box_size


# ===========================================================================
# SMIIO INDICATOR
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
    """

    # -----------------------------------------------------------------------
    # __init__
    # -----------------------------------------------------------------------
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        super().__init__(data_dict=data_dict, lot_size=lot_size)

        symbol        = kwargs.get('symbol', 'BTCUSD')
        current_price = kwargs.get('current_price', None)
        self.renko_box      = kwargs.get('renko_box') or get_renko_box_size(symbol, current_price)
        self.st_atr_length  = kwargs.get('st_atr_length',  5)
        self.st_factor      = kwargs.get('st_factor',      2.0)
        self.smiio_shortlen = kwargs.get('smiio_shortlen', 5)
        self.smiio_longlen  = kwargs.get('smiio_longlen',  20)
        self.smiio_siglen   = kwargs.get('smiio_siglen',   5)
        self.slippage_usd   = kwargs.get('slippage_usd',   0.0)
        self.commission_pct = kwargs.get('commission_pct', 0.0)

    # -----------------------------------------------------------------------
    # Abstract method implementations
    # -----------------------------------------------------------------------
    @property
    def optimization_params(self) -> dict:
        return {
            'renko_box':      {'default': 200,  'min': 100,  'max': 500,  'step': 50},
            'st_atr_length':  {'default': 5,    'min': 3,    'max': 14,   'step': 1},
            'st_factor':      {'default': 2.0,  'min': 1.0,  'max': 5.0,  'step': 0.5},
            'smiio_shortlen': {'default': 5,    'min': 3,    'max': 10,   'step': 1},
            'smiio_longlen':  {'default': 20,   'min': 10,   'max': 40,   'step': 5},
        }

    @property
    def required_timeframes(self) -> list:
        return ['2H']

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
        df_2h = self._data.get('2H')
        if df_2h is None or len(df_2h) == 0:
            raise ValueError("Requires '2H' timeframe data")

        closes     = df_2h['close'].values
        timestamps = (df_2h.index if isinstance(df_2h.index, pd.DatetimeIndex)
                      else pd.to_datetime(df_2h['timestamp']))

        builder   = RenkoBuilder(box_size=self.renko_box)
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
        box = self.renko_box

        closes = df['renko_close'].values
        renko_dir = df['renko_dir'].values

        # --- SupertrendIndicator (same as RenkoReversal) ---
        # st_dir: -1 = GREEN (bullish), +1 = RED (bearish)
        st_ind = SupertrendIndicator(
            atr_period=self.st_atr_length,
            factor=self.st_factor,
        )
        df_st = st_ind.calculate(df)
        st_dir = df_st['st_dir'].values

        # --- SMIIO ---
        smi, sig = compute_smiio(
            closes,
            short_len=self.smiio_shortlen,
            long_len=self.smiio_longlen,
            signal_len=self.smiio_siglen,
        )

        # --- ST-DEBUG ---
        debug_dates = {'2026-05-04'}
        print(f"\n[ST-DEBUG] Total Renko bricks = {n}")
        print(f"[ST-DEBUG] renko_box used = {self.renko_box:.2f}")
        for i in range(min(5, n)):
            ts = pd.Timestamp(timestamps[i])
            print(f"  bar={i} ts={ts} close={closes[i]:.0f} "
                  f"st_upper={df_st['st_upper'].values[i]:.0f} "
                  f"st_lower={df_st['st_lower'].values[i]:.0f} "
                  f"st={st_dir[i]}")
        for i in range(1, n):
            ts = pd.Timestamp(timestamps[i])
            if ts.strftime('%Y-%m-%d') in debug_dates:
                print(f"  bar={i} ts={ts} close={closes[i]:.0f} "
                      f"st_upper={df_st['st_upper'].values[i]:.0f} "
                      f"st_lower={df_st['st_lower'].values[i]:.0f} "
                      f"smi={smi[i]:.4f} sig={sig[i]:.4f} "
                      f"smi_cross={'UP' if smi[i] > sig[i] and smi[i - 1] <= sig[i - 1] else 'DN' if smi[i] < sig[i] and smi[i - 1] >= sig[i - 1] else '-'} "
                      f"st={st_dir[i]} prev_st={st_dir[i - 1]} r_dir={renko_dir[i]}")

        # --- Signal loop ---
        # st_dir: -1 = GREEN (bullish), +1 = RED (bearish)
        signals = []
        current_direction = None
        pending = None

        for i in range(1, n):
            ts = str(pd.Timestamp(timestamps[i]).strftime('%Y-%m-%dT%H:%M:%S'))
            close = closes[i]
            r_dir = renko_dir[i]
            st = st_dir[i]
            prev_st = st_dir[i - 1]

            smi_cross_up   = smi[i] > sig[i] and smi[i - 1] <= sig[i - 1]
            smi_cross_down = smi[i] < sig[i] and smi[i - 1] >= sig[i - 1]
            st_flip_green  = prev_st == 1 and st == -1   # RED -> GREEN
            st_flip_red    = prev_st == -1 and st == 1   # GREEN -> RED
            smi_above      = smi[i] > sig[i]
            smi_below      = smi[i] < sig[i]

            # ----------------------------------------------------------
            # EXIT: ST flip confirmed — execute at current bar (i)
            # ----------------------------------------------------------
            if current_direction == 'long' and st_flip_red and r_dir == -1:
                signals.append({
                    'signal_type': 'EXIT',
                    'price': self._apply_slippage(close, 'long', False),
                    'timestamp': ts,
                    'sl_price': close - box,
                    'entry_type': '',
                    'exit_type': 'ST_FLIP_RED',
                    'direction': 'long',
                })
                current_direction = None
                pending = None

            elif current_direction == 'short' and st_flip_green and r_dir == 1:
                signals.append({
                    'signal_type': 'EXIT',
                    'price': self._apply_slippage(close, 'short', False),
                    'timestamp': ts,
                    'sl_price': close + box,
                    'entry_type': '',
                    'exit_type': 'ST_FLIP_GREEN',
                    'direction': 'short',
                })
                current_direction = None
                pending = None

            # ----------------------------------------------------------
            # SET PENDING on crossover or ST flip (no position open)
            # ----------------------------------------------------------
            if current_direction is None:

                # BUY_A: SMIIO crosses up + ST already GREEN
                if smi_cross_up and st == -1:
                    pending = {'side': 'long', 'entry_type': 'BUY_A'}

                # BUY_B: ST flips GREEN + SMIIO already above signal
                elif st_flip_green and smi_above:
                    pending = {'side': 'long', 'entry_type': 'BUY_B'}

                # SELL_A: SMIIO crosses down + ST already RED
                if smi_cross_down and st == 1:
                    pending = {'side': 'short', 'entry_type': 'SELL_A'}

                # SELL_B: ST flips RED + SMIIO already below signal
                elif st_flip_red and smi_below:
                    pending = {'side': 'short', 'entry_type': 'SELL_B'}

            # ----------------------------------------------------------
            # EXECUTE PENDING: confirmation brick closes in signal direction
            # entry executes at current bar (i)
            # ----------------------------------------------------------
            if pending is not None and current_direction is None:
                side = pending['side']

                # Cancel stale pending if ST flips against it
                if side == 'long' and st == 1:
                    pending = None
                elif side == 'short' and st == -1:
                    pending = None

                elif side == 'long' and r_dir == 1:
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price': self._apply_slippage(close, 'long', True),
                        'timestamp': ts,
                        'sl_price': close - box * 2,
                        'entry_type': pending['entry_type'],
                        'exit_type': '',
                        'direction': 'long',
                    })
                    current_direction = 'long'
                    pending = None

                elif side == 'short' and r_dir == -1:
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price': self._apply_slippage(close, 'short', True),
                        'timestamp': ts,
                        'sl_price': close + box * 2,
                        'entry_type': pending['entry_type'],
                        'exit_type': '',
                        'direction': 'short',
                    })
                    current_direction = 'short'
                    pending = None

        print(f"[SIGNAL] Total signals generated = {len(signals)}")
        return signals
