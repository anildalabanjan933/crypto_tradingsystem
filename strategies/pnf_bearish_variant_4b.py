# strategies/pnf_bearish_variant_4b.py

import pandas as pd
import numpy as np
from data.data_loader import DataLoader
from data.data_aggregator import DataAggregator
from indicators.pnf import PnFChartBuilder
from strategies.base_strategy import BaseStrategy


# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
DATA_FILE  = 'data/btc_1m_delta.csv'
DATE_FROM  = '2025-06-11'
DATE_TO    = '2026-06-11'
BOX_SIZE   = 0.15
REVERSAL   = 3
ADX_PERIOD = 14
ADX_THRESH = 20
SMA_SHORT  = 10
SMA_LONG   = 20


# ─────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────

def calc_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high  = df['high']
    low   = df['low']
    close = df['close']

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs()
    ], axis=1).max(axis=1)

    up   = high - high.shift(1)
    down = low.shift(1) - low

    plus_dm  = np.where((up > down) & (up > 0),  up,   0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    def wilder_smooth(arr, n):
        result = np.full(len(arr), np.nan)
        seed_idx = n - 1
        while seed_idx < len(arr) and np.isnan(arr[seed_idx]):
            seed_idx += 1
        if seed_idx >= len(arr):
            return pd.Series(result, index=df.index)
        result[seed_idx] = np.nansum(arr[max(0, seed_idx - n + 1): seed_idx + 1])
        for i in range(seed_idx + 1, len(arr)):
            result[i] = result[i-1] - (result[i-1] / n) + arr[i]
        return pd.Series(result, index=df.index)

    atr      = wilder_smooth(tr.values,      period)
    plus_di  = 100 * wilder_smooth(plus_dm,  period) / atr
    minus_di = 100 * wilder_smooth(minus_dm, period) / atr

    dx  = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).fillna(0)
    adx = wilder_smooth(dx.values, period)
    return adx


# ─────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────

def get_bar_idx(ts_index: pd.Index, ts) -> int:
    mask = ts_index <= ts
    if not mask.any():
        return 0
    return int(np.nonzero(mask)[0][-1])


# ─────────────────────────────────────────
# PATTERN DETECTION
# ─────────────────────────────────────────

def detect_entry_signals(cols, ts_index, sma10, sma20, adx_series,
                         first_entry_done, sma10_above_sma20_flag):
    signals = []
    n = len(cols)

    for i in range(n - 4):
        o1 = cols[i]
        x1 = cols[i + 1]
        o2 = cols[i + 2]

        if o1['type'] != 'O': continue
        if x1['type'] != 'X': continue
        if o2['type'] != 'O': continue

        o1_bottom = o1['end_level']
        o2_end    = o2['end_level']
        box       = o1_bottom * (BOX_SIZE / 100.0)

        if not (o2_end <= o1_bottom - box):
            continue
        if i + 4 >= n:
            continue

        signal_col  = cols[i + 4]
        entry_ts    = signal_col['end_timestamp']
        entry_price = o2_end
        bar_idx     = get_bar_idx(ts_index, entry_ts)

        if not first_entry_done:
            adx_val = adx_series.iloc[bar_idx]
            if pd.isna(adx_val) or adx_val <= ADX_THRESH:
                continue

            x1_bar_idx  = get_bar_idx(ts_index, x1['end_timestamp'])
            sma10_at_x1 = sma10.iloc[x1_bar_idx]
            sma20_at_x1 = sma20.iloc[x1_bar_idx]
            x1_high     = x1['high']
            x1_low      = x1['low']

            touches_sma = False
            for sma_val in [sma10_at_x1, sma20_at_x1]:
                if pd.isna(sma_val):
                    continue
                if x1_low <= sma_val <= x1_high:
                    touches_sma = True
                    break
            if not touches_sma:
                continue

        else:
            if sma10_above_sma20_flag:
                continue
            s10 = sma10.iloc[bar_idx]
            s20 = sma20.iloc[bar_idx]
            if pd.isna(s10) or pd.isna(s20) or s10 >= s20:
                continue

        signals.append({
            'entry_ts':    entry_ts,
            'entry_price': entry_price,
            'sl_level':    o2['start_level'],
            'col_o1_idx':  i,
            'col_x1_idx':  i + 1,
            'col_o2_idx':  i + 2,
        })

    return signals


