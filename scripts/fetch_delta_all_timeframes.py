# scripts/fetch_delta_all_timeframes.py
# Responsibility: Fetch all timeframes of BTC candles from Delta Exchange

import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import os


class DeltaDataFetcher:
    """Fetch historical candle data from Delta Exchange."""

    def __init__(self):
        self.base_url = "https://api.india.delta.exchange/v2/history/candles"
        self.symbol = 'BTCUSD'
        self.resolutions = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']

        self.resolution_seconds = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '30m': 1800,
            '1h': 3600,
            '4h': 14400,
            '1d': 86400
        }

        os.makedirs('data', exist_ok=True)

    def fetch_candles(self, resolution, start_time, end_time):
        """
        Fetch OHLCV candles from Delta Exchange.

        Parameters:
        - resolution: '1m', '5m', '15m', '30m', '1h', '4h', '1d'
        - start_time: Unix timestamp (seconds)
        - end_time: Unix timestamp (seconds)

        Returns:
        - List of candles
        """
        all_candles = []
        current_start = start_time

        # API returns max 2000 candles per request
        max_candles_per_request = 2000
        seconds_per_candle = self.resolution_seconds.get(resolution, 60)

        print(f"\n{'=' * 70}")
        print(f"Fetching {self.symbol} {resolution.upper()} candles")
        print(f"Date range: {datetime.fromtimestamp(start_time)} to {datetime.fromtimestamp(end_time)}")
        print(f"{'=' * 70}")

        batch_count = 0

        while current_start < end_time:
            batch_count += 1

            # Calculate end time for this batch
            batch_end = min(current_start + (max_candles_per_request * seconds_per_candle), end_time)

            params = {
                'symbol': self.symbol,
                'resolution': resolution,
                'start': current_start,
                'end': batch_end
            }

            print(
                f"Batch {batch_count}: {datetime.fromtimestamp(current_start).strftime('%Y-%m-%d %H:%M')} to {datetime.fromtimestamp(batch_end).strftime('%Y-%m-%d %H:%M')}",
                end=" ... ")

            try:
                response = requests.get(self.base_url, params=params, timeout=10)
                response.raise_for_status()

                data = response.json()

                if data.get('success') and data.get('result'):
                    candles = data['result']
                    all_candles.extend(candles)
                    print(f"✅ {len(candles)} candles")
                else:
                    print(f"⚠️  No data")
                    break

            except requests.exceptions.RequestException as e:
                print(f"❌ Error: {e}")
                break

            # Move to next batch
            current_start = batch_end

            # Rate limiting (0.5 second delay between requests)
            time.sleep(0.5)

        print(f"✅ Total {resolution.upper()} candles fetched: {len(all_candles)}")
        return all_candles

    def candles_to_dataframe(self, candles):
        """
        Convert candle list to DataFrame.

        Candle format from Delta Exchange:
        [time, open, high, low, close, volume]
        time is in seconds
        """
        if not candles:
            return None

        df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume'])

        # CORRECTED: 'time' is already in seconds, just convert to int
        df['timestamp'] = df['time'].astype(int)

        # Reorder columns
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

        # Remove duplicates
        df = df.drop_duplicates(subset=['timestamp'])

        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)

        return df

    def save_to_csv(self, df, filename):
        """Save DataFrame to CSV."""
        if df is None or len(df) == 0:
            print(f"⚠️  No data to save for {filename}")
            return False

        df.to_csv(filename, index=False)
        print(f"✅ Saved {len(df)} candles to {filename}")
        print(
            f"   Date range: {datetime.fromtimestamp(df['timestamp'].min()).strftime('%Y-%m-%d %H:%M')} to {datetime.fromtimestamp(df['timestamp'].max()).strftime('%Y-%m-%d %H:%M')}")
        return True

    def fetch_all_timeframes(self, days_back=365):
        """
        Fetch all timeframes for the specified date range.

        Parameters:
        - days_back: Number of days to fetch (default: 365 = 1 year)
        """
        # Calculate date range
        end_time = int(datetime.now().timestamp())
        start_time = int((datetime.now() - timedelta(days=days_back)).timestamp())

        print(f"\n{'=' * 70}")
        print(f"DELTA EXCHANGE DATA FETCHER")
        print(f"{'=' * 70}")
        print(f"Symbol: {self.symbol}")
        print(f"Period: {days_back} days")
        print(f"Start: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M')}")
        print(f"End: {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M')}")
        print(f"{'=' * 70}")

        results = {}

        for resolution in self.resolutions:
            # Fetch candles
            candles = self.fetch_candles(resolution, start_time, end_time)

            if candles:
                # Convert to DataFrame
                df = self.candles_to_dataframe(candles)

                if df is not None and len(df) > 0:
                    # Generate filename
                    filename = f'data/btc_{resolution}_delta.csv'

                    # Save to CSV
                    if self.save_to_csv(df, filename):
                        results[resolution] = {
                            'filename': filename,
                            'candles': len(df),
                            'start': datetime.fromtimestamp(df['timestamp'].min()),
                            'end': datetime.fromtimestamp(df['timestamp'].max())
                        }

            # Delay between different resolutions
            time.sleep(1)

        # Print summary
        print(f"\n{'=' * 70}")
        print(f"FETCH SUMMARY")
        print(f"{'=' * 70}")

        for resolution in self.resolutions:
            if resolution in results:
                info = results[resolution]
                print(f"✅ {resolution.upper():5} - {info['candles']:6} candles - {info['filename']}")
            else:
                print(f"❌ {resolution.upper():5} - Failed to fetch")

        print(f"{'=' * 70}\n")

        return results


def main():
    """Main execution."""
    fetcher = DeltaDataFetcher()

    # Fetch all timeframes for last 1 year
    results = fetcher.fetch_all_timeframes(days_back=365)

    if results:
        print(f"\n✅ Successfully fetched {len(results)} timeframes")
        print("\nYou can now run backtests with any timeframe combination:")
        print("  - 1H + 15M")
        print("  - 4H + 1H")
        print("  - 1H + 5M")
        print("  - 15M + 5M")
        print("  - etc.")
    else:
        print("\n❌ Failed to fetch data")


if __name__ == "__main__":
    main()
