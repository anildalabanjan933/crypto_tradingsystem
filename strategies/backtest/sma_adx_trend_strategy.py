# strategies/backtest/sma_adx_trend_strategy.py
# Strategy: SMA + ADX Trend Ride (TF-2)
# Entry LONG  : SMA20 > SMA100 AND ADX > adx_threshold AND close > SMA20
# Entry SHORT : SMA20 < SMA100 AND ADX > adx_threshold AND close < SMA20
# Exit        : SMA20 cross (price crosses back through SMA20) OR ADX < adx_exit_threshold
# SL          : entry_price -/+ (atr_mult * ATR)

import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy


def compute_sma(closes: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(closes).rolling(window=period, min_periods=period).mean().to_numpy()


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )
    tr[0] = high[0] - low[0]
    return pd.Series(tr).rolling(window=period, min_periods=period).mean().to_numpy()


def compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    tr = np.zeros(n)

    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )

    tr_s = pd.Series(tr).rolling(window=period, min_periods=period).sum().to_numpy()
    plus_dm_s = pd.Series(plus_dm).rolling(window=period, min_periods=period).sum().to_numpy()
    minus_dm_s = pd.Series(minus_dm).rolling(window=period, min_periods=period).sum().to_numpy()

    with np.errstate(divide='ignore', invalid='ignore'):
        plus_di = np.where(tr_s != 0, 100.0 * plus_dm_s / tr_s, 0.0)
        minus_di = np.where(tr_s != 0, 100.0 * minus_dm_s / tr_s, 0.0)
        dx = np.where((plus_di + minus_di) != 0,
                      100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di), 0.0)

    adx = pd.Series(dx).rolling(window=period, min_periods=period).mean().to_numpy()
    return adx


class SmaAdxTrendStrategy(BaseStrategy):
    """
    TF-2 : SMA + ADX Trend Ride

    LONG  : SMA20 > SMA100 AND ADX > adx_entry_threshold AND close > SMA20
    SHORT : SMA20 < SMA100 AND ADX > adx_entry_threshold AND close < SMA20
    EXIT  : close crosses back through SMA20 (opposite side) OR ADX < adx_exit_threshold
    SL    : atr_mult * ATR from entry price
    """

    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        super().__init__(data_dict=data_dict, lot_size=lot_size)

        self.timeframe = kwargs.get('timeframe', '1h')
        self.sma_fast_len = kwargs.get('sma_fast_len', 20)
        self.sma_slow_len = kwargs.get('sma_slow_len', 100)
        self.adx_period = kwargs.get('adx_period', 14)
        self.adx_entry_threshold = kwargs.get('adx_entry_threshold', 25.0)
        self.adx_exit_threshold = kwargs.get('adx_exit_threshold', 20.0)
        self.atr_period = kwargs.get('atr_period', 14)
        self.atr_mult = kwargs.get('atr_mult', 2.0)
        self.slippage_usd = kwargs.get('slippage_usd', 5.0)

    @property
    def required_timeframes(self) -> list:
        return [self.timeframe]

    @property
    def optimization_params(self) -> dict:
        return {
            'sma_fast_len':        {'default': 20,  'min': 10,  'max': 30,  'step': 5},
            'sma_slow_len':        {'default': 100, 'min': 50,  'max': 200, 'step': 25},
            'adx_period':          {'default': 14,  'min': 10,  'max': 20,  'step': 2},
            'adx_entry_threshold': {'default': 25.0, 'min': 20.0, 'max': 35.0, 'step': 5.0},
            'adx_exit_threshold':  {'default': 20.0, 'min': 15.0, 'max': 25.0, 'step': 2.5},
            'atr_period':          {'default': 14,  'min': 10,  'max': 20,  'step': 2},
            'atr_mult':            {'default': 2.0, 'min': 1.5, 'max': 3.0, 'step': 0.5},
        }

    def _apply_slippage(self, price: float, direction: str, is_entry: bool) -> float:
        slip = self.slippage_usd
        if direction == 'long':
            return price + slip if is_entry else price - slip
        else:
            return price - slip if is_entry else price + slip

    def generate_signals(self) -> list:
        df = self.get_data(self.timeframe)
        df = df.sort_index()

        close = df['close'].to_numpy()
        high = df['high'].to_numpy()
        low = df['low'].to_numpy()
        ts_index = df.index

        sma_fast = compute_sma(close, self.sma_fast_len)
        sma_slow = compute_sma(close, self.sma_slow_len)
        adx = compute_adx(high, low, close, self.adx_period)
        atr = compute_atr(high, low, close, self.atr_period)

        signals = []
        current_direction = None
        entry_price = 0.0

        n = len(close)
        warmup = max(self.sma_slow_len, self.adx_period * 2, self.atr_period) + 1

        for i in range(warmup, n):
            if np.isnan(sma_fast[i]) or np.isnan(sma_slow[i]) or np.isnan(adx[i]) or np.isnan(atr[i]):
                continue

            ts = ts_index[i]
            c = close[i]
            prev_c = close[i - 1]
            sf = sma_fast[i]
            prev_sf = sma_fast[i - 1]
            ss = sma_slow[i]
            adx_val = adx[i]
            atr_val = atr[i]

            long_cond = sf > ss and adx_val > self.adx_entry_threshold and c > sf
            short_cond = sf < ss and adx_val > self.adx_entry_threshold and c < sf

            sma_cross_down = prev_c >= prev_sf and c < sf
            sma_cross_up = prev_c <= prev_sf and c > sf
            adx_weak = adx_val < self.adx_exit_threshold

            if current_direction is None:
                if long_cond:
                    entry_price = self._apply_slippage(c, 'long', True)
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price': entry_price,
                        'timestamp': ts,
                        'sl_price': entry_price - (self.atr_mult * atr_val),
                        'entry_type': 'SMA_ADX_LONG',
                        'exit_type': '',
                        'direction': 'long',
                    })
                    current_direction = 'long'
                elif short_cond:
                    entry_price = self._apply_slippage(c, 'short', True)
                    signals.append({
                        'signal_type': 'ENTRY',
                        'price': entry_price,
                        'timestamp': ts,
                        'sl_price': entry_price + (self.atr_mult * atr_val),
                        'entry_type': 'SMA_ADX_SHORT',
                        'exit_type': '',
                        'direction': 'short',
                    })
                    current_direction = 'short'

            elif current_direction == 'long' and (sma_cross_down or adx_weak):
                exit_reason = 'SMA_CROSS' if sma_cross_down else 'ADX_WEAK'
                signals.append({
                    'signal_type': 'EXIT',
                    'price': self._apply_slippage(c, 'long', False),
                    'timestamp': ts,
                    'sl_price': 0.0,
                    'entry_type': '',
                    'exit_type': exit_reason,
                    'direction': 'long',
                })
                current_direction = None

            elif current_direction == 'short' and (sma_cross_up or adx_weak):
                exit_reason = 'SMA_CROSS' if sma_cross_up else 'ADX_WEAK'
                signals.append({
                    'signal_type': 'EXIT',
                    'price': self._apply_slippage(c, 'short', False),
                    'timestamp': ts,
                    'sl_price': 0.0,
                    'entry_type': '',
                    'exit_type': exit_reason,
                    'direction': 'short',
                })
                current_direction = None

        self.signals = signals
        return signals
