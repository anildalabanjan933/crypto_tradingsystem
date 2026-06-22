# data/data_aggregator.py
# Responsibility: Aggregate 1M OHLCV data to multiple timeframes

import pandas as pd


class DataAggregator:
    """
    Aggregates 1M OHLCV data to multiple timeframes.
    Supports: 1M → 5M → 15M → 30M → 1H → 4H → 1D

    All output DataFrames use lowercase column names:
    open, high, low, close, volume
    Consistent with data_loader.py and all downstream consumers.
    """

    def __init__(self, data_1m):
        """
        Initialize DataAggregator with 1M data.

        Parameters
        ----------
        data_1m : pd.DataFrame
            1M OHLCV data with datetime index and lowercase columns
        """
        self.data_1m   = data_1m.sort_index()
        self.data_5m   = None
        self.data_15m  = None
        self.data_30m  = None
        self.data_1h   = None
        self.data_4h   = None
        self.data_daily = None

        # Pre-aggregate all timeframes
        self._aggregate_all()

    def _aggregate_all(self):
        """Pre-aggregate all timeframes from 1M data."""
        print("Aggregating timeframes...")
        self.data_5m    = self._resample('5min',  '5M')
        self.data_15m   = self._resample('15min', '15M')
        self.data_30m   = self._resample('30min', '30M')
        self.data_1h    = self._resample('1h',    '1H')
        self.data_4h    = self._resample('4h',    '4H')
        self.data_daily = self._resample('1D',    'Daily')

    def _resample(self, freq, label):
        """
        Resample OHLCV data to specified frequency.

        Parameters
        ----------
        freq : str
            Pandas frequency string (e.g., '5min', '1h', '1D')
        label : str
            Label for logging (e.g., '5M', '1H')

        Returns
        -------
        pd.DataFrame
            Resampled OHLCV data with lowercase columns
        """
        # All lowercase — matches data_loader.py output
        agg_dict = {
            'open'  : 'first',
            'high'  : 'max',
            'low'   : 'min',
            'close' : 'last',
            'volume': 'sum'
        }

        try:
            resampled = self.data_1m.resample(freq).agg(agg_dict)

            # Remove rows with NaN (incomplete candles / gaps)
            resampled = resampled.dropna()

            print(f"✅ Aggregated to {label}: {len(resampled)} candles")
            return resampled

        except Exception as e:
            print(f"❌ Error aggregating to {label}: {e}")
            return None

    # ── Getters ────────────────────────────────────────────────────────

    def get_1m_data(self):
        """Get 1M data."""
        return self.data_1m

    def get_5m_data(self):
        """Get 5M data."""
        return self.data_5m

    def get_15m_data(self):
        """Get 15M data."""
        return self.data_15m

    def get_30m_data(self):
        """Get 30M data."""
        return self.data_30m

    def get_1h_data(self):
        """Get 1H data."""
        return self.data_1h

    def get_4h_data(self):
        """Get 4H data."""
        return self.data_4h

    def get_daily_data(self):
        """Get Daily data."""
        return self.data_daily

    def validate_continuity(self, data, timeframe):
        """
        Validate data continuity for a timeframe.

        Parameters
        ----------
        data : pd.DataFrame
            OHLCV data
        timeframe : str
            Timeframe name (e.g., '1H', '15M')
        """
        if data is None or len(data) == 0:
            print(f"⚠️  {timeframe}: No data available")
            return

        if len(data) > 1:
            time_diffs = data.index.to_series().diff()

            freq_map = {
                '1M'   : pd.Timedelta(minutes=1),
                '5M'   : pd.Timedelta(minutes=5),
                '15M'  : pd.Timedelta(minutes=15),
                '30M'  : pd.Timedelta(minutes=30),
                '1H'   : pd.Timedelta(hours=1),
                '4H'   : pd.Timedelta(hours=4),
                'Daily': pd.Timedelta(days=1),
            }

            expected_freq = freq_map.get(timeframe, pd.Timedelta(hours=1))

            # Find gaps (more than 1.5x expected frequency)
            gaps = time_diffs[time_diffs > expected_freq * 1.5]

            if len(gaps) > 0:
                print(f"⚠️  {timeframe}: Found {len(gaps)} gaps in data")
            else:
                print(f"✅ {timeframe}: Data is continuous")
