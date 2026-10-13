# strategies/backtest/renko_htf_smiio_cross_v5_strategy.py
# V3 SMIIO cross (signal TF) filtered by higher-TF Renko Supertrend.
# LOOKAHEAD GUARD: HTF value is used only if its candle has CLOSED
# (label + HTF length <= signal candle close time).
import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy
from strategies.backtest.renko_smiio_supertrend_strategy import compute_smiio
from strategies.backtest.renko_rc_utils import build_renko_rc, slip, tsfmt, tf_delta
from indicators.renko import SupertrendIndicator


class RenkoHTFSmiioCrossV5Strategy(BaseStrategy):
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kw):
        super().__init__(data_dict=data_dict, lot_size=lot_size)
        self.renko_timeframe = kw.get('renko_timeframe', '4h')
        self.htf = kw.get('htf_timeframe', 'daily')
        self.renko_box_pct = kw.get('renko_box_pct', 0.005)
        self.htf_box_pct = kw.get('htf_box_pct', 0.003)
        self.reference_price = kw.get('reference_price', None)
        self.st_atr_length = kw.get('st_atr_length', 5)
        self.st_factor = kw.get('st_factor', 3.0)
        self.smiio_shortlen = kw.get('smiio_shortlen', 10)
        self.smiio_longlen = kw.get('smiio_longlen', 20)
        self.smiio_siglen = kw.get('smiio_siglen', 3)
        self.slippage_usd = kw.get('slippage_usd', 0.0)

    @property
    def required_timeframes(self):
        return [self.renko_timeframe, self.htf]

    @property
    def optimization_params(self):
        return {
            'renko_timeframe': {'values': ['1h', '2h', '4h']},
            'smiio_siglen': {'default': 3, 'min': 3, 'max': 7, 'step': 4},
            'st_factor': {'default': 3.0, 'min': 2.0, 'max': 3.0, 'step': 1.0},
        }

    def _htf_trend_at(self, close_times: np.ndarray):
        h, _ = build_renko_rc(self._data, self.htf, self.htf_box_pct)
        hst = SupertrendIndicator(self.st_atr_length, self.st_factor).calculate(h)['st_dir'].values
        lob = np.where(h['last_of_bar'].values)[0]
        h_close = (pd.to_datetime(h['timestamp'].values[lob]) + tf_delta(self.htf)).values
        h_dir = hst[lob]
        pos = np.searchsorted(h_close, close_times, side='right') - 1
        out = np.zeros(len(close_times), dtype=int)
        ok = pos >= 0
        out[ok] = h_dir[pos[ok]]
        return out

    def generate_signals(self) -> list:
        df, box = build_renko_rc(self._data, self.renko_timeframe,
                                 self.renko_box_pct, self.reference_price)
        rc = df['renko_close'].values
        real = df['real_close'].values
        lob = np.where(df['last_of_bar'].values)[0]
        ts = [tsfmt(t) for t in df['timestamp'].values]
        smi, sig = compute_smiio(rc, self.smiio_shortlen, self.smiio_longlen, self.smiio_siglen)
        sig_close = (pd.to_datetime(df['timestamp'].values) + tf_delta(self.renko_timeframe)).values
        htf_dir = self._htf_trend_at(sig_close)

        signals, cur, last_exit_i = [], None, -1
        for a in range(1, len(lob)):
            k, p = lob[a], lob[a - 1]
            up = smi[k] > sig[k] and smi[p] <= sig[p]
            dn = smi[k] < sig[k] and smi[p] >= sig[p]
            if cur == 'long' and (dn or htf_dir[k] == 1):
                signals.append({'signal_type': 'EXIT', 'price': slip(real[k], 'long', False, self.slippage_usd),
                                'timestamp': ts[k], 'sl_price': real[k] - box, 'entry_type': '',
                                'exit_type': 'SMIIO_DOWN_OR_HTF_FLIP', 'direction': 'long'})
                cur, last_exit_i = None, k
            elif cur == 'short' and (up or htf_dir[k] == -1):
                signals.append({'signal_type': 'EXIT', 'price': slip(real[k], 'short', False, self.slippage_usd),
                                'timestamp': ts[k], 'sl_price': real[k] + box, 'entry_type': '',
                                'exit_type': 'SMIIO_UP_OR_HTF_FLIP', 'direction': 'short'})
                cur, last_exit_i = None, k
            if cur is None and k != last_exit_i:
                if up and htf_dir[k] == -1:
                    cur = 'long'
                    signals.append({'signal_type': 'ENTRY', 'price': slip(real[k], 'long', True, self.slippage_usd),
                                    'timestamp': ts[k], 'sl_price': real[k] - box * 2,
                                    'entry_type': 'SMIIO_UP_HTF_UP', 'exit_type': '', 'direction': 'long'})
                elif dn and htf_dir[k] == 1:
                    cur = 'short'
                    signals.append({'signal_type': 'ENTRY', 'price': slip(real[k], 'short', True, self.slippage_usd),
                                    'timestamp': ts[k], 'sl_price': real[k] + box * 2,
                                    'entry_type': 'SMIIO_DOWN_HTF_DOWN', 'exit_type': '', 'direction': 'short'})
        return signals
