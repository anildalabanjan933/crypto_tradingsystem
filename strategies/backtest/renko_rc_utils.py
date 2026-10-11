# strategies/backtest/renko_rc_utils.py
# Shared helpers for V5 strategies. real_close + last_of_bar built in.
import numpy as np
import pandas as pd
from indicators.renko import RenkoBuilder

TF_TD = {'1m': '1min', '5m': '5min', '15m': '15min', '30m': '30min',
         '1h': '1h', '2h': '2h', '4h': '4h', '1d': '1D'}


def tf_delta(tf: str) -> pd.Timedelta:
    return pd.Timedelta(TF_TD.get(tf, tf))


def build_renko_rc(data: dict, tf: str, box_pct: float, reference_price=None):
    """Renko bricks from tf closes. Adds: timestamp (candle LABEL), real_close
    (close of the SAME candle that produced the brick), last_of_bar (True only
    for the last brick of each source candle)."""
    df_tf = data.get(tf)
    if df_tf is None or len(df_tf) == 0:
        raise ValueError(f"Requires '{tf}' timeframe data")
    closes = df_tf['close'].values
    ts = (df_tf.index if isinstance(df_tf.index, pd.DatetimeIndex)
          else pd.to_datetime(df_tf['timestamp']))
    anchor = reference_price if reference_price else closes[0]
    box = max(1, round(anchor * box_pct))
    raw = RenkoBuilder(box_size=box, reference_price=anchor).build(closes)
    if raw is None or len(raw) == 0:
        raise ValueError("RenkoBuilder produced no bricks")
    idx = raw['bar_index'].values.copy()
    idx[idx > len(closes) - 1] = len(closes) - 1
    tsv = ts.values if hasattr(ts, 'values') else np.asarray(ts)
    raw['timestamp'] = tsv[idx]
    raw['real_close'] = closes[idx]
    last = np.ones(len(raw), dtype=bool)
    last[:-1] = idx[1:] != idx[:-1]
    raw['last_of_bar'] = last
    return raw, box


def slip(price, direction, is_entry, slippage_usd):
    if direction == 'long':
        return price + slippage_usd if is_entry else price - slippage_usd
    return price - slippage_usd if is_entry else price + slippage_usd


def tsfmt(t):
    return pd.Timestamp(t).strftime('%Y-%m-%dT%H:%M:%S')