def detect_exit_signals(cols):
    signals = []
    n = len(cols)

    for i in range(n - 4):
        x1 = cols[i]
        om = cols[i + 1]
        x2 = cols[i + 2]

        if x1['type'] != 'X': continue
        if om['type'] != 'O': continue
        if x2['type'] != 'X': continue

        x1_top = x1['end_level']
        x2_end = x2['end_level']
        box    = x1_top * (BOX_SIZE / 100.0)

        if not (x2_end >= x1_top + box):
            continue
        if i + 4 >= n:
            continue

        signal_col = cols[i + 4]
        signals.append({
            'exit_ts':    signal_col['end_timestamp'],
            'exit_price': x2_end,
            'col_x1_idx': i,
            'col_om_idx': i + 1,
            'col_x2_idx': i + 2,
        })

    return signals


# ─────────────────────────────────────────
# BACKTEST ENGINE
# ─────────────────────────────────────────

def run_backtest(cols, df_1h, sma10, sma20, adx_series):
    trades = []

    in_trade         = False
    first_entry_done = False
    sma10_above_flag = False

    entry_ts    = None
    entry_price = None
    sl_level    = None
    trade_count = 0

    ts_index         = df_1h.index
    all_exits        = detect_exit_signals(cols)
    all_exits_sorted = sorted(all_exits, key=lambda x: x['exit_ts'])

    raw_entries = []
    n = len(cols)
    for i in range(n - 4):
        o1 = cols[i]
        x1 = cols[i + 1]
        o2 = cols[i + 2]

        if o1['type'] != 'O': continue
        if x1['type'] != 'X': continue
        if o2['type'] != 'O': continue

        o1_bottom = o1['end_level']
        o2_end    = o2['end_level']
        box       = o1_bottom * (BOX_SIZE / 100.0)

        if not (o2_end <= o1_bottom - box):
            continue
        if i + 4 >= n:
            continue

        signal_col = cols[i + 4]
        raw_entries.append({
            'ts':        signal_col['end_timestamp'],
            'price':     o2_end,
            'sl':        o2['start_level'],
            'x1_end_ts': x1['end_timestamp'],
            'x1_high':   x1['high'],
            'x1_low':    x1['low'],
            'col_i':     i,
        })

    raw_entries.sort(key=lambda x: x['ts'])

    entry_ptr              = 0
    exit_ptr               = 0
    used_entry_col_indices = set()

    for bar_pos, bar_ts in enumerate(ts_index):

        s10 = sma10.iloc[bar_pos]
        s20 = sma20.iloc[bar_pos]
        if not pd.isna(s10) and not pd.isna(s20):
            sma10_above_flag = s10 > s20
        else:
            sma10_above_flag = False

        if in_trade:
            bar_high = df_1h['high'].iloc[bar_pos]
            if bar_high >= sl_level:
                trades.append({
                    'trade_no':    trade_count,
                    'entry_ts':    entry_ts,
                    'entry_price': entry_price,
                    'exit_ts':     bar_ts,
                    'exit_price':  sl_level,
                    'exit_reason': 'SL',
                    'pnl_pct':     round((entry_price - sl_level) / entry_price * 100, 4),
                })
                in_trade = False
                sl_level = None

        if in_trade:
            while exit_ptr < len(all_exits_sorted):
                ex = all_exits_sorted[exit_ptr]
                if ex['exit_ts'] <= bar_ts:
                    if ex['exit_ts'] > entry_ts:
                        trades.append({
                            'trade_no':    trade_count,
                            'entry_ts':    entry_ts,
                            'entry_price': entry_price,
                            'exit_ts':     ex['exit_ts'],
                            'exit_price':  ex['exit_price'],
                            'exit_reason': 'PATTERN',
                            'pnl_pct':     round((entry_price - ex['exit_price']) / entry_price * 100, 4),
                        })
                        in_trade = False
                        sl_level = None
                        exit_ptr += 1
                        break
                    exit_ptr += 1
                else:
                    break

        if not in_trade:
            while entry_ptr < len(raw_entries):
                en = raw_entries[entry_ptr]
                if en['ts'] <= bar_ts:
                    if en['col_i'] in used_entry_col_indices:
                        entry_ptr += 1
                        continue

                    valid = False

                    if not first_entry_done:
                        adx_bar = get_bar_idx(ts_index, en['ts'])
                        adx_val = adx_series.iloc[adx_bar]
                        if pd.isna(adx_val) or adx_val <= ADX_THRESH:
                            entry_ptr += 1
                            continue

                        x1_bar = get_bar_idx(ts_index, en['x1_end_ts'])
                        s10_x1 = sma10.iloc[x1_bar]
                        s20_x1 = sma20.iloc[x1_bar]
                        touches = False
                        for sv in [s10_x1, s20_x1]:
                            if not pd.isna(sv) and en['x1_low'] <= sv <= en['x1_high']:
                                touches = True
                                break
                        if not touches:
                            entry_ptr += 1
                            continue

                        valid = True

                    else:
                        if sma10_above_flag:
                            entry_ptr += 1
                            continue
                        valid = True

                    if valid:
                        trade_count     += 1
                        in_trade         = True
                        first_entry_done = True
                        entry_ts         = en['ts']
                        entry_price      = en['price']
                        sl_level         = en['sl']
                        used_entry_col_indices.add(en['col_i'])
                        entry_ptr       += 1
                        break

                    entry_ptr += 1
                else:
                    break

    if in_trade:
        last_close = df_1h['close'].iloc[-1]
        last_ts    = ts_index[-1]
        trades.append({
            'trade_no':    trade_count,
            'entry_ts':    entry_ts,
            'entry_price': entry_price,
            'exit_ts':     last_ts,
            'exit_price':  last_close,
            'exit_reason': 'END_OF_DATA',
            'pnl_pct':     round((entry_price - last_close) / entry_price * 100, 4),
        })

    return trades


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    loader = DataLoader(DATA_FILE)
    loader.load_data()
    loader.filter_by_date_range(DATE_FROM, DATE_TO)
    data_1m = loader.data

    aggregator = DataAggregator(data_1m)
    data_1h    = aggregator.get_1h_data()

    builder = PnFChartBuilder(BOX_SIZE, REVERSAL)
    cols    = builder.build_pnf_chart(data_1h)

    print(f"Total PnF columns : {len(cols)}")
    print(f"Total 1H bars     : {len(data_1h)}")

    n_debug = len(cols)
    raw_entry_count = 0
    for i in range(n_debug - 4):
        o1 = cols[i]; x1 = cols[i+1]; o2 = cols[i+2]
        if o1['type'] != 'O': continue
        if x1['type'] != 'X': continue
        if o2['type'] != 'O': continue
        box = o1['end_level'] * (BOX_SIZE / 100.0)
        if o2['end_level'] <= o1['end_level'] - box:
            raw_entry_count += 1
            if raw_entry_count <= 10:
                print(f"  RAW ENTRY #{raw_entry_count}: col_i={i}  "
                      f"ts={cols[i+4]['end_timestamp']}  "
                      f"price={o2['end_level']:.2f}  "
                      f"sl={o2['start_level']:.2f}")

    print(f"Total raw O-X-O entry patterns : {raw_entry_count}")

    raw_exit_count = 0
    for i in range(n_debug - 4):
        x1 = cols[i]; om = cols[i+1]; x2 = cols[i+2]
        if x1['type'] != 'X': continue
        if om['type'] != 'O': continue
        if x2['type'] != 'X': continue
        box = x1['end_level'] * (BOX_SIZE / 100.0)
        if x2['end_level'] >= x1['end_level'] + box:
            raw_exit_count += 1

    print(f"Total raw X-O-X exit patterns  : {raw_exit_count}")
    print("-" * 60)

    sma10      = calc_sma(data_1h['close'], SMA_SHORT)
    sma20      = calc_sma(data_1h['close'], SMA_LONG)
    adx_series = calc_adx(data_1h, ADX_PERIOD)

    trades = run_backtest(cols, data_1h, sma10, sma20, adx_series)

    print(f"\nTotal trades: {len(trades)}\n")
    print(f"{'#':<6} {'Entry Time':<22} {'Entry Price':>12} {'Exit Time':<22} "
          f"{'Exit Price':>12} {'Reason':<12} {'PnL %':>8}")
    print("-" * 100)
    for t in trades:
        print(
            f"{t['trade_no']:<6} "
            f"{str(t['entry_ts']):<22} "
            f"{t['entry_price']:>12.2f} "
            f"{str(t['exit_ts']):<22} "
            f"{t['exit_price']:>12.2f} "
            f"{t['exit_reason']:<12} "
            f"{t['pnl_pct']:>8.4f}%"
        )

    if trades:
        wins      = [t for t in trades if t['pnl_pct'] > 0]
        losses    = [t for t in trades if t['pnl_pct'] <= 0]
        total_pnl = sum(t['pnl_pct'] for t in trades)
        print(f"\nWins   : {len(wins)}")
        print(f"Losses : {len(losses)}")
        print(f"Win %  : {len(wins)/len(trades)*100:.1f}%")
        print(f"Total PnL (sum of % per trade): {total_pnl:.4f}%")


