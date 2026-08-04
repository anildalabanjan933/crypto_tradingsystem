"""
TF-1 : Supertrend + EMA Trend
Priority 1 - Trend Following
Market: Trending
"""

import pandas as pd
import numpy as np
from strategies.backtest.base_strategy import BaseStrategy


class TF1SupertrendEMAStrategy(BaseStrategy):

    def __init__(self, data_dict: dict, lot_size: float, **kwargs):
        super().__init__(data_dict, lot_size, **kwargs)

        self.ema_fast_len = kwargs.get('ema_fast_len', 50)
        self.ema_slow_len = kwargs.get('ema_slow_len', 200)
        self.st_atr_length = kwargs.get('st_atr_length', 10)
        self.st_factor = kwargs.get('st_factor', 3.0)
        self.adx_length = kwargs.get('adx_length', 14)
        self.adx_threshold = kwargs.get('adx_threshold', 20)
        self.timeframe = kwargs.get('timeframe', '1h')
        self.swing_lookback = kwargs.get('swing_lookback', 5)

    @property
    def required_timeframes(self):
        return [self.timeframe]

    @staticmethod
    def _ema(series, length):
        return series.ewm(span=length, adjust=False).mean()

    def _supertrend(self, df, atr_length, factor):
        high, low, close = df['high'], df['low'], df['close']
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(span=atr_length, adjust=False).mean()

        hl2 = (high + low) / 2
        upperband = hl2 + factor * atr
        lowerband = hl2 - factor * atr

        final_upper = upperband.copy()
        final_lower = lowerband.copy()
        direction = pd.Series(index=df.index, dtype=int)

        for i in range(len(df)):
            if i == 0:
                final_upper.iloc[i] = upperband.iloc[i]
                final_lower.iloc[i] = lowerband.iloc[i]
                direction.iloc[i] = 1
                continue
            if upperband.iloc[i] < final_upper.iloc[i-1] or close.iloc[i-1] > final_upper.iloc[i-1]:
                final_upper.iloc[i] = upperband.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i-1]
            if lowerband.iloc[i] > final_lower.iloc[i-1] or close.iloc[i-1] < final_lower.iloc[i-1]:
                final_lower.iloc[i] = lowerband.iloc[i]
            else:
                final_lower.iloc[i] = final_lower.iloc[i-1]
            if direction.iloc[i-1] == 1:
                direction.iloc[i] = -1 if close.iloc[i] < final_lower.iloc[i] else 1
            else:
                direction.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1

        return direction

    def _adx(self, df, length):
        high, low, close = df['high'], df['low'], df['close']
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(span=length, adjust=False).mean()
        plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(span=length, adjust=False).mean() / atr
        minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(span=length, adjust=False).mean() / atr
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        return dx.ewm(span=length, adjust=False).mean().fillna(0)

    def generate_signals(self):
        df = self._data[self.timeframe].copy().sort_index()

        df['ema_fast'] = self._ema(df['close'], self.ema_fast_len)
        df['ema_slow'] = self._ema(df['close'], self.ema_slow_len)
        df['st_dir'] = self._supertrend(df, self.st_atr_length, self.st_factor)
        df['adx'] = self._adx(df, self.adx_length)
        df['prev_high'] = df['high'].shift(1)
        df['prev_low'] = df['low'].shift(1)
        df['swing_high'] = df['high'].rolling(self.swing_lookback).max().shift(1)
        df['swing_low'] = df['low'].rolling(self.swing_lookback).min().shift(1)

        signals = []
        position = None
        sl_price = None
        warmup = max(self.ema_slow_len, self.st_atr_length, self.adx_length, self.swing_lookback) + 1

        for i in range(warmup, len(df)):
            row = df.iloc[i]
            prev_st_dir = df['st_dir'].iloc[i-1]
            ts = df.index[i]

            long_cond = (row['ema_fast'] > row['ema_slow'] and row['st_dir'] == 1
                         and row['adx'] > self.adx_threshold and row['close'] > row['prev_high'])
            short_cond = (row['ema_fast'] < row['ema_slow'] and row['st_dir'] == -1
                          and row['adx'] > self.adx_threshold and row['close'] < row['prev_low'])

            if position == 'long':
                st_rev = row['st_dir'] == -1 and prev_st_dir == 1
                ema_cross = row['ema_fast'] < row['ema_slow']
                sl_hit = sl_price is not None and row['low'] <= sl_price
                if st_rev or ema_cross or sl_hit:
                    exit_price = sl_price if sl_hit else row['close']
                    signals.append({
                        'signal_type': 'EXIT',
                        'price': exit_price,
                        'timestamp': ts,
                        'sl_price': sl_price,
                        'entry_type': '',
                        'exit_type': 'SL' if sl_hit else ('ST_FLIP' if st_rev else 'EMA_CROSS'),
                        'direction': 'long',
                    })
                    position, sl_price = None, None

            elif position == 'short':
                st_rev = row['st_dir'] == 1 and prev_st_dir == -1
                ema_cross = row['ema_fast'] > row['ema_slow']
                sl_hit = sl_price is not None and row['high'] >= sl_price
                if st_rev or ema_cross or sl_hit:
                    exit_price = sl_price if sl_hit else row['close']
                    signals.append({
                        'signal_type': 'EXIT',
                        'price': exit_price,
                        'timestamp': ts,
                        'sl_price': sl_price,
                        'entry_type': '',
                        'exit_type': 'SL' if sl_hit else ('ST_FLIP' if st_rev else 'EMA_CROSS'),
                        'direction': 'short',
                    })
                    position, sl_price = None, None

            if position is None:
                if long_cond:
                    sl_price = row['swing_low']
                    position = 'long'
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price': row['close'],
                        'timestamp': ts,
                        'sl_price': sl_price,
                        'entry_type': 'BUY',
                        'exit_type': '',
                        'direction': 'long',
                    })
                elif short_cond:
                    sl_price = row['swing_high']
                    position = 'short'
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price': row['close'],
                        'timestamp': ts,
                        'sl_price': sl_price,
                        'entry_type': 'SELL',
                        'exit_type': '',
                        'direction': 'short',
                    })

        return signals

    @property
    def optimization_params(self) -> dict:
        return {
            'ema_fast_len': {'default': 50, 'min': 20, 'max': 80, 'step': 10},
            'ema_slow_len': {'default': 200, 'min': 100, 'max': 300, 'step': 25},
            'st_atr_length': {'default': 10, 'min': 5, 'max': 20, 'step': 1},
            'st_factor': {'default': 3.0, 'min': 1.5, 'max': 5.0, 'step': 0.5},
            'adx_length': {'default': 14, 'min': 7, 'max': 21, 'step': 1},
            'adx_threshold': {'default': 20, 'min': 15, 'max': 30, 'step': 1},
        }
