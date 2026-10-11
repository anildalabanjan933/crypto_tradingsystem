# strategies/backtest/renko_channel_breakout_v5_strategy.py
# V2 Brick Channel Breakout (Donchian on brick closes) + Supertrend agreement.
import numpy as np
from strategies.backtest.base_strategy import BaseStrategy
from strategies.backtest.renko_rc_utils import build_renko_rc, slip, tsfmt
from indicators.renko import SupertrendIndicator


class RenkoChannelBreakoutV5Strategy(BaseStrategy):
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kw):
        super().__init__(data_dict=data_dict, lot_size=lot_size)
        self.renko_timeframe = kw.get('renko_timeframe', '2h')
        self.renko_box_pct = kw.get('renko_box_pct', 0.001)
        self.reference_price = kw.get('reference_price', None)
        self.st_atr_length = kw.get('st_atr_length', 5)
        self.st_factor = kw.get('st_factor', 3.0)
        self.entry_n = kw.get('entry_n', 20)
        self.exit_m = kw.get('exit_m', 10)
        self.min_bricks = kw.get('min_bricks', 2)
        self.slippage_usd = kw.get('slippage_usd', 0.0)

    @property
    def required_timeframes(self):
        return [self.renko_timeframe]

    @property
    def optimization_params(self):
        return {
            'entry_n': {'default': 20, 'min': 15, 'max': 30, 'step': 5},
            'exit_m': {'default': 10, 'min': 8, 'max': 10, 'step': 2},
            'st_factor': {'default': 3.0, 'min': 2.0, 'max': 3.0, 'step': 1.0},
        }

    def generate_signals(self) -> list:
        df, box = build_renko_rc(self._data, self.renko_timeframe,
                                 self.renko_box_pct, self.reference_price)
        rc = df['renko_close'].values
        real = df['real_close'].values
        lob = np.where(df['last_of_bar'].values)[0]
        ts = [tsfmt(t) for t in df['timestamp'].values]
        st = SupertrendIndicator(self.st_atr_length, self.st_factor).calculate(df)['st_dir'].values

        signals, cur, last_exit_i = [], None, -1
        N, M = self.entry_n, self.exit_m
        for a in range(1, len(lob)):
            k, p = lob[a], lob[a - 1]
            if p + 1 < N:
                continue
            bricks_this_bar = k - p
            hi_n = rc[p - N + 1:p + 1].max()
            lo_n = rc[p - N + 1:p + 1].min()
            lo_m = rc[p - M + 1:p + 1].min()
            hi_m = rc[p - M + 1:p + 1].max()

            if cur == 'long' and (rc[k] < lo_m or st[k] == 1):
                signals.append({'signal_type': 'EXIT', 'price': slip(real[k], 'long', False, self.slippage_usd),
                                'timestamp': ts[k], 'sl_price': real[k] - box, 'entry_type': '',
                                'exit_type': 'CHANNEL_OR_ST_EXIT', 'direction': 'long'})
                cur, last_exit_i = None, k
            elif cur == 'short' and (rc[k] > hi_m or st[k] == -1):
                signals.append({'signal_type': 'EXIT', 'price': slip(real[k], 'short', False, self.slippage_usd),
                                'timestamp': ts[k], 'sl_price': real[k] + box, 'entry_type': '',
                                'exit_type': 'CHANNEL_OR_ST_EXIT', 'direction': 'short'})
                cur, last_exit_i = None, k

            if cur is None and k != last_exit_i and bricks_this_bar >= self.min_bricks:
                if rc[k] > hi_n and st[k] == -1:
                    cur = 'long'
                    signals.append({'signal_type': 'ENTRY', 'price': slip(real[k], 'long', True, self.slippage_usd),
                                    'timestamp': ts[k], 'sl_price': real[k] - box * 2,
                                    'entry_type': 'CHANNEL_BREAK_UP', 'exit_type': '', 'direction': 'long'})
                elif rc[k] < lo_n and st[k] == 1:
                    cur = 'short'
                    signals.append({'signal_type': 'ENTRY', 'price': slip(real[k], 'short', True, self.slippage_usd),
                                    'timestamp': ts[k], 'sl_price': real[k] + box * 2,
                                    'entry_type': 'CHANNEL_BREAK_DOWN', 'exit_type': '', 'direction': 'short'})
        return signals