if __name__ == '__main__':
    main()


# ============================================================
# BaseStrategy wrapper — required for menu registration
# ============================================================

class PnFBearishVariant4B(BaseStrategy):
    """
    Bearish PnF Double Bottom Breakdown strategy (Variant 4B).
    Wraps the standalone backtest engine for menu integration.
    """

    @property
    def required_timeframes(self):
        return ['1H']

    @property
    def optimization_params(self):
        return {
            'adx_threshold': {'default': 20, 'min': 15, 'max': 35, 'step': 5},
            'box_size':      {'default': 0.15, 'min': 0.10, 'max': 0.30, 'step': 0.05},
            'reversal':      {'default': 3, 'min': 2, 'max': 5, 'step': 1},
        }

    def generate_signals(self):
        df_1h = self.get_data('1H')

        cols       = PnFChartBuilder(BOX_SIZE, REVERSAL).build_pnf_chart(df_1h)
        sma10      = calc_sma(df_1h['close'], SMA_SHORT)
        sma20      = calc_sma(df_1h['close'], SMA_LONG)
        adx_series = calc_adx(df_1h, ADX_PERIOD)
        ts_index   = df_1h.index

        raw_entries = []
        n = len(cols)
        for i in range(n - 4):
            o1 = cols[i]
            x1 = cols[i + 1]
            o2 = cols[i + 2]

            if o1['type'] != 'O': continue
            if x1['type'] != 'X': continue
            if o2['type'] != 'O': continue

            o1_bottom = o1['end_level']
            o2_end    = o2['end_level']
            box       = o1_bottom * (BOX_SIZE / 100.0)

            if not (o2_end <= o1_bottom - box):
                continue
            if i + 4 >= n:
                continue

            signal_col = cols[i + 4]
            raw_entries.append({
                'ts':        signal_col['end_timestamp'],
                'price':     o2_end,
                'sl':        o2['start_level'],
                'x1_end_ts': x1['end_timestamp'],
                'x1_high':   x1['high'],
                'x1_low':    x1['low'],
                'col_i':     i,
            })

        raw_entries.sort(key=lambda x: x['ts'])

        signals          = []
        first_entry_done = False
        used_col_indices = set()

        for en in raw_entries:
            if en['col_i'] in used_col_indices:
                continue

            bar_idx = get_bar_idx(ts_index, en['ts'])

            if not first_entry_done:
                adx_val = adx_series.iloc[bar_idx]
                if pd.isna(adx_val) or adx_val <= ADX_THRESH:
                    continue

                x1_bar = get_bar_idx(ts_index, en['x1_end_ts'])
                s10_x1 = sma10.iloc[x1_bar]
                s20_x1 = sma20.iloc[x1_bar]
                touches = False
                for sv in [s10_x1, s20_x1]:
                    if not pd.isna(sv) and en['x1_low'] <= sv <= en['x1_high']:
                        touches = True
                        break
                if not touches:
                    continue

            else:
                s10 = sma10.iloc[bar_idx]
                s20 = sma20.iloc[bar_idx]
                if pd.isna(s10) or pd.isna(s20) or s10 >= s20:
                    continue

            entry_type = 'FIRST_ENTRY' if not first_entry_done else 'RE_ENTRY'
            used_col_indices.add(en['col_i'])
            first_entry_done = True

            signals.append({
                'signal_type': 'ENTRY',
                'entry_type':  entry_type,
                'timestamp':   en['ts'],
                'price':       en['price'],
                'sl_price':    en['sl'],
                'reason':      'PnF Double Bottom Breakdown (O-X-O)',
            })

        all_exits = detect_exit_signals(cols)
        for ex in all_exits:
            signals.append({
                'signal_type': 'EXIT',
                'exit_type':   'DOUBLE_TOP',
                'timestamp':   ex['exit_ts'],
                'price':       ex['exit_price'],
                'reason':      'PnF Double Top Breakout (X-O-X)',
            })

        self.signals = signals
        return signals
