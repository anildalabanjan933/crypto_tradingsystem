# indicators/sma.py
# Responsibility: Calculate SMA (Simple Moving Average)
# Used for 1H confirmation (SMA10, SMA20)

import pandas as pd


# Function-based implementation as expected by strategies/bullish_trend_pullback.py
def calculate_sma(close_prices, period):
    """
    Calculate SMA (Simple Moving Average).

    Parameters
    ----------
    close_prices : pd.Series
        Close prices
    period : int
        SMA period

    Returns
    -------
    pd.Series
        SMA values
    """
    sma = close_prices.rolling(window=period).mean()

    return sma
