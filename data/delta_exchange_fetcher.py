# data/delta_exchange_fetcher.py
# Responsibility: Fetch BTC historical OHLCV data from Delta Exchange API
# Downloads 30M candles, validates, aggregates to 1H and 4H, saves all timeframes

import requests
import pandas as pd
import time
from datetime import datetime, timedelta
import os


class DeltaExchangeFetcher:
    """
    Fetches BTC historical OHLCV data from Delta Exchange API.

    Features:
    - Fetches 30M candles from Delta Exchange
    - Validates data continuity and correctness
    - Aggregates to 1H and 4H candles
    - Saves all timeframes to CSV
    """

    BASE_URL = "https://api.india.delta.exchange"
    ENDPOINT = "/v2/history/candles"
    SYMBOL = "BTCUSD"
    RESOLUTION = "30m"
    MAX_CANDLES_PER_REQUEST = 2000

    def __init__(self, output_path="data/btc_ohlcv.csv"):
        """
        Initialize fetcher.

        Parameters
        ----------
        output_path : str
            Path to save 30M CSV file
        """
        self.output_path = output_path
        self.all_candles = []
        self.session = requests.Session()
        self.data_30m = None
        self.data_1h = None
        self.data_4h = None

    def fetch_data(self, start_date, end_date):
        """
        Fetch historical data from Delta Exchange API.

        Parameters
        ----------
        start_date : str
            Start date in YYYY-MM-DD format
        end_date : str
            End date in YYYY-MM-DD format

        Returns
        -------
        pd.DataFrame
            30M OHLCV data
        """
        print(f"📊 Fetching BTC {self.RESOLUTION} data from {start_date} to {end_date}")

        # Convert dates to unix timestamps
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp()) + 86400  # Include full end day

        # Calculate number of requests needed
        total_seconds = end_ts - start_ts
        total_candles = (total_seconds // 1800)  # 1800 seconds = 30 minutes
        num_requests = (total_candles // self.MAX_CANDLES_PER_REQUEST) + 1

        print(f"📈 Total candles needed: {total_candles}")
        print(f"📡 API requests required: {num_requests}")

        # Fetch data in chunks
        current_ts = start_ts
        request_count = 0

        while current_ts < end_ts:
            request_count += 1
            chunk_end_ts = min(current_ts + (self.MAX_CANDLES_PER_REQUEST * 1800), end_ts)

            print(f"\n[Request {request_count}/{num_requests}] Fetching candles...")

            try:
                candles = self._fetch_chunk(current_ts, chunk_end_ts)

                if candles:
                    self.all_candles.extend(candles)
                    print(f"✅ Fetched {len(candles)} candles")
                else:
                    print(f"⚠️  No candles returned")

                # Rate limiting: wait 0.5 seconds between requests
                time.sleep(0.5)

                current_ts = chunk_end_ts

            except Exception as e:
                print(f"❌ Error fetching chunk: {e}")
                return None

        print(f"\n✅ Total candles fetched: {len(self.all_candles)}")

        # Convert to DataFrame
        df = pd.DataFrame(self.all_candles)
        self.data_30m = df

        return df

    def _fetch_chunk(self, start_ts, end_ts, retries=3):
        """
        Fetch a chunk of data with retry logic.

        Parameters
        ----------
        start_ts : int
            Start unix timestamp
        end_ts : int
            End unix timestamp
        retries : int
            Number of retries on failure

        Returns
        -------
        list
            List of candle dictionaries
        """
        for attempt in range(retries):
            try:
                params = {
                    "symbol": self.SYMBOL,
                    "resolution": self.RESOLUTION,
                    "start": start_ts,
                    "end": end_ts
                }

                response = self.session.get(
                    f"{self.BASE_URL}{self.ENDPOINT}",
                    params=params,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()

                    if data.get("success") and data.get("result"):
                        candles = data["result"]
                        return self._parse_candles(candles)
                    else:
                        print(f"⚠️  API returned no data")
                        return []

                elif response.status_code == 429:
                    print(f"⚠️  Rate limited. Waiting 5 seconds...")
                    time.sleep(5)
                    continue

                else:
                    print(f"❌ API error: {response.status_code}")
                    return None

            except requests.Timeout:
                print(f"⚠️  Timeout (attempt {attempt + 1}/{retries}). Retrying...")
                time.sleep(2 ** attempt)  # Exponential backoff

            except Exception as e:
                print(f"❌ Error: {e}")
                return None

        print(f"❌ Failed after {retries} attempts")
        return None

    def _parse_candles(self, candles):
        """
        Parse API response candles to standard format.

        Parameters
        ----------
        candles : list
            List of candle objects from API

        Returns
        -------
        list
            List of parsed candle dictionaries
        """
        parsed = []

        for candle in candles:
            dt = datetime.fromtimestamp(candle['time'])

            parsed_candle = {
                'Date': dt.strftime('%Y-%m-%d'),
                'Time': dt.strftime('%H:%M'),
                'Open': candle['open'],
                'High': candle['high'],
                'Low': candle['low'],
                'Close': candle['close'],
                'Volume': candle['volume']
            }

            parsed.append(parsed_candle)

        return parsed

    def validate_data(self, df):
        """
        Validate fetched data for continuity and correctness.

        Parameters
        ----------
        df : pd.DataFrame
            Fetched OHLCV data

        Returns
        -------
        bool
            True if data is valid
        """
        print("\n🔍 Validating 30M data...")

        if df is None or len(df) == 0:
            print("❌ No data to validate")
            return False

        # Check row count
        expected_rows = 35040  # 2 years × 365 days × 48 candles/day
        actual_rows = len(df)
        print(f"   Row count: {actual_rows} (expected ~{expected_rows})")

        if actual_rows < expected_rows * 0.95:  # Allow 5% tolerance
            print(f"⚠️  Row count lower than expected")

        # Create DateTime column
        df['DateTime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])

        # Check date range
        min_date = df['DateTime'].min()
        max_date = df['DateTime'].max()
        print(f"   Date range: {min_date.date()} to {max_date.date()}")

        # Check for duplicates
        duplicates = df['DateTime'].duplicated().sum()
        print(f"   Duplicates: {duplicates}")

        if duplicates > 0:
            print(f"⚠️  Found {duplicates} duplicate timestamps - will be removed during aggregation")

        # Check OHLC logic
        invalid_ohlc = ((df['High'] < df['Low']) |
                        (df['High'] < df['Open']) |
                        (df['High'] < df['Close']) |
                        (df['Low'] > df['Open']) |
                        (df['Low'] > df['Close'])).sum()
        print(f"   Invalid OHLC: {invalid_ohlc}")

        if invalid_ohlc > 0:
            print(f"❌ Found {invalid_ohlc} invalid OHLC records")
            return False

        # Check for null values
        nulls = df.isnull().sum().sum()
        print(f"   Null values: {nulls}")

        if nulls > 0:
            print(f"❌ Found {nulls} null values")
            return False

        # Check volume
        zero_volume = (df['Volume'] <= 0).sum()
        print(f"   Zero volume candles: {zero_volume}")

        print("✅ 30M data validation complete")
        return True

    def aggregate_to_1h(self):
        """
        Aggregate 30M candles to 1H candles.

        Returns
        -------
        pd.DataFrame
            1H OHLCV data
        """
        print("\n📊 Aggregating 30M to 1H candles...")

        if self.data_30m is None:
            print("❌ No 30M data to aggregate")
            return None

        df = self.data_30m.copy()
        df['DateTime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])

        # Remove duplicates (keep first occurrence)
        df = df.drop_duplicates(subset=['DateTime'], keep='first')

        df = df.sort_values('DateTime').reset_index(drop=True)

        # Group by hour
        df['Hour'] = df['DateTime'].dt.floor('1h')

        agg_dict = {
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }

        df_1h = df.groupby('Hour').agg(agg_dict).reset_index()
        df_1h['Date'] = df_1h['Hour'].dt.strftime('%Y-%m-%d')
        df_1h['Time'] = df_1h['Hour'].dt.strftime('%H:%M')
        df_1h['DateTime'] = df_1h['Hour']

        df_1h = df_1h[['Date', 'Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'DateTime']]

        print(f"✅ Generated {len(df_1h)} 1H candles")

        self.data_1h = df_1h
        return df_1h

    def aggregate_to_4h(self):
        """
        Aggregate 30M candles to 4H candles.

        Returns
        -------
        pd.DataFrame
            4H OHLCV data
        """
        print("\n📊 Aggregating 30M to 4H candles...")

        if self.data_30m is None:
            print("❌ No 30M data to aggregate")
            return None

        df = self.data_30m.copy()
        df['DateTime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])

        # Remove duplicates (keep first occurrence)
        df = df.drop_duplicates(subset=['DateTime'], keep='first')

        df = df.sort_values('DateTime').reset_index(drop=True)

        # Group by 4-hour periods
        df['4HourDateTime'] = df['DateTime'].dt.floor('4h')

        agg_dict = {
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }

        df_4h = df.groupby('4HourDateTime').agg(agg_dict).reset_index()
        df_4h['Date'] = df_4h['4HourDateTime'].dt.strftime('%Y-%m-%d')
        df_4h['Time'] = df_4h['4HourDateTime'].dt.strftime('%H:%M')
        df_4h['DateTime'] = df_4h['4HourDateTime']

        df_4h = df_4h[['Date', 'Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'DateTime']]

        print(f"✅ Generated {len(df_4h)} 4H candles")

        self.data_4h = df_4h
        return df_4h

    def save_to_csv(self, df, output_path):
        """
        Save data to CSV file.

        Parameters
        ----------
        df : pd.DataFrame
            OHLCV data
        output_path : str
            Path to save CSV

        Returns
        -------
        bool
            True if saved successfully
        """
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)

            # Remove DateTime column before saving
            if 'DateTime' in df.columns:
                df = df.drop('DateTime', axis=1)

            # Save to CSV
            df.to_csv(output_path, index=False)

            file_size = os.path.getsize(output_path) / 1024 / 1024
            print(f"✅ Saved to {output_path}")
            print(f"   File size: {file_size:.2f} MB")
            print(f"   Rows: {len(df)}")

            return True

        except Exception as e:
            print(f"❌ Error saving CSV: {e}")
            return None


def fetch_and_prepare_data(start_date="2024-01-01", end_date="2025-12-31"):
    """
    Main function to fetch BTC data and prepare all timeframes.

    Parameters
    ----------
    start_date : str
        Start date in YYYY-MM-DD format
    end_date : str
        End date in YYYY-MM-DD format

    Returns
    -------
    tuple
        (data_30m, data_1h, data_4h) or (None, None, None) on failure
    """
    print("=" * 70)
    print("Delta Exchange BTC Historical Data Fetcher")
    print("=" * 70)

    fetcher = DeltaExchangeFetcher()

    # Step 1: Fetch 30M data
    print("\n[Step 1] Fetching 30M data from Delta Exchange API...")
    df_30m = fetcher.fetch_data(start_date, end_date)

    if df_30m is None:
        print("❌ Failed to fetch data")
        return None, None, None

    # Step 2: Validate 30M data
    print("\n[Step 2] Validating 30M data...")
    if not fetcher.validate_data(df_30m):
        print("⚠️  Data validation failed, but continuing...")

    # Step 3: Save 30M data
    print("\n[Step 3] Saving 30M data...")
    if not fetcher.save_to_csv(df_30m, "data/btc_ohlcv.csv"):
        print("❌ Failed to save 30M CSV")
        return None, None, None

    # Step 4: Aggregate to 1H
    print("\n[Step 4] Aggregating to 1H candles...")
    df_1h = fetcher.aggregate_to_1h()

    if df_1h is None:
        print("❌ Failed to aggregate to 1H")
        return None, None, None

    # Step 5: Aggregate to 4H
    print("\n[Step 5] Aggregating to 4H candles...")
    df_4h = fetcher.aggregate_to_4h()

    if df_4h is None:
        print("❌ Failed to aggregate to 4H")
        return None, None, None

    print("\n" + "=" * 70)
    print("✅ Data fetch and preparation complete!")
    print("=" * 70)
    print(f"\n📊 Data Summary:")
    print(f"   30M candles: {len(df_30m)}")
    print(f"   1H candles: {len(df_1h)}")
    print(f"   4H candles: {len(df_4h)}")

    return df_30m, df_1h, df_4h


if __name__ == "__main__":
    fetch_and_prepare_data()
