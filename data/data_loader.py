# data/data_loader.py
# Responsibility: Load and validate OHLCV data from CSV

import pandas as pd


class DataLoader:
    """
    Loads and validates OHLCV data from CSV file.
    Expects 1M candle data as base timeframe.
    """

    def __init__(self, csv_path):
        """
        Initialize DataLoader.

        Parameters
        ----------
        csv_path : str
            Path to CSV file containing 1M OHLCV data
        """
        self.csv_path = csv_path
        self.data = None

    def load_data(self):
        """
        Load 1M OHLCV data from CSV.

        Returns
        -------
        pd.DataFrame
            OHLCV data with datetime index
        """
        try:
            df = pd.read_csv(self.csv_path)

            # Ensure timestamp column exists
            if 'timestamp' not in df.columns:
                raise ValueError("CSV must contain 'timestamp' column")

            # Convert timestamp to datetime (Unix epoch seconds → tz-naive UTC)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            df.set_index('timestamp', inplace=True)

            # Normalize all column names to lowercase
            # This ensures consistency across all downstream consumers:
            # supertrend.py, pnf.py, pnf_indicators.py all use lowercase
            df.columns = df.columns.str.lower()

            required_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in required_cols:
                if col not in df.columns:
                    raise ValueError(f"CSV must contain '{col}' column")

            # Ensure numeric types
            for col in required_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # Drop rows where any OHLCV value is NaN after coercion
            df = df.dropna(subset=required_cols)

            # Sort by timestamp
            df = df.sort_index()

            self.data = df
            print(f"✅ Loaded {len(df)} 1M candles from {self.csv_path}")
            return df

        except FileNotFoundError:
            print(f"❌ CSV file not found: {self.csv_path}")
            return None
        except Exception as e:
            print(f"❌ Error loading CSV: {e}")
            return None

    def validate_format(self):
        """
        Validate CSV format.

        Returns
        -------
        bool
            True if format is valid
        """
        if self.data is None:
            print("❌ No data loaded")
            return False

        required_cols = ['open', 'high', 'low', 'close', 'volume']

        for col in required_cols:
            if col not in self.data.columns:
                print(f"❌ Missing column: {col}")
                return False

        # Check for numeric values
        for col in required_cols:
            if not pd.api.types.is_numeric_dtype(self.data[col]):
                print(f"❌ Column {col} is not numeric")
                return False

        print("✅ CSV format is valid")
        return True

    def filter_by_date_range(self, start_date, end_date):
        """
        Filter data by date range.

        Parameters
        ----------
        start_date : str
            Start date (YYYY-MM-DD)
        end_date : str
            End date (YYYY-MM-DD)

        Returns
        -------
        pd.DataFrame
            Filtered data
        """
        if self.data is None:
            print("❌ No data loaded")
            return None

        start = pd.to_datetime(start_date)
        end   = pd.to_datetime(end_date)

        filtered = self.data[
            (self.data.index >= start) & (self.data.index <= end)
        ]

        print(f"✅ Filtered {len(filtered)} candles for {start_date} to {end_date}")
        return filtered

    def validate_data_continuity(self):
        """
        Validate data continuity (check for gaps).

        Returns
        -------
        bool
            True if data is continuous
        """
        if self.data is None or len(self.data) < 2:
            print("⚠️  Insufficient data to validate continuity")
            return False

        # Expected frequency: 1 minute
        expected_freq = pd.Timedelta(minutes=1)

        # Calculate time differences
        time_diffs = self.data.index.to_series().diff()

        # Find gaps (more than 1.5x expected frequency)
        gaps = time_diffs[time_diffs > expected_freq * 1.5]

        if len(gaps) > 0:
            print(f"⚠️  Found {len(gaps)} gaps in data")
            return False
        else:
            print(f"✅ Data is continuous (1M candles)")
            return True
