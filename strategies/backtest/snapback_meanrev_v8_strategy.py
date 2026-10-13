# strategies/backtest/snapback_meanrev_v8_strategy.py
# V8 "Overextension Snap-Back" - NON-Renko, 1h candles, symmetric long/short, HIGH FREQUENCY.
#
# MECHANISM (why many trades AND a smoother curve is even possible):
#   On 1h BTC, price repeatedly stretches away from its 1-day mean (EMA24) by >= Z ATRs (stop runs,
#   liquidation cascades, thin-book impulses) and then partly snaps back as the forced flow ends.
#   Winners are SHORT-lived and bounded (exit at the mean) -> win rate is structurally high
#   (target ~55-65%), losses are capped by a hard ATR stop + time stop. Smoothness comes from many
#   small, frequent, bounded outcomes (Sharpe ~ per-trade edge/stdev x sqrt(trades)), NOT from a
#   bigger edge. It only works if NET expectancy per trade is > 0 after ~$24 cost - untested.
#
# RULES (all on CLOSED 1h candles; fill = that candle's close; timestamp = candle label):
#   dev[i]   = (close[i] - EMA24[i]) / ATR14[i]
#   LONG  : flat, dev[i-1] <= -Z (was stretched), close[i] > close[i-1] (snap-back has begun, no
#           falling-knife entry), and room to mean >= MIN_ROOM*ATR (reward not tiny), long not blocked.
#   SHORT : mirror.
#   EXIT  : MEAN_TARGET  close crosses back to EMA24
#           STOP         adverse move >= S*ATR(entry)  -> blocks that direction (see below)
#           TIME_STOP    MAX_HOLD bars without either
#   PULLBACK-vs-REVERSAL rule: a STOP means the stretch was a trend, not an overshoot. That
#           direction is BLOCKED until close re-crosses EMA24 (stops serial knife-catching, the main
#           drawdown source of any fade system). The opposite direction stays active, so after a
#           down-trend break the system fades rallies (i.e. trades WITH the trend). No regime filter.
#
# PARAMS optimized (2): z_entry, stop_atr  -> 9 combos.  Fixed: EMA 24, ATR 14, MIN_ROOM 0.8, MAX_HOLD 12.
# Pricing: slippage_usd = 0.0 (TradeBuilder charges slippage once).
import numpy as np
import pandas as pd
from strategies.backtest.base_strategy import BaseStrategy


class SnapBackV8Strategy(BaseStrategy):
    EMA_N = 24
    ATR_P = 14
    MIN_ROOM = 0.8
    MAX_HOLD = 12

    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kw):
        super().__init__(data_dict=data_dict, lot_size=lot_size)
        self.timeframe = kw.get('timeframe', '1h')
        self.z_entry = float(kw.get('z_entry', 1.5))
        self.stop_atr = float(kw.get('stop_atr', 1.5))
        self.slippage_usd = kw.get('slippage_usd', 0.0)

    @property
    def required_timeframes(self):
        return [self.timeframe]

    @property
    def optimization_params(self):
        # 3 x 3 = 9 combos. Lower z_entry => more trades. Judge on plateau, TRAIN only.
        return {
            'z_entry': {'default': 1.5, 'min': 1.2, 'max': 1.8, 'step': 0.3},
            'stop_atr': {'default': 1.5, 'min': 1.2, 'max': 1.8, 'step': 0.3},
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
        Z, S = self.z_entry, self.stop_atr

        pc = np.concatenate(([c[0]], c[:-1]))
        tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
        atr = pd.Series(tr).rolling(self.ATR_P).mean().values
        ema = pd.Series(c).ewm(span=self.EMA_N, adjust=False).mean().values
        dev = (c - ema) / atr

        signals, pos = [], None
        entry_px = atr_e = 0.0
        held = 0
        block_long = block_short = False
        start = max(self.EMA_N, self.ATR_P) * 3

        for i in range(start, n):
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            ts = self._ts(idx[i])

            # unblock a direction once price has re-crossed the mean
            if block_long and c[i] >= ema[i]:
                block_long = False
            if block_short and c[i] <= ema[i]:
                block_short = False

            # --- exits (checked before entries; never on the entry bar) ---
            if pos is not None:
                held += 1
                if pos == 'long':
                    if c[i] <= entry_px - S * atr_e:
                        why = 'STOP'; block_long = True
                    elif c[i] >= ema[i]:
                        why = 'MEAN_TARGET'
                    elif held >= self.MAX_HOLD:
                        why = 'TIME_STOP'
                    else:
                        why = None
                else:
                    if c[i] >= entry_px + S * atr_e:
                        why = 'STOP'; block_short = True
                    elif c[i] <= ema[i]:
                        why = 'MEAN_TARGET'
                    elif held >= self.MAX_HOLD:
                        why = 'TIME_STOP'
                    else:
                        why = None
                if why:
                    stp = entry_px - S * atr_e if pos == 'long' else entry_px + S * atr_e
                    signals.append(self._sig('EXIT', pos, c[i], ts, stp, exit_type=why))
                    pos = None

            # --- entries (flat only) ---
            if pos is None and np.isfinite(dev[i - 1]):
                if (dev[i - 1] <= -Z and c[i] > c[i - 1] and not block_long
                        and ema[i] - c[i] >= self.MIN_ROOM * a):
                    pos, entry_px, atr_e, held = 'long', c[i], a, 0
                    signals.append(self._sig('ENTRY', 'long', c[i], ts, c[i] - S * a,
                                             entry_type='SNAPBACK_LONG'))
                elif (dev[i - 1] >= Z and c[i] < c[i - 1] and not block_short
                        and c[i] - ema[i] >= self.MIN_ROOM * a):
                    pos, entry_px, atr_e, held = 'short', c[i], a, 0
                    signals.append(self._sig('ENTRY', 'short', c[i], ts, c[i] + S * a,
                                             entry_type='SNAPBACK_SHORT'))
        return signals
