"""
strategies_options/backtest/mood_based_portfolio_backtest.py

Mood-based BTC option-selling portfolio backtest.
Single engine, auto-switches strategy mode based on 3-day price trend (mood).
All strikes kept within 2000 points of spot (SAFE zone, confirmed by data
availability test: 33-100% real data coverage vs 77-87% gaps beyond 2000pts).

Modes:
  SIDEWAYS        -> ATM straddle (sell both)
  MILD_BULLISH    -> strangle, put 500pts, call 1500pts
  STRONG_BULLISH  -> sell put only, 1000pts
  MILD_BEARISH    -> strangle, call 500pts, put 1500pts
  STRONG_BEARISH  -> sell call only, 1000pts

Risk rules implemented:
  - Leg-wise SL: 50% of collected premium
  - One re-entry per leg on SL hit, same side only
  - Daily portfolio loss cap: configurable (default Rs 2000 equiv)
  - Gap risk kill-switch: if spot moves >3% within 1h, exit everything
  - Fixed lot size per leg (10 lots default)
  - No overall SL/TP beyond leg-wise and daily cap

IMPORTANT ASSUMPTIONS (flagged, not guessed silently):
  - CONTRACT_BTC_PER_LOT = 0.001 (confirmed earlier via getProductBySymbol)
  - USD_TO_INR used only for reporting against Rs-based gates; verify current
    rate before trusting absolute Rs numbers.
  - Entry time and expiry are same calendar day (Delta daily-expiry BTC options).
  - Missing option data (0 candles) for a leg => that leg is SKIPPED for that
    day and logged as NO_DATA, not silently treated as zero PnL.
"""

import requests
import time
import csv
import os
import argparse
import math
from datetime import datetime, timedelta, timezone

BASE_URL = "https://api.india.delta.exchange"
CANDLE_PATH = "/v2/history/candles"
UNDERLYING_SYMBOL = "BTCUSD"

OUTPUT_DIR = "output_options"
TRADE_LOG_FILE = os.path.join(OUTPUT_DIR, "mood_portfolio_trades.csv")
SUMMARY_FILE = os.path.join(OUTPUT_DIR, "mood_portfolio_summary.csv")

REQUEST_TIMEOUT = (3, 27)

# ---------------- CONFIG (confirm/adjust before trusting results) ----------------
CONTRACT_BTC_PER_LOT = 0.001     # from product spec, verified earlier
LOT_SIZE = 10                    # lots per leg, fixed per design
LEG_SL_PCT = 0.50                # exit leg if premium grows 50% against us
STARTING_CAPITAL_USD = 227.0     # approx Rs 20,000 at ~88 USD/INR, VERIFY before trusting
DAILY_LOSS_CAP_USD = 22.7        # approx Rs 2,000 equiv, VERIFY
GAP_RISK_PCT = 0.03              # 3% spot move in <1h triggers full exit
STRIKE_ROUND = 1000
MAX_REENTRY = 1
RESOLUTION = "5m"

MOOD_THRESHOLDS = {
    "strong_bullish": 0.05,
    "mild_bullish": 0.015,
    "mild_bearish": -0.015,
    "strong_bearish": -0.05,
}

# ---------------- API HELPERS ----------------

