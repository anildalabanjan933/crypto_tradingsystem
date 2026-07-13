# data/download_market_data.py
# Responsibility: Incremental market data downloader for BTC and ETH 1M candles

import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone

BASE_URL = "https://api.india.delta.exchange"

SYMBOLS = {
    "BTC": {"symbol": "BTCUSD", "file": "data/btc_1m_delta.csv"},
    "ETH": {"symbol": "ETHUSD", "file": "data/eth_1m_delta.csv"},
}

FULL_FETCH_START = "2024-01-01"
MAX_CANDLES = 2000
RESOLUTION = "1m"
CANDLE_SECONDS = 60


def fetch_candles(symbol, start_ts, end_ts):
    url = BASE_URL + "/v2/history/candles"
    params = {"symbol": symbol, "resolution": RESOLUTION, "start": int(start_ts), "end": int(end_ts)}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise ValueError("API error: " + str(data))
    return data.get("result", [])


def candles_to_df(candles):
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles)
    df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df["Date"] = df["datetime"].dt.strftime("%Y-%m-%d")
    df["Time"] = df["datetime"].dt.strftime("%H:%M:%S")
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
    df = df[["Date", "Time", "Open", "High", "Low", "Close", "Volume"]]
    return df


def get_last_timestamp(filepath):
    if not os.path.exists(filepath):
        return None
    try:
        df = pd.read_csv(filepath)
        if df.empty:
            return None
        last_row = df.iloc[-1]
        dt_str = str(last_row["Date"]) + " " + str(last_row["Time"])
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]:
            try:
                dt = datetime.strptime(dt_str.strip(), fmt)
                break
            except ValueError:
                continue
        else:
            return None
        dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception as e:
        print("  Warning: could not read last timestamp from " + filepath + ": " + str(e))
        return None


def download_or_update(asset_key):
    cfg = SYMBOLS[asset_key]
    symbol = cfg["symbol"]
    filepath = cfg["file"]
    now_ts = int(time.time()) - CANDLE_SECONDS
    last_ts = get_last_timestamp(filepath)
    if last_ts is None:
        start_ts = int(datetime.strptime(FULL_FETCH_START, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        mode = "full"
        print("  No existing file found. Full fetch from " + FULL_FETCH_START + ".")
    else:
        start_ts = last_ts + CANDLE_SECONDS
        mode = "incremental"
        last_dt = datetime.utcfromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M:%S")
        print("  Existing file found. Incremental update from " + last_dt + " UTC.")
    if start_ts >= now_ts:
        print("  " + symbol + " is already up to date.")
        return
    all_candles = []
    batch_start = start_ts
    batch_num = 0
    while batch_start < now_ts:
        batch_end = min(batch_start + MAX_CANDLES * CANDLE_SECONDS, now_ts)
        batch_num += 1
        s = datetime.utcfromtimestamp(batch_start).strftime("%Y-%m-%d %H:%M")
        e = datetime.utcfromtimestamp(batch_end).strftime("%Y-%m-%d %H:%M")
        print("  Fetching batch " + str(batch_num) + ": " + s + " -> " + e, end="\r")
        try:
            candles = fetch_candles(symbol, batch_start, batch_end)
        except Exception as ex:
            print("\n  Error fetching batch " + str(batch_num) + ": " + str(ex))
            break
        if not candles:
            batch_start = batch_end + CANDLE_SECONDS
            continue
        all_candles.extend(candles)
        batch_start = max(c["time"] for c in candles) + CANDLE_SECONDS
        time.sleep(0.2)
    print()
    if not all_candles:
        print("  No new candles fetched for " + symbol + ".")
        return
    new_df = candles_to_df(all_candles)
    new_df = new_df.drop_duplicates(subset=["Date", "Time"]).sort_values(["Date", "Time"]).reset_index(drop=True)
    if mode == "incremental" and os.path.exists(filepath):
        existing_df = pd.read_csv(filepath)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["Date", "Time"]).sort_values(["Date", "Time"]).reset_index(drop=True)
        combined.to_csv(filepath, index=False)
        print("  Updated: " + str(len(new_df)) + " new rows added. Total rows: " + str(len(combined)) + ".")
    else:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        new_df.to_csv(filepath, index=False)
        print("  Created: " + str(len(new_df)) + " rows saved to " + filepath + ".")


def run_download_menu():
    while True:
        print("\n" + "=" * 70)
        print("DOWNLOAD / UPDATE MARKET DATA")
        print("=" * 70)
        print("1. Update BTC 1M")
        print("2. Update ETH 1M")
        print("3. Update Both")
        print("4. Back")
        print("=" * 70)
        choice = input("Enter choice (1-4): ").strip()
        if choice == "1":
            print("\nUpdating BTC 1M data...")
            download_or_update("BTC")
        elif choice == "2":
            print("\nUpdating ETH 1M data...")
            download_or_update("ETH")
        elif choice == "3":
            print("\nUpdating BTC 1M data...")
            download_or_update("BTC")
            print("\nUpdating ETH 1M data...")
            download_or_update("ETH")
        elif choice == "4":
            break
        else:
            print("Invalid choice. Please try again.")
