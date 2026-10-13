# strategies/backtest/squeeze_breakout_v7_strategy.py
# V7 "Volatility Squeeze Breakout" - NON-Renko, candle-based, symmetric long/short.
#
# EDGE CONCEPT (market-structure rationale, not fitted to 2024-26):
#   BTC volatility clusters and mean-reverts: after a stretch of unusually LOW realized range
#   (compression), the next directional move tends to be larger than average (expansion), because
#   leverage/stops/liquidity build up on both sides of a tight range and release together.
#   A plain channel breakout (what V5/V6 did) fires in compression AND in already-expanded
#   markets; most of its trades are small noisy moves that cost ~$20-28 each. V7 trades ONLY
#   breakouts that come out of compression, and lets winners run with an ATR chandelier trail,
#   so average gross per trade is driven by a few large expansion moves (fat right tail), not
#   by win rate. Expect low win rate (~30-40%) and PF coming from payoff ratio.
#
# RULES (4h candles, all decisions on CLOSED candle, fill = that candle's close):
#   squeeze  : ATR%(prev bar) is in the lowest SQUEEZE_Q fraction of the previous W bars.
#   LONG     : flat AND squeeze AND close > highest close of previous N bars.
#   SHORT    : flat AND squeeze AND close < lowest  close of previous N bars.
#   EXIT     : ATR chandelier, close-based. long: close < max(init_stop, highest_close - T*ATR).
#              Stop only ratchets in the trade's favour. short mirrored.
#   Pullback-vs-reversal: a retrace smaller than T*ATR from the best close is a pullback (hold);
#              a close beyond it is structure broken -> exit. No fixed % stop, no regime filter
#              other than the squeeze condition on ENTRY (exits always active).
#
# PARAMS: breakout_n, trail_atr (optimized, 9 combos). squeeze_q fixed 0.35 (override via kw).
#   ATR_P=14 and W=180 are fixed constants, not tuned.
# Pricing: signal timestamp = candle LABEL, price = that candle's close (same convention as V5/V6
#   real_close fills; candle closes at label + TF - 1min). slippage_usd = 0.0 because
#   TradeBuilder charges slippage once.
import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy


class SqueezeBreakoutV7Strategy(BaseStrategy):
    ATR_P = 14   # fixed
    W = 180      # fixed: look-back (bars) for the compression percentile (~30 days of 4h)

    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kw):
        super().__init__(data_dict=data_dict, lot_size=lot_size)
        self.timeframe = kw.get('timeframe', '4h')
        self.breakout_n = int(kw.get('breakout_n', 20))
        self.trail_atr = float(kw.get('trail_atr', 3.0))
        self.squeeze_q = float(kw.get('squeeze_q', 0.35))
        self.slippage_usd = kw.get('slippage_usd', 0.0)

    @property
    def required_timeframes(self):
        return [self.timeframe]

    @property
    def optimization_params(self):
        # 3 x 3 = 9 combos (<= 12). Choose by plateau on TRAIN only, then test once.
        return {
            'breakout_n': {'default': 20, 'min': 16, 'max': 24, 'step': 4},
            'trail_atr': {'default': 3.0, 'min': 2.5, 'max': 3.5, 'step': 0.5},
        }

    @staticmethod
    def _ts(t):
        return pd.Timestamp(t).strftime('%Y-%m-%dT%H:%M:%S')

    def _sig(self, kind, side, price, ts, stop, entry_type='', exit_type=''):
        is_entry = kind == 'ENTRY'
        s = self.slippage_usd
        px = price + s if (side == 'long') == is_entry else price - s
        return {'signal_type': kind, 'price': float(px), 'timestamp': ts,
                'sl_price': float(stop),
                'entry_type': entry_type if is_entry else '',
                'exit_type': '' if is_entry else exit_type,
                'direction': side}

    def generate_signals(self) -> list:
        df = self.get_data(self.timeframe)
        if df is None or len(df) == 0:
            raise ValueError(f"Requires '{self.timeframe}' timeframe data")
        idx = (df.index if isinstance(df.index, pd.DatetimeIndex)
               else pd.to_datetime(df['timestamp']))
        h = df['high'].values.astype(float)
        l = df['low'].values.astype(float)
        c = df['close'].values.astype(float)
        n = len(c)
        P, W, N, T, Q = self.ATR_P, self.W, self.breakout_n, self.trail_atr, self.squeeze_q

        # True range -> simple ATR (no look-ahead: value at i uses bars <= i)
        pc = np.concatenate(([c[0]], c[:-1]))
        tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
        atr = pd.Series(tr).rolling(P).mean().values
        atrp = atr / c

        signals, pos = [], None
        entry_ref = best = stop = 0.0
        start = max(N, W + P) + 2

        for i in range(start, n):
            ts = self._ts(idx[i])
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue

            # --- exits first: chandelier trail, close-based, ratchets only in favour ---
            if pos == 'long':
                best = max(best, c[i])
                stop = max(stop, best - T * a)
                if c[i] < stop:
                    signals.append(self._sig('EXIT', 'long', c[i], ts, stop,
                                             exit_type='ATR_TRAIL'))
                    pos = None
            elif pos == 'short':
                best = min(best, c[i])
                stop = min(stop, best + T * a)
                if c[i] > stop:
                    signals.append(self._sig('EXIT', 'short', c[i], ts, stop,
                                             exit_type='ATR_TRAIL'))
                    pos = None

            # --- entries (flat only): breakout that comes OUT of compression ---
            if pos is None:
                win = atrp[i - 1 - W:i - 1]
                if not np.all(np.isfinite(win)) or not np.isfinite(atrp[i - 1]):
                    continue
                squeeze = (win <= atrp[i - 1]).mean() <= Q
                if not squeeze:
                    continue
                hi = c[i - N:i].max()
                lo = c[i - N:i].min()
                if c[i] > hi:
                    pos, best = 'long', c[i]
                    stop = c[i] - T * a
                    signals.append(self._sig('ENTRY', 'long', c[i], ts, stop,
                                             entry_type='SQUEEZE_BREAK_LONG'))
                elif c[i] < lo:
                    pos, best = 'short', c[i]
                    stop = c[i] + T * a
                    signals.append(self._sig('ENTRY', 'short', c[i], ts, stop,
                                             entry_type='SQUEEZE_BREAK_SHORT'))
        return signals
