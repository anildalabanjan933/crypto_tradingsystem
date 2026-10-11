# strategies/backtest/renko_trend_pullback_v5_strategy.py
# V1 Trend Pullback. Signals evaluated ONLY on the last brick of each candle.
# Prices = real_close of that candle. Slippage: leave slippage_usd=0 (TradeBuilder charges it once).
import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy
from strategies.backtest.renko_smiio_supertrend_strategy import compute_smiio
from strategies.backtest.renko_rc_utils import build_renko_rc, slip, tsfmt
from indicators.renko import SupertrendIndicator


class RenkoTrendPullbackV5Strategy(BaseStrategy):
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kw):
        super().__init__(data_dict=data_dict, lot_size=lot_size)
        self.renko_timeframe = kw.get('renko_timeframe', '2h')
        self.renko_box_pct = kw.get('renko_box_pct', 0.001)
        self.reference_price = kw.get('reference_price', None)
        self.st_atr_length = kw.get('st_atr_length', 5)
        self.st_factor = kw.get('st_factor', 3.0)
        self.pullback_min = kw.get('pullback_min', 2)      # opposite bricks needed
        self.smiio_shortlen = kw.get('smiio_shortlen', 10)
        self.smiio_longlen = kw.get('smiio_longlen', 20)
        self.smiio_siglen = kw.get('smiio_siglen', 3)
        self.slippage_usd = kw.get('slippage_usd', 0.0)

    @property
    def required_timeframes(self):
        return [self.renko_timeframe]

    @property
    def optimization_params(self):
        return {
            'st_factor': {'default': 3.0, 'min': 2.0, 'max': 3.0, 'step': 1.0},
            'pullback_min': {'default': 2, 'min': 2, 'max': 3, 'step': 1},
            'renko_box_pct': {'default': 0.001, 'min': 0.001, 'max': 0.0015, 'step': 0.0005},
        }

    def generate_signals(self) -> list:
        df, box = build_renko_rc(self._data, self.renko_timeframe,
                                 self.renko_box_pct, self.reference_price)
        n = len(df)
        rc = df['renko_close'].values
        rdir = df['renko_dir'].values
        real = df['real_close'].values
        lob = np.where(df['last_of_bar'].values)[0]
        ts = [tsfmt(t) for t in df['timestamp'].values]
        st = SupertrendIndicator(self.st_atr_length, self.st_factor).calculate(df)['st_dir'].values
        smi, sig = compute_smiio(rc, self.smiio_shortlen, self.smiio_longlen, self.smiio_siglen)

        signals, cur, extreme, last_exit_i = [], None, None, -1
        for a in range(1, len(lob)):
            k, p = lob[a], lob[a - 1]
            # pullback run length = consecutive opposite bricks ending at p
            run, j = 0, p
            while j >= 0 and rdir[j] == rdir[p]:
                run += 1; j -= 1

            exit_now = False
            if cur == 'long':
                if st[k] == 1 or rc[k] < extreme - box:
                    exit_now = True
            elif cur == 'short':
                if st[k] == -1 or rc[k] > extreme + box:
                    exit_now = True
            if exit_now:
                signals.append({'signal_type': 'EXIT', 'price': slip(real[k], cur, False, self.slippage_usd),
                                'timestamp': ts[k], 'sl_price': real[k] - box if cur == 'long' else real[k] + box,
                                'entry_type': '', 'exit_type': 'ST_FLIP_OR_PULLBACK_BREAK', 'direction': cur})
                cur, last_exit_i = None, k

            if cur is None and k != last_exit_i:          # no same-bar flip
                if st[k] == -1 and smi[k] > sig[k] and rdir[k] == 1 and rdir[p] == -1 and run >= self.pullback_min:
                    extreme = rc[p - run + 1:p + 1].min()
                    cur = 'long'
                    signals.append({'signal_type': 'ENTRY', 'price': slip(real[k], 'long', True, self.slippage_usd),
                                    'timestamp': ts[k], 'sl_price': real[k] - box * 2,
                                    'entry_type': 'PULLBACK_LONG', 'exit_type': '', 'direction': 'long'})
                elif st[k] == 1 and smi[k] < sig[k] and rdir[k] == -1 and rdir[p] == 1 and run >= self.pullback_min:
                    extreme = rc[p - run + 1:p + 1].max()
                    cur = 'short'
                    signals.append({'signal_type': 'ENTRY', 'price': slip(real[k], 'short', True, self.slippage_usd),
                                    'timestamp': ts[k], 'sl_price': real[k] + box * 2,
                                    'entry_type': 'PULLBACK_SHORT', 'exit_type': '', 'direction': 'short'})
        return signals
