"""
scripts_options/check_option_data_availability.py

Quick 30-day data availability check for BTC daily-expiry options on Delta Exchange.
Confirms whether real option candle history (via MARK:symbol) is complete enough
before building the full 7-strategy portfolio backtest engine.

Usage:
    python3 check_option_data_availability.py --days 30 --strike-round 1000

Output:
    output_options/data_availability_report.csv
"""

import requests
import time
import csv
import os
import argparse
from datetime import datetime, timedelta, timezone

BASE_URL = "https://api.india.delta.exchange"
CANDLE_PATH = "/v2/history/candles"
UNDERLYING_SYMBOL = "BTCUSD"
OUTPUT_DIR = "output_options"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "data_availability_report.csv")

REQUEST_TIMEOUT = (3, 27)


def get_underlying_close(day_start_ts, day_end_ts):
    params = {
        "resolution": "1h",
        "symbol": UNDERLYING_SYMBOL,
        "start": day_start_ts,
        "end": day_end_ts,
    }
    try:
        resp = requests.get(BASE_URL + CANDLE_PATH, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success") or not data.get("result"):
            return None
        candles = data["result"]
        candles_sorted = sorted(candles, key=lambda c: c["time"])
        return candles_sorted[-1]["close"]
    except requests.exceptions.RequestException as e:
        print(f"[WARN] Failed to fetch underlying close: {e}")
        return None


def build_option_symbol(option_type, strike, expiry_date):
    date_suffix = expiry_date.strftime("%d%m%y")
    return f"{option_type}-BTC-{strike}-{date_suffix}"


def fetch_candle_count(symbol, day_start_ts, day_end_ts, resolution="5m"):
    params = {
        "resolution": resolution,
        "symbol": f"MARK:{symbol}",
        "start": day_start_ts,
        "end": day_end_ts,
    }
    try:
        resp = requests.get(BASE_URL + CANDLE_PATH, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return 0, data.get("error", "unknown_error")
        return len(data.get("result", [])), None
    except requests.exceptions.RequestException as e:
        return 0, str(e)


def round_to_nearest(value, step):
    return int(round(value / step) * step)


def main():
    parser = argparse.ArgumentParser(description="Check BTC option data availability for last N days.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--strike-round", type=int, default=1000)
    parser.add_argument("--resolution", type=str, default="5m")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    today = datetime.now(timezone.utc).date()
    rows = []

    print(f"Checking {args.days} days of BTC daily-expiry option data availability...")

    for i in range(1, args.days + 1):
        day = today - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=timezone.utc)
        day_end = day_start + timedelta(hours=23, minutes=59)

        day_start_ts = int(day_start.timestamp())
        day_end_ts = int(day_end.timestamp())

        spot_close = get_underlying_close(day_start_ts, day_end_ts)
        if spot_close is None:
            rows.append({
                "date": day.isoformat(),
                "spot_close": None,
                "call_symbol": None,
                "put_symbol": None,
                "call_candles": 0,
                "put_candles": 0,
                "status": "NO_SPOT_DATA"
            })
            print(f"{day.isoformat()}: NO SPOT DATA")
            continue

        atm_strike = round_to_nearest(spot_close, args.strike_round)
        call_symbol = build_option_symbol("C", atm_strike, day)
        put_symbol = build_option_symbol("P", atm_strike, day)

        call_count, call_err = fetch_candle_count(call_symbol, day_start_ts, day_end_ts, args.resolution)
        time.sleep(0.2)
        put_count, put_err = fetch_candle_count(put_symbol, day_start_ts, day_end_ts, args.resolution)
        time.sleep(0.2)

        status = "OK" if (call_count > 0 and put_count > 0) else "GAP_DETECTED"

        rows.append({
            "date": day.isoformat(),
            "spot_close": spot_close,
            "call_symbol": call_symbol,
            "put_symbol": put_symbol,
            "call_candles": call_count,
            "put_candles": put_count,
            "status": status
        })

        print(f"{day.isoformat()}: strike={atm_strike} call_candles={call_count} put_candles={put_count} status={status}")

    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date", "spot_close", "call_symbol", "put_symbol",
            "call_candles", "put_candles", "status"
        ])
        writer.writeheader()
        writer.writerows(rows)

    gap_days = sum(1 for r in rows if r["status"] != "OK")
    print(f"\nDone. {gap_days}/{len(rows)} days had gaps or missing data.")
    print(f"Report saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
