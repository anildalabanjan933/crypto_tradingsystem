# indicators/rsi.py
# Responsibility: Calculate RSI (Relative Strength Index)

import pandas as pd
import numpy as np


def calculate_rsi(close_prices, period=14):
    """
    Calculate RSI (Relative Strength Index).

    Parameters
    ----------
    close_prices : pd.Series
        Close prices
    period : int
        RSI period (default: 14)

    Returns
    -------
    pd.Series
        RSI values (0-100)
    """
    # Calculate price changes
    delta = close_prices.diff()

    # Separate gains and losses
    gains = delta.where(delta > 0, 0)
    losses = -delta.where(delta < 0, 0)

    # Calculate average gains and losses
    avg_gains = gains.rolling(window=period).mean()
    avg_losses = losses.rolling(window=period).mean()

    # Calculate RS and RSI
    rs = avg_gains / avg_losses
    rsi = 100 - (100 / (1 + rs))

    return rsi
