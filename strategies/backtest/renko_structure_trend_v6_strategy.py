# strategies/backtest/renko_structure_trend_v6_strategy.py
# V6 "Renko Structure Trend" - slow-horizon trend following with structure-based
# pullback entries and structure-based exits. Both directions, symmetric.
#
# WHY THIS DESIGN (market rationale, not fitted to 2024-26 path):
#  1. Cost reality: ~$20-28 per round trip at 100 lots (0.1 BTC). Gross PnL per trade must be
#     >= ~$80 => average move per trade >= ~$800 (~1.1%). Only slow horizons can do that.
#     So: DAILY candles, box ~2% (~$1,400). Expect ~15-40 trades/year, not 2/day.
#  2. Edge source: time-series momentum / trend persistence in BTC at multi-day horizons
#     (documented across crypto, driven by slow-moving flows, herding, leverage cascades).
#     No claim at 2h-4h horizons (already tested: no edge there).
#  3. Winners are allowed to run; losers are cut by STRUCTURE (depth of pullback in bricks),
#     not by a fixed %. Low win rate (~35-45%) with PF from payoff ratio is expected -
#     this is honest: a high win rate AND smooth line is not what trend systems produce.
#
# SCENARIOS (all symmetric long/short):
#   a) CONT_LONG / c) CONT_SHORT : close breaks the N-brick channel -> trend state flips, enter.
#   b) PULLBACK_LONG / d) PULLBACK_SHORT : in an established trend, after a pullback of
#      PB_MIN..K bricks, the next candle resumes in trend direction -> enter (flat only).
# PULLBACK vs REVERSAL (explicit rule):
#   pullback depth (from trend extreme, in bricks) <= K  -> still a pullback, trend intact.
#   depth > K OR close breaks the opposite N-brick channel -> structure broken = REVERSAL:
#   exit, and trend state flips (new CONT entry the other way if channel broken).
# No regime filter: it trades in ranges too (expect more small losses there, fewer trades
#   than trending phases) - report trade count by regime when validating.
#
# Parameters (3 tunable): renko_box_pct, channel_n, pullback_k.  PB_MIN fixed at 2.
# Pricing: signals evaluated ONLY on last brick of each candle (last_of_bar); fill = real_close.
# slippage_usd stays 0.0 (TradeBuilder charges slippage once).
import numpy as np
from strategies.backtest.base_strategy import BaseStrategy
from strategies.backtest.renko_rc_utils import build_renko_rc, slip, tsfmt


class RenkoStructureTrendV6Strategy(BaseStrategy):
    PB_MIN = 2  # fixed: min pullback depth (bricks) to count as a pullback

    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kw):
        super().__init__(data_dict=data_dict, lot_size=lot_size)
        self.renko_timeframe = kw.get('renko_timeframe', 'daily')
        self.renko_box_pct = kw.get('renko_box_pct', 0.02)
        self.reference_price = kw.get('reference_price', None)
        self.channel_n = int(kw.get('channel_n', 8))
        self.pullback_k = float(kw.get('pullback_k', 4))
        self.slippage_usd = kw.get('slippage_usd', 0.0)

    @property
    def required_timeframes(self):
        return [self.renko_timeframe]

    @property
    def optimization_params(self):
        # Small grid on purpose (anti curve-fit). Judge on plateau, TEST period only afterwards.
        return {
            'renko_box_pct': {'default': 0.02, 'min': 0.015, 'max': 0.025, 'step': 0.005},
            'channel_n': {'default': 8, 'min': 6, 'max': 10, 'step': 2},
            'pullback_k': {'default': 4, 'min': 3, 'max': 5, 'step': 1},
        }

    def _sig(self, kind, side, price, ts, box, entry_type='', exit_type=''):
        is_entry = kind == 'ENTRY'
        sl = price - box * self.pullback_k if side == 'long' else price + box * self.pullback_k
        return {'signal_type': kind,
                'price': slip(price, side, is_entry, self.slippage_usd),
                'timestamp': ts, 'sl_price': sl,
                'entry_type': entry_type if is_entry else '',
                'exit_type': '' if is_entry else exit_type,
                'direction': side}

    def generate_signals(self) -> list:
        df, box = build_renko_rc(self._data, self.renko_timeframe,
                                 self.renko_box_pct, self.reference_price)
        rc = df['renko_close'].values
        real = df['real_close'].values
        lob = np.where(df['last_of_bar'].values)[0]
        ts = [tsfmt(t) for t in df['timestamp'].values]
        N, K = self.channel_n, self.pullback_k

        signals, cur = [], None
        trend, extreme, depth_prev = 0, None, 0.0

        for a in range(1, len(lob)):
            k, p = lob[a], lob[a - 1]
            if p + 1 < N:
                continue
            hi = rc[p - N + 1:p + 1].max()
            lo = rc[p - N + 1:p + 1].min()
            brk_up, brk_dn = rc[k] > hi, rc[k] < lo

            # --- trend state + extreme tracking (uses closed brick data only) ---
            if brk_up:
                trend, extreme = 1, rc[k]
            elif brk_dn:
                trend, extreme = -1, rc[k]
            elif trend == 1:
                extreme = max(extreme, rc[k])
            elif trend == -1:
                extreme = min(extreme, rc[k])

            if trend == 1:
                depth = (extreme - rc[k]) / box
            elif trend == -1:
                depth = (rc[k] - extreme) / box
            else:
                depth = 0.0

            # --- exits: structure broken (reversal), never a fixed % stop ---
            if cur == 'long' and (trend == -1 or depth > K):
                signals.append(self._sig('EXIT', 'long', real[k], ts[k], box,
                                         exit_type='STRUCTURE_BREAK'))
                cur = None
            elif cur == 'short' and (trend == 1 or depth > K):
                signals.append(self._sig('EXIT', 'short', real[k], ts[k], box,
                                         exit_type='STRUCTURE_BREAK'))
                cur = None

            # --- entries (flat only) ---
            if cur is None:
                if brk_up:
                    cur = 'long'
                    signals.append(self._sig('ENTRY', 'long', real[k], ts[k], box, 'CONT_LONG'))
                elif brk_dn:
                    cur = 'short'
                    signals.append(self._sig('ENTRY', 'short', real[k], ts[k], box, 'CONT_SHORT'))
                elif trend == 1 and self.PB_MIN <= depth_prev <= K and rc[k] > rc[p] and depth <= K:
                    cur = 'long'
                    signals.append(self._sig('ENTRY', 'long', real[k], ts[k], box, 'PULLBACK_LONG'))
                elif trend == -1 and self.PB_MIN <= depth_prev <= K and rc[k] < rc[p] and depth <= K:
                    cur = 'short'
                    signals.append(self._sig('ENTRY', 'short', real[k], ts[k], box, 'PULLBACK_SHORT'))

            depth_prev = depth
        return signals
