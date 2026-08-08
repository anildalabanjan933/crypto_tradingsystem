import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy


def compute_ema(closes, period):
    return pd.Series(closes).ewm(span=period, adjust=False).mean().to_numpy()


def compute_atr(high, low, close, period=14):
    n = len(close)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    tr[0] = high[0] - low[0]
    return pd.Series(tr).rolling(period).mean().to_numpy()


def compute_supertrend(high, low, close, period=10, mult=3.0):
    n = len(close)
    atr = compute_atr(high, low, close, period)
    hl2 = (high + low) / 2.0
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    st_line = np.zeros(n)
    trend = np.zeros(n)
    trend[:] = 1
    for i in range(1, n):
        if np.isnan(atr[i]):
            st_line[i] = hl2[i]
            trend[i] = trend[i - 1]
            continue
        if close[i - 1] > upper[i - 1]:
            lower[i] = max(lower[i], lower[i - 1])
        if close[i - 1] < lower[i - 1]:
            upper[i] = min(upper[i], upper[i - 1])
        if trend[i - 1] == 1:
            trend[i] = -1 if close[i] < lower[i] else 1
        else:
            trend[i] = 1 if close[i] > upper[i] else -1
        st_line[i] = lower[i] if trend[i] == 1 else upper[i]
    return trend, st_line


class SupertrendPullbackStrategy(BaseStrategy):
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        super().__init__(data_dict=data_dict, lot_size=lot_size)
        self.timeframe = kwargs.get('timeframe', '1h')
        self.st_atr_period = kwargs.get('st_atr_period', 10)
        self.st_mult = kwargs.get('st_mult', 3.0)
        self.ema_len = kwargs.get('ema_len', 50)
        self.swing_lookback = kwargs.get('swing_lookback', 5)
        self.slippage_usd = kwargs.get('slippage_usd', 5.0)

    @property
    def required_timeframes(self) -> list:
        return [self.timeframe]

    @property
    def optimization_params(self) -> dict:
        return {
            'st_atr_period': {'default': 10, 'min': 7, 'max': 14, 'step': 1},
            'st_mult':       {'default': 3.0, 'min': 2.0, 'max': 4.0, 'step': 0.5},
            'ema_len':       {'default': 50, 'min': 30, 'max': 100, 'step': 10},
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

        trend, st_line = compute_supertrend(high, low, close, self.st_atr_period, self.st_mult)
        ema = compute_ema(close, self.ema_len)
        swing_low = pd.Series(low).rolling(self.swing_lookback).min().shift(1).to_numpy()
        swing_high = pd.Series(high).rolling(self.swing_lookback).max().shift(1).to_numpy()

        signals = []
        current_direction = None
        n = len(close)
        warmup = max(self.st_atr_period, self.ema_len, self.swing_lookback) + 2

        for i in range(warmup, n):
            if np.isnan(st_line[i]) or np.isnan(ema[i]) or np.isnan(swing_low[i]):
                continue
            ts = ts_index[i]
            c, o, h, l = close[i], open_[i], high[i], low[i]
            bull = c > o
            bear = c < o
            trend_flip_down = trend[i - 1] == 1 and trend[i] == -1
            trend_flip_up = trend[i - 1] == -1 and trend[i] == 1

            long_cond = trend[i] == 1 and c > ema[i] and l <= st_line[i] and c > st_line[i] and bull
            short_cond = trend[i] == -1 and c < ema[i] and h >= st_line[i] and c < st_line[i] and bear

            if current_direction is None:
                if long_cond:
                    ep = self._apply_slippage(c, 'long', True)
                    signals.append({'signal_type': 'ENTRY', 'price': ep, 'timestamp': ts,
                                     'sl_price': swing_low[i], 'entry_type': 'ST_PULLBACK_LONG',
                                     'exit_type': '', 'direction': 'long'})
                    current_direction = 'long'
                elif short_cond:
                    ep = self._apply_slippage(c, 'short', True)
                    signals.append({'signal_type': 'ENTRY', 'price': ep, 'timestamp': ts,
                                     'sl_price': swing_high[i], 'entry_type': 'ST_PULLBACK_SHORT',
                                     'exit_type': '', 'direction': 'short'})
                    current_direction = 'short'
            elif current_direction == 'long' and trend_flip_down:
                signals.append({'signal_type': 'EXIT', 'price': self._apply_slippage(c, 'long', False),
                                 'timestamp': ts, 'sl_price': 0.0, 'entry_type': '',
                                 'exit_type': 'ST_REVERSE', 'direction': 'long'})
                current_direction = None
            elif current_direction == 'short' and trend_flip_up:
                signals.append({'signal_type': 'EXIT', 'price': self._apply_slippage(c, 'short', False),
                                 'timestamp': ts, 'sl_price': 0.0, 'entry_type': '',
                                 'exit_type': 'ST_REVERSE', 'direction': 'short'})
                current_direction = None

        self.signals = signals
        return signals
