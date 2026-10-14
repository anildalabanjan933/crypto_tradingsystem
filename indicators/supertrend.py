"""
Supertrend Indicator
Calculated on candlestick OHLCV data (not PnF columns)
Returns pd.DataFrame with upper_band, lower_band, supertrend, trend columns
"""

import pandas as pd
import numpy as np


class Supertrend:
    def __init__(self, period: int = 10, multiplier: float = 3.0):
        self.period = period
        self.multiplier = multiplier

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates Supertrend for a given OHLCV DataFrame.

        Args:
            df: DataFrame with 'high', 'low', 'close' columns
                Index must be DatetimeIndex (tz-naive) for .asof() to work

        Returns:
            pd.DataFrame with columns:
                upper_band  : always above price (use as SL for short positions)
                lower_band  : always below price (use as SL for long positions)
                supertrend  : switching line (active SL based on trend direction)
                trend       : 1 = uptrend, -1 = downtrend
        """
        if len(df) < self.period:
            empty = pd.DataFrame({
                'upper_band' : [np.nan] * len(df),
                'lower_band' : [np.nan] * len(df),
                'supertrend' : [np.nan] * len(df),
                'trend'      : [np.nan] * len(df),
            }, index=df.index)
            return empty

        # ── Step 1: True Range ──────────────────────────────────────────
        high_low        = df['high'] - df['low']
        high_prev_close = abs(df['high'] - df['close'].shift(1))
        low_prev_close  = abs(df['low']  - df['close'].shift(1))

        tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

        # ── Step 2: ATR (Wilder's EMA) ──────────────────────────────────
        atr = tr.ewm(span=self.period, adjust=False).mean()

        # ── Step 3: Basic Bands ─────────────────────────────────────────
        hl2         = (df['high'] + df['low']) / 2
        basic_upper = hl2 + (self.multiplier * atr)
        basic_lower = hl2 - (self.multiplier * atr)

        # ── Step 4: Final Bands (carry-forward logic) ───────────────────
        final_upper = basic_upper.copy().astype(float)
        final_lower = basic_lower.copy().astype(float)

        for i in range(1, len(df)):
            # Upper band: only tighten (move down), never widen
            if basic_upper.iloc[i] < final_upper.iloc[i - 1]:
                final_upper.iloc[i] = basic_upper.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i - 1]

            # Lower band: only tighten (move up), never widen
            if basic_lower.iloc[i] > final_lower.iloc[i - 1]:
                final_lower.iloc[i] = basic_lower.iloc[i]
            else:
                final_lower.iloc[i] = final_lower.iloc[i - 1]

        # ── Step 5: Trend Direction ─────────────────────────────────────
        trend      = pd.Series(np.nan, index=df.index)
        supertrend = pd.Series(np.nan, index=df.index)

        trend.iloc[0]      = 1
        supertrend.iloc[0] = final_lower.iloc[0]

        for i in range(1, len(df)):
            prev_trend = trend.iloc[i - 1]
            close      = df['close'].iloc[i]

            if prev_trend == 1:
                if close < final_lower.iloc[i]:
                    trend.iloc[i]      = -1
                    supertrend.iloc[i] = final_upper.iloc[i]
                else:
                    trend.iloc[i]      = 1
                    supertrend.iloc[i] = final_lower.iloc[i]
            else:
                if close > final_upper.iloc[i]:
                    trend.iloc[i]      = 1
                    supertrend.iloc[i] = final_lower.iloc[i]
                else:
                    trend.iloc[i]      = -1
                    supertrend.iloc[i] = final_upper.iloc[i]

        # ── Step 6: Return full DataFrame ──────────────────────────────
        return pd.DataFrame({
            'upper_band' : final_upper,
            'lower_band' : final_lower,
            'supertrend' : supertrend,
            'trend'      : trend,
        }, index=df.index)
