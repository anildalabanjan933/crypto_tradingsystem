# indicators/ema.py
# Responsibility: Calculate EMA (Exponential Moving Average)

import pandas as pd


def calculate_ema(close_prices, period):
    """
    Calculate EMA (Exponential Moving Average).

    Parameters
    ----------
    close_prices : pd.Series
        Close prices
    period : int
        EMA period

    Returns
    -------
    pd.Series
        EMA values
    """
    return close_prices.ewm(span=period, adjust=False).mean()
