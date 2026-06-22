# indicators/dmi.py
# Responsibility: Calculate DMI (Directional Movement Index)
# Returns DI+ (Plus Directional Indicator) and DI- (Minus Directional Indicator)
# Used for trend direction in 4H and 1H timeframes

import pandas as pd
import numpy as np


# Function-based implementation as expected by strategies/bullish_trend_pullback.py
def calculate_dmi(high, low, close, period=14):
    """
    Calculate DI+ and DI- for given OHLC data.

    Parameters
    ----------
    high : pd.Series
        High prices
    low : pd.Series
        Low prices
    close : pd.Series
        Close prices
    period : int
        DMI period (default: 14)

    Returns
    -------
    pd.DataFrame
        DataFrame with 'DI+' and 'DI-' columns
    """
    # Calculate True Range
    tr1 = high - low
    tr2 = np.abs(high - close.shift(1))
    tr3 = np.abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Calculate Directional Movement
    up_move = high.diff()
    down_move = low.diff()

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=low.index)

    # Smooth using Wilder's method (EMA-like smoothing)
    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr

    return pd.DataFrame({'DI+': plus_di, 'DI-': minus_di}, index=high.index)

