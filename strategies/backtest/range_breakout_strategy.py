import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy


def compute_atr(high, low, close, period=14):
    n = len(close)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    tr[0] = high[0] - low[0]
    return pd.Series(tr).rolling(period).mean().to_numpy()


class RangeBreakoutStrategy(BaseStrategy):
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        super().__init__(data_dict=data_dict, lot_size=lot_size)
        self.timeframe = kwargs.get('timeframe', '1h')
        self.range_lookback = kwargs.get('range_lookback', 20)
        self.atr_period = kwargs.get('atr_period', 14)
        self.atr_ma_period = kwargs.get('atr_ma_period', 20)
        self.atr_trail_mult = kwargs.get('atr_trail_mult', 3.0)
        self.slippage_usd = kwargs.get('slippage_usd', 5.0)

    @property
    def required_timeframes(self) -> list:
        return [self.timeframe]

    @property
    def optimization_params(self) -> dict:
        return {
            'range_lookback':  {'default': 20, 'min': 10, 'max': 30, 'step': 5},
            'atr_period':      {'default': 14, 'min': 10, 'max': 20, 'step': 2},
            'atr_ma_period':   {'default': 20, 'min': 10, 'max': 30, 'step': 5},
            'atr_trail_mult':  {'default': 3.0, 'min': 2.0, 'max': 4.0, 'step': 0.5},
        }

    def _apply_slippage(self, price, direction, is_entry):
        slip = self.slippage_usd
        if direction == 'long':
            return price + slip if is_entry else price - slip
        return price - slip if is_entry else price + slip

    def generate_signals(self) -> list:
        df = self.get_data(self.timeframe).sort_index()
        close = df['close'].to_numpy()
        high = df['high'].to_numpy()
        low = df['low'].to_numpy()
        ts_index = df.index

        atr = compute_atr(high, low, close, self.atr_period)
        atr_ma = pd.Series(atr).rolling(self.atr_ma_period).mean().to_numpy()
        range_high = pd.Series(high).rolling(self.range_lookback).max().shift(1).to_numpy()
        range_low = pd.Series(low).rolling(self.range_lookback).min().shift(1).to_numpy()

        signals = []
        current_direction = None
        trail_extreme = 0.0
        n = len(close)
        warmup = max(self.range_lookback, self.atr_ma_period, self.atr_period) + 2

        for i in range(warmup, n):
            if np.isnan(atr[i]) or np.isnan(atr_ma[i]) or np.isnan(range_high[i]):
                continue
            ts = ts_index[i]
            c = close[i]
            atr_low_cond = atr[i] < atr_ma[i]
            long_cond = atr_low_cond and c > range_high[i]
            short_cond = atr_low_cond and c < range_low[i]

            if current_direction is None:
                if long_cond:
                    ep = self._apply_slippage(c, 'long', True)
                    trail_extreme = c
                    signals.append({'signal_type': 'ENTRY', 'price': ep, 'timestamp': ts,
                                     'sl_price': range_low[i], 'entry_type': 'RANGE_BREAKOUT_LONG',
                                     'exit_type': '', 'direction': 'long'})
                    current_direction = 'long'
                elif short_cond:
                    ep = self._apply_slippage(c, 'short', True)
                    trail_extreme = c
                    signals.append({'signal_type': 'ENTRY', 'price': ep, 'timestamp': ts,
                                     'sl_price': range_high[i], 'entry_type': 'RANGE_BREAKOUT_SHORT',
                                     'exit_type': '', 'direction': 'short'})
                    current_direction = 'short'
            elif current_direction == 'long':
                trail_extreme = max(trail_extreme, c)
                trail_stop = trail_extreme - self.atr_trail_mult * atr[i]
                if c < trail_stop:
                    signals.append({'signal_type': 'EXIT', 'price': self._apply_slippage(c, 'long', False),
                                     'timestamp': ts, 'sl_price': 0.0, 'entry_type': '',
                                     'exit_type': 'ATR_TRAIL', 'direction': 'long'})
                    current_direction = None
            elif current_direction == 'short':
                trail_extreme = min(trail_extreme, c)
                trail_stop = trail_extreme + self.atr_trail_mult * atr[i]
                if c > trail_stop:
                    signals.append({'signal_type': 'EXIT', 'price': self._apply_slippage(c, 'short', False),
                                     'timestamp': ts, 'sl_price': 0.0, 'entry_type': '',
                                     'exit_type': 'ATR_TRAIL', 'direction': 'short'})
                    current_direction = None

        self.signals = signals
        return signals
