# download_btc_2h.py
# Purpose: Download 2h OHLCV data for BTCUSD from Delta Exchange API
# Saves to data/btc_2h_delta.csv
# Max 2000 candles per request - paginates automatically

import requests
import pandas as pd
import time
import os
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════
BASE_URL    = "https://api.india.delta.exchange"
SYMBOL      = "BTCUSD"
RESOLUTION  = "2h"
OUTPUT_PATH = "data/btc_2h_delta.csv"

# How many years back to fetch
YEARS_BACK  = 3   # 3 years = ~13140 candles at 2h = ~7 requests

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def ts_to_str(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')

def fetch_candles(symbol, resolution, start_ts, end_ts):
    """Fetch up to 2000 candles from Delta Exchange API."""
    url    = f"{BASE_URL}/v2/history/candles"
    params = {
        "symbol"    : symbol,
        "resolution": resolution,
        "start"     : int(start_ts),
        "end"       : int(end_ts),
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") and data.get("result"):
            return data["result"]
        else:
            print(f"  API error: {data}")
            return []
    except Exception as e:
        print(f"  Request failed: {e}")
        return []

# ═══════════════════════════════════════════════════════════════
# MAIN DOWNLOADER
# ═══════════════════════════════════════════════════════════════
def download_historical_data():
    print("=" * 60)
    print(f"DOWNLOADING {SYMBOL} {RESOLUTION} DATA")
    print("=" * 60)

    # Time range
    end_ts   = int(datetime.now(timezone.utc).timestamp())
    start_ts = end_ts - (YEARS_BACK * 365 * 24 * 3600)

    print(f"Range: {ts_to_str(start_ts)} to {ts_to_str(end_ts)}")
    print(f"Estimated candles: ~{YEARS_BACK * 365 * 12} at 2h resolution")

    # 2h candle interval in seconds
    candle_interval = 2 * 3600       # 7200 seconds
    max_per_request = 2000
    window_size     = candle_interval * max_per_request   # 2000 candles per request

    all_candles = []
    chunk_start = start_ts
    request_num = 0

    while chunk_start < end_ts:
        chunk_end = min(chunk_start + window_size, end_ts)
        request_num += 1

        print(f"\n[Request {request_num}] {ts_to_str(chunk_start)} to {ts_to_str(chunk_end)}")

        candles = fetch_candles(SYMBOL, RESOLUTION, chunk_start, chunk_end)

        if candles:
            all_candles.extend(candles)
            print(f"  Fetched {len(candles)} candles | Total so far: {len(all_candles)}")
        else:
            print(f"  No data returned for this window")

        chunk_start = chunk_end + candle_interval
        time.sleep(0.3)   # rate limit safety

    if not all_candles:
        print("\nNo data downloaded. Check symbol and API connectivity.")
        return

    # ── Build DataFrame ───────────────────────────────────────
    df = pd.DataFrame(all_candles)

    # Rename columns to match existing system format
    df = df.rename(columns={
        'time'  : 'timestamp',
        'open'  : 'open',
        'high'  : 'high',
        'low'   : 'low',
        'close' : 'close',
        'volume': 'volume'
    })

    # Keep only needed columns
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

    # Remove duplicates and sort
    df = df.drop_duplicates(subset='timestamp')
    df = df.sort_values('timestamp').reset_index(drop=True)

    # Add readable datetime column for inspection
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)

    # ── Save ──────────────────────────────────────────────────
    os.makedirs("data", exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print("\n" + "=" * 60)
    print(f"DOWNLOAD COMPLETE")
    print(f"Total candles : {len(df)}")
    print(f"Date range    : {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")
    print(f"Saved to      : {OUTPUT_PATH}")
    print("=" * 60)

    # Quick sanity check
    print(f"\nFirst 3 rows:")
    print(df[['datetime','open','high','low','close','volume']].head(3).to_string())
    print(f"\nLast 3 rows:")
    print(df[['datetime','open','high','low','close','volume']].tail(3).to_string())

if __name__ == "__main__":
    download_historical_data()