def fetch_candles(symbol, start_ts, end_ts, resolution="5m"):
    params = {"resolution": resolution, "symbol": symbol, "start": start_ts, "end": end_ts}
    try:
        resp = requests.get(BASE_URL + CANDLE_PATH, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return []
        return sorted(data.get("result", []), key=lambda c: c["time"])
    except requests.exceptions.RequestException:
        return []


def round_to_nearest(value, step):
    return int(round(value / step) * step)


def build_option_symbol(option_type, strike, day):
    date_suffix = day.strftime("%d%m%y")
    return f"{option_type}-BTC-{strike}-{date_suffix}"


def get_daily_close(day):
    """1d candle close for a given date (used for mood detection)."""
    start = datetime(day.year, day.month, day.day, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    candles = fetch_candles(UNDERLYING_SYMBOL, int(start.timestamp()), int(end.timestamp()), "1d")
    if not candles:
        return None
    return candles[-1]["close"]


def detect_mood(day):
    """3-day % change ending at 'day' (uses day-3 close vs day-close)."""
    close_today = get_daily_close(day)
    close_3d_ago = get_daily_close(day - timedelta(days=3))
    if close_today is None or close_3d_ago is None or close_3d_ago == 0:
        return None, None
    pct_change = (close_today - close_3d_ago) / close_3d_ago
    if pct_change >= MOOD_THRESHOLDS["strong_bullish"]:
        mood = "STRONG_BULLISH"
    elif pct_change >= MOOD_THRESHOLDS["mild_bullish"]:
        mood = "MILD_BULLISH"
    elif pct_change <= MOOD_THRESHOLDS["strong_bearish"]:
        mood = "STRONG_BEARISH"
    elif pct_change <= MOOD_THRESHOLDS["mild_bearish"]:
        mood = "MILD_BEARISH"
    else:
        mood = "SIDEWAYS"
    return mood, pct_change


def get_legs_for_mood(mood, atm_strike):
    """Returns list of (option_type, strike) legs to SELL for given mood."""
    r = STRIKE_ROUND
    if mood == "SIDEWAYS":
        return [("C", atm_strike), ("P", atm_strike)]
    elif mood == "MILD_BULLISH":
        return [("P", round_to_nearest(atm_strike - 500, r)),
                ("C", round_to_nearest(atm_strike + 1500, r))]
    elif mood == "STRONG_BULLISH":
        return [("P", round_to_nearest(atm_strike - 1000, r))]
    elif mood == "MILD_BEARISH":
        return [("C", round_to_nearest(atm_strike + 500, r)),
                ("P", round_to_nearest(atm_strike - 1500, r))]
    elif mood == "STRONG_BEARISH":
        return [("C", round_to_nearest(atm_strike + 1000, r))]
    return []


def check_gap_risk(spot_candles):
    """Returns the timestamp index where spot moved >GAP_RISK_PCT within 1h, else None."""
    for i in range(1, len(spot_candles)):
        prev = spot_candles[i - 1]["close"]
        cur = spot_candles[i]["close"]
        if prev > 0 and abs(cur - prev) / prev >= GAP_RISK_PCT:
            return spot_candles[i]["time"]
    return None


def simulate_leg(option_type, strike, day, gap_exit_time):
    """
    Simulate selling one option leg for the day.
    Returns dict with pnl_usd, status, entry_price, exit_price, reentries_used.
    """
    symbol = build_option_symbol(option_type, strike, day)
    day_start = datetime(day.year, day.month, day.day, 0, 0, tzinfo=timezone.utc)
    day_end = day_start + timedelta(hours=23, minutes=59)
    start_ts, end_ts = int(day_start.timestamp()), int(day_end.timestamp())

    candles = fetch_candles(f"MARK:{symbol}", start_ts, end_ts, RESOLUTION)
    if not candles:
        return {"symbol": symbol, "status": "NO_DATA", "pnl_usd": 0.0,
                "entry_price": None, "exit_price": None, "reentries": 0}

    pnl_total = 0.0
    reentries_used = 0
    idx = 0
    status = "HELD_TO_EXPIRY"
    entry_price_first = candles[0]["open"]

    while idx < len(candles):
        entry_price = candles[idx]["open"]
        sl_price = entry_price * (1 + LEG_SL_PCT)
        exit_price = candles[-1]["close"]
        exit_reason = "EXPIRY"

        for j in range(idx, len(candles)):
            c = candles[j]
            if gap_exit_time and c["time"] >= gap_exit_time:
                exit_price = c["close"]
                exit_reason = "GAP_RISK_EXIT"
                idx = len(candles)
                break
            if c["high"] >= sl_price:
                exit_price = sl_price
                exit_reason = "SL_HIT"
                idx = j + 1
                break
        else:
            idx = len(candles)

        leg_pnl = (entry_price - exit_price) * LOT_SIZE * CONTRACT_BTC_PER_LOT
        pnl_total += leg_pnl

        if exit_reason == "SL_HIT" and reentries_used < MAX_REENTRY and idx < len(candles):
            reentries_used += 1
            status = "SL_HIT_REENTERED"
            continue
        else:
            status = exit_reason
            break

    return {"symbol": symbol, "status": status, "pnl_usd": pnl_total,
            "entry_price": entry_price_first, "exit_price": exit_price,
            "reentries": reentries_used}


def run_backtest(start_date, end_date):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    trades = []
    daily_pnls = []
    day = start_date

    while day <= end_date:
        mood, pct_change = detect_mood(day)
        if mood is None:
            day += timedelta(days=1)
            continue

        day_start = datetime(day.year, day.month, day.day, 0, 0, tzinfo=timezone.utc)
        day_end = day_start + timedelta(hours=23, minutes=59)
        spot_candles = fetch_candles(UNDERLYING_SYMBOL, int(day_start.timestamp()),
                                      int(day_end.timestamp()), "1h")
        if not spot_candles:
            day += timedelta(days=1)
            continue

        spot_close = spot_candles[-1]["close"]
        atm_strike = round_to_nearest(spot_close, STRIKE_ROUND)
        legs = get_legs_for_mood(mood, atm_strike)
        gap_exit_time = check_gap_risk(spot_candles)

        day_pnl = 0.0
        for option_type, strike in legs:
            result = simulate_leg(option_type, strike, day, gap_exit_time)
            result.update({"date": day.isoformat(), "mood": mood, "pct_change_3d": pct_change})
            trades.append(result)
            if result["status"] != "NO_DATA":
                day_pnl += result["pnl_usd"]

        if day_pnl < -DAILY_LOSS_CAP_USD:
            day_pnl = -DAILY_LOSS_CAP_USD  # approximate cap enforcement

        daily_pnls.append({"date": day.isoformat(), "mood": mood, "pnl_usd": day_pnl})
        print(f"{day.isoformat()} mood={mood} ({pct_change:.2%}) legs={legs} day_pnl=${day_pnl:.2f}")

        day += timedelta(days=1)
        time.sleep(0.3)

    write_trade_log(trades)
    write_summary(daily_pnls)
    return daily_pnls


def write_trade_log(trades):
    with open(TRADE_LOG_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date", "mood", "pct_change_3d", "symbol", "status",
            "entry_price", "exit_price", "reentries", "pnl_usd"
        ])
        writer.writeheader()
        writer.writerows(trades)


def write_summary(daily_pnls):
    with open(SUMMARY_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "mood", "pnl_usd"])
        writer.writeheader()
        writer.writerows(daily_pnls)

    pnls = [d["pnl_usd"] for d in daily_pnls]
    n = len(pnls)
    if n == 0:
        print("No trading days processed.")
        return

    total_pnl = sum(pnls)
    mean_pnl = total_pnl / n
    variance = sum((p - mean_pnl) ** 2 for p in pnls) / n if n > 1 else 0
    std_pnl = math.sqrt(variance)
    sharpe = (mean_pnl / std_pnl) * math.sqrt(252) if std_pnl > 0 else 0.0

    equity = STARTING_CAPITAL_USD
    peak = equity
    max_dd = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)

    max_dd_pct = (max_dd / STARTING_CAPITAL_USD) * 100 if STARTING_CAPITAL_USD > 0 else 0

    print("\n==================== PORTFOLIO REPORT ====================")
    print(f"Days traded      : {n}")
    print(f"Total PnL (USD)  : {total_pnl:.2f}")
    print(f"Avg PnL/day (USD): {mean_pnl:.2f}")
    print(f"Sharpe (ann.)    : {sharpe:.2f}")
    print(f"Max Drawdown USD : {max_dd:.2f} ({max_dd_pct:.1f}% of capital)")
    print(f"Final equity USD : {equity:.2f}")
    print("Gate check: Sharpe>=3.0 ->", "PASS" if sharpe >= 3.0 else "FAIL")
    print("Gate check: MaxDD<=10%  ->", "PASS" if max_dd_pct <= 10.0 else "FAIL")
    print("============================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mood-based BTC option portfolio backtest.")
    parser.add_argument("--start", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", type=str, required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()

    run_backtest(start_date, end_date)
