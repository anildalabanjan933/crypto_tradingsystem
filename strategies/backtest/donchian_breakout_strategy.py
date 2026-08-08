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


def compute_adx(high, low, close, period=14):
    n = len(close)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    tr = np.zeros(n)
    for i in range(1, n):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    tr_s = pd.Series(tr).rolling(period).sum().to_numpy()
    plus_s = pd.Series(plus_dm).rolling(period).sum().to_numpy()
    minus_s = pd.Series(minus_dm).rolling(period).sum().to_numpy()
    with np.errstate(divide='ignore', invalid='ignore'):
        plus_di = np.where(tr_s != 0, 100.0 * plus_s / tr_s, 0.0)
        minus_di = np.where(tr_s != 0, 100.0 * minus_s / tr_s, 0.0)
        dx = np.where((plus_di + minus_di) != 0, 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di), 0.0)
    return pd.Series(dx).rolling(period).mean().to_numpy()


class DonchianBreakoutStrategy(BaseStrategy):
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        super().__init__(data_dict=data_dict, lot_size=lot_size)
        self.timeframe = kwargs.get('timeframe', '1h')
        self.donchian_period = kwargs.get('donchian_period', 20)
        self.adx_period = kwargs.get('adx_period', 14)
        self.adx_threshold = kwargs.get('adx_threshold', 20.0)
        self.atr_period = kwargs.get('atr_period', 14)
        self.atr_mult = kwargs.get('atr_mult', 2.0)
        self.slippage_usd = kwargs.get('slippage_usd', 5.0)

    @property
    def required_timeframes(self) -> list:
        return [self.timeframe]

    @property
    def optimization_params(self) -> dict:
        return {
            'donchian_period': {'default': 20, 'min': 10, 'max': 30, 'step': 5},
            'adx_period':      {'default': 14, 'min': 10, 'max': 20, 'step': 2},
            'adx_threshold':   {'default': 20.0, 'min': 15.0, 'max': 30.0, 'step': 5.0},
            'atr_mult':        {'default': 2.0, 'min': 1.5, 'max': 3.0, 'step': 0.5},
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
        adx = compute_adx(high, low, close, self.adx_period)
        dc_high = pd.Series(high).rolling(self.donchian_period).max().shift(1).to_numpy()
        dc_low = pd.Series(low).rolling(self.donchian_period).min().shift(1).to_numpy()
        dc_mid = (dc_high + dc_low) / 2.0

        signals = []
        current_direction = None
        n = len(close)
        warmup = max(self.donchian_period, self.adx_period * 2, self.atr_period) + 2

        for i in range(warmup, n):
            if np.isnan(atr[i]) or np.isnan(adx[i]) or np.isnan(dc_high[i]):
                continue
            ts = ts_index[i]
            c = close[i]
            long_cond = adx[i] > self.adx_threshold and c > dc_high[i]
            short_cond = adx[i] > self.adx_threshold and c < dc_low[i]

            if current_direction is None:
                if long_cond:
                    ep = self._apply_slippage(c, 'long', True)
                    signals.append({'signal_type': 'ENTRY', 'price': ep, 'timestamp': ts,
                                     'sl_price': ep - self.atr_mult * atr[i], 'entry_type': 'DONCHIAN_LONG',
                                     'exit_type': '', 'direction': 'long'})
                    current_direction = 'long'
                elif short_cond:
                    ep = self._apply_slippage(c, 'short', True)
                    signals.append({'signal_type': 'ENTRY', 'price': ep, 'timestamp': ts,
                                     'sl_price': ep + self.atr_mult * atr[i], 'entry_type': 'DONCHIAN_SHORT',
                                     'exit_type': '', 'direction': 'short'})
                    current_direction = 'short'
            elif current_direction == 'long' and c < dc_mid[i]:
                signals.append({'signal_type': 'EXIT', 'price': self._apply_slippage(c, 'long', False),
                                 'timestamp': ts, 'sl_price': 0.0, 'entry_type': '',
                                 'exit_type': 'DONCHIAN_MID', 'direction': 'long'})
                current_direction = None
            elif current_direction == 'short' and c > dc_mid[i]:
                signals.append({'signal_type': 'EXIT', 'price': self._apply_slippage(c, 'short', False),
                                 'timestamp': ts, 'sl_price': 0.0, 'entry_type': '',
                                 'exit_type': 'DONCHIAN_MID', 'direction': 'short'})
                current_direction = None

        self.signals = signals
        return signals
