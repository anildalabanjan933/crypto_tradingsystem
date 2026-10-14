import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy


def compute_ema(closes, period):
    return pd.Series(closes).ewm(span=period, adjust=False).mean().to_numpy()


def compute_rsi(closes, period=14):
    s = pd.Series(closes)
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.to_numpy()


class EmaPullbackStrategy(BaseStrategy):
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        super().__init__(data_dict=data_dict, lot_size=lot_size)
        self.timeframe = kwargs.get('timeframe', '1h')
        self.ema_fast_len = kwargs.get('ema_fast_len', 20)
        self.ema_slow_len = kwargs.get('ema_slow_len', 50)
        self.rsi_period = kwargs.get('rsi_period', 14)
        self.swing_lookback = kwargs.get('swing_lookback', 5)
        self.slippage_usd = kwargs.get('slippage_usd', 5.0)

    @property
    def required_timeframes(self) -> list:
        return [self.timeframe]

    @property
    def optimization_params(self) -> dict:
        return {
            'ema_fast_len':   {'default': 20, 'min': 10, 'max': 30, 'step': 5},
            'ema_slow_len':   {'default': 50, 'min': 30, 'max': 100, 'step': 10},
            'rsi_period':     {'default': 14, 'min': 10, 'max': 20, 'step': 2},
            'swing_lookback': {'default': 5,  'min': 3,  'max': 10, 'step': 1},
        }

    def _apply_slippage(self, price, direction, is_entry):
        slip = self.slippage_usd
        if direction == 'long':
            return price + slip if is_entry else price - slip
        return price - slip if is_entry else price + slip

    def generate_signals(self) -> list:
        df = self.get_data(self.timeframe).sort_index()
        close = df['close'].to_numpy()
        open_ = df['open'].to_numpy()
        high = df['high'].to_numpy()
        low = df['low'].to_numpy()
        ts_index = df.index

        ema_fast = compute_ema(close, self.ema_fast_len)
        ema_slow = compute_ema(close, self.ema_slow_len)
        rsi = compute_rsi(close, self.rsi_period)
        swing_low = pd.Series(low).rolling(self.swing_lookback).min().shift(1).to_numpy()
        swing_high = pd.Series(high).rolling(self.swing_lookback).max().shift(1).to_numpy()

        signals = []
        current_direction = None
        n = len(close)
        warmup = max(self.ema_slow_len, self.rsi_period, self.swing_lookback) + 2

        for i in range(warmup, n):
            if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]) or np.isnan(rsi[i]) or np.isnan(swing_low[i]):
                continue
            ts = ts_index[i]
            c, o, h, l = close[i], open_[i], high[i], low[i]
            ef, es = ema_fast[i], ema_slow[i]
            pef, pes = ema_fast[i - 1], ema_slow[i - 1]
            bull = c > o
            bear = c < o

            long_cond = ef > es and l <= ef and c > ef and bull and rsi[i] > 50
            short_cond = ef < es and h >= ef and c < ef and bear and rsi[i] < 50
            ema_cross_down = pef >= pes and ef < es
            ema_cross_up = pef <= pes and ef > es

            if current_direction is None:
                if long_cond:
                    ep = self._apply_slippage(c, 'long', True)
                    signals.append({'signal_type': 'ENTRY', 'price': ep, 'timestamp': ts,
                                     'sl_price': swing_low[i], 'entry_type': 'EMA_PULLBACK_LONG',
                                     'exit_type': '', 'direction': 'long'})
                    current_direction = 'long'
                elif short_cond:
                    ep = self._apply_slippage(c, 'short', True)
                    signals.append({'signal_type': 'ENTRY', 'price': ep, 'timestamp': ts,
                                     'sl_price': swing_high[i], 'entry_type': 'EMA_PULLBACK_SHORT',
                                     'exit_type': '', 'direction': 'short'})
                    current_direction = 'short'
            elif current_direction == 'long' and (ema_cross_down or c < swing_low[i]):
                reason = 'EMA_CROSS' if ema_cross_down else 'SWING_BREAK'
                signals.append({'signal_type': 'EXIT', 'price': self._apply_slippage(c, 'long', False),
                                 'timestamp': ts, 'sl_price': 0.0, 'entry_type': '',
                                 'exit_type': reason, 'direction': 'long'})
                current_direction = None
            elif current_direction == 'short' and (ema_cross_up or c > swing_high[i]):
                reason = 'EMA_CROSS' if ema_cross_up else 'SWING_BREAK'
                signals.append({'signal_type': 'EXIT', 'price': self._apply_slippage(c, 'short', False),
                                 'timestamp': ts, 'sl_price': 0.0, 'entry_type': '',
                                 'exit_type': reason, 'direction': 'short'})
                current_direction = None

        self.signals = signals
        return signals
