import requests
import pandas as pd
import time
from datetime import datetime

# Config
SYMBOL = "ETHUSD"
RESOLUTION = "2h"
OUTPUT_PATH = "data/eth_2h_delta.csv"
BASE_URL = "https://api.india.delta.exchange"

# Date range: same as BTC (2023-12-29 to 2026-06-21)
START_DATE = "2023-12-29"
END_DATE   = "2026-06-21"

def fetch_candles(symbol, resolution, start_ts, end_ts):
    url = f"{BASE_URL}/v2/history/candles"
    params = {
        "symbol": symbol,
        "resolution": resolution,
        "start": start_ts,
        "end": end_ts
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get("success") and data.get("result"):
        return data["result"]
    return []

def download_all_candles():
    start_ts = int(datetime.strptime(START_DATE, "%Y-%m-%d").timestamp())
    end_ts   = int(datetime.strptime(END_DATE,   "%Y-%m-%d").timestamp())

    interval_seconds = 2 * 60 * 60  # 2 hours
    max_candles_per_request = 2000
    batch_seconds = interval_seconds * max_candles_per_request  # ~166 days per batch

    all_candles = []
    batch_start = start_ts

    print(f"Downloading {SYMBOL} {RESOLUTION} candles from {START_DATE} to {END_DATE}...")

    while batch_start < end_ts:
        batch_end = min(batch_start + batch_seconds, end_ts)

        print(f"  Fetching: {datetime.utcfromtimestamp(batch_start)} -> {datetime.utcfromtimestamp(batch_end)}")

        candles = fetch_candles(SYMBOL, RESOLUTION, batch_start, batch_end)

        if candles:
            all_candles.extend(candles)
            print(f"  Got {len(candles)} candles. Total so far: {len(all_candles)}")
        else:
            print(f"  No candles returned for this batch.")

        batch_start = batch_end
        time.sleep(0.5)  # avoid rate limiting

    return all_candles

def save_to_csv(candles):
    if not candles:
        print("No candles to save.")
        return

    df = pd.DataFrame(candles)

    # Rename columns to match BTC format
    df = df.rename(columns={"time": "timestamp"})

    # Add datetime column (same as BTC format)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="s").dt.strftime("%Y-%m-%d %H:%M:%S")

    # Sort by timestamp ascending
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

    # Reorder columns to match btc_2h_delta.csv format
    df = df[["timestamp", "open", "high", "low", "close", "volume", "datetime"]]

    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved {len(df)} candles to {OUTPUT_PATH}")
    print(f"Date range: {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")

if __name__ == "__main__":
    candles = download_all_candles()
    save_to_csv(candles)
