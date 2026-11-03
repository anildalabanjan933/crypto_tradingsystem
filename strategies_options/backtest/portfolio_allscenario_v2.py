
"""
strategies_options/backtest/portfolio_allscenario_v2.py

Multi-scenario BTC option-selling portfolio backtest.
3 independent sub-strategies, chosen daily by REAL-TIME trigger check
(using only data known at or before entry time - no lookahead).
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
UNDERLYING_SYMBOL = ".DEXBTUSD"

OUTPUT_DIR = "output_options"
TRADE_LOG_FILE = os.path.join(OUTPUT_DIR, "portfolio_v2_trades.csv")
SUMMARY_FILE = os.path.join(OUTPUT_DIR, "portfolio_v2_summary.csv")

REQUEST_TIMEOUT = (3, 27)
TEST_WINDOW_START = datetime(2025, 7, 1).date()

CONTRACT_BTC_PER_LOT = 0.001
LOT_SIZE_FULL = 100
LOT_SIZE_HALF = 50
STARTING_CAPITAL_USD = 227.0
DAILY_LOSS_CAP_USD = 11.36
ACCOUNT_DD_STOP_PCT = 10.0
STRIKE_ROUND = 1000
RESOLUTION = "5m"

LEG_SL_PCT_NORMAL = 0.30
LEG_SL_PCT_SPIKE = 0.20
TIME_EXIT_HOURS_NORMAL = 6
TIME_EXIT_HOURS_SPIKE = 3
ENTRY_HOUR_UTC = 10

TAKER_COMMISSION_RATE = 0.00015
PREMIUM_COMMISSION_RATE = 0.05
GST_MULTIPLIER = 1.18
SLIPPAGE_PCT = 0.05

TREND_THRESHOLD_PCT = 0.015
VOL_SPIKE_MULTIPLIER = 1.5


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


def get_realtime_window(day, entry_hour, lookback_hours):
    """
    Returns candles STRICTLY BEFORE entry_time (zero lookahead).
    """
    entry_time = datetime(day.year, day.month, day.day, entry_hour, 0, tzinfo=timezone.utc)
    window_start = entry_time - timedelta(hours=lookback_hours)
    candles = fetch_candles(UNDERLYING_SYMBOL, int(window_start.timestamp()),
                             int(entry_time.timestamp()), "5m")
    entry_ts = int(entry_time.timestamp())
    candles = [c for c in candles if c["time"] < entry_ts]
    for c in candles:
        assert c["time"] < entry_ts, "LOOKAHEAD BUG: candle at/after entry_time included!"
    return candles, entry_time


def realized_vol_pct(candles):
    if len(candles) < 2:
        return 0.0
    closes = [c["close"] for c in candles]
    rets = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes)) if closes[i-1] > 0]
    if not rets:
        return 0.0
    mean_r = sum(rets) / len(rets)
    var = sum((r - mean_r) ** 2 for r in rets) / len(rets)
    return math.sqrt(var)


def detect_submode(day):
    candles_4h, entry_time = get_realtime_window(day, ENTRY_HOUR_UTC, 4)
    if len(candles_4h) < 10:
        return None, None, None

    spot_entry = candles_4h[-1]["close"]
    price_4h_ago = candles_4h[0]["close"]
    move_pct = (spot_entry - price_4h_ago) / price_4h_ago if price_4h_ago > 0 else 0.0

    vol_4h = realized_vol_pct(candles_4h)

    candles_1h, _ = get_realtime_window(day, ENTRY_HOUR_UTC, 1)
    vol_1h = realized_vol_pct(candles_1h) if len(candles_1h) >= 5 else 0.0

    candles_baseline, _ = get_realtime_window(day, ENTRY_HOUR_UTC, 240)
    vol_baseline = realized_vol_pct(candles_baseline) if len(candles_baseline) >= 50 else 0.0
    vol_ratio = (vol_4h / vol_baseline) if vol_baseline > 0 else 1.0

    if vol_4h > 0 and vol_1h > VOL_SPIKE_MULTIPLIER * vol_4h:
        return "SPIKE", spot_entry, entry_time
    elif abs(move_pct) > TREND_THRESHOLD_PCT:
        direction = "UP" if move_pct > 0 else "DOWN"
        return f"TREND_{direction}", spot_entry, entry_time
    elif vol_ratio < 0.6:
        return None, None, None
    else:
        return "CALM", spot_entry, entry_time


def get_legs_for_submode(submode, atm_strike):
    r = STRIKE_ROUND
    if submode == "CALM":
        return [("C", atm_strike), ("P", atm_strike)], LOT_SIZE_FULL, LEG_SL_PCT_NORMAL, TIME_EXIT_HOURS_NORMAL
    elif submode == "TREND_UP":
        return [("P", round_to_nearest(atm_strike - 500, r)),
                ("C", round_to_nearest(atm_strike + 1500, r))], LOT_SIZE_FULL, LEG_SL_PCT_NORMAL, TIME_EXIT_HOURS_NORMAL
    elif submode == "TREND_DOWN":
        return [("C", round_to_nearest(atm_strike + 500, r)),
                ("P", round_to_nearest(atm_strike - 1500, r))], LOT_SIZE_FULL, LEG_SL_PCT_NORMAL, TIME_EXIT_HOURS_NORMAL
    elif submode == "SPIKE":
        return [("C", atm_strike), ("P", atm_strike)], LOT_SIZE_HALF, LEG_SL_PCT_SPIKE, TIME_EXIT_HOURS_SPIKE
    return [], 0, 0, 0


def compute_fee(option_price, spot_price, lots):
    notional_based = TAKER_COMMISSION_RATE * spot_price
    premium_based = PREMIUM_COMMISSION_RATE * option_price
    fee_per_unit = min(notional_based, premium_based)
    fee = fee_per_unit * CONTRACT_BTC_PER_LOT * lots
    return fee * GST_MULTIPLIER


def apply_slippage(price, is_entry_sell):
    if is_entry_sell:
        return price * (1 - SLIPPAGE_PCT)
    else:
        return price * (1 + SLIPPAGE_PCT)


def simulate_leg(option_type, strike, day, entry_time, lot_size, sl_pct, exit_hours, spot_price_for_fees):
    symbol = build_option_symbol(option_type, strike, day)
    exit_deadline = entry_time + timedelta(hours=exit_hours)
    start_ts, end_ts = int(entry_time.timestamp()), int(exit_deadline.timestamp())

    candles = fetch_candles(f"MARK:{symbol}", start_ts, end_ts, RESOLUTION)
    if not candles:
        return {"symbol": symbol, "status": "NO_DATA", "pnl_usd": 0.0,
                "fees_usd": 0.0, "entry_price": None, "exit_price": None}

    raw_entry_price = candles[0]["open"]
    entry_price_eff = apply_slippage(raw_entry_price, is_entry_sell=True)
    fees_total = compute_fee(raw_entry_price, spot_price_for_fees, lot_size)

    sl_price = raw_entry_price * (1 + sl_pct)
    raw_exit_price = candles[-1]["close"]
    exit_reason = "TIME_EXIT"

    for c in candles:
        if c["high"] >= sl_price:
            raw_exit_price = sl_price
            exit_reason = "SL_HIT"
            break

    exit_price_eff = apply_slippage(raw_exit_price, is_entry_sell=False)
    fees_total += compute_fee(raw_exit_price, spot_price_for_fees, lot_size)

    leg_pnl = (entry_price_eff - exit_price_eff) * lot_size * CONTRACT_BTC_PER_LOT
    net_pnl = leg_pnl - fees_total

    return {"symbol": symbol, "status": exit_reason, "pnl_usd": net_pnl,
            "fees_usd": fees_total, "entry_price": raw_entry_price, "exit_price": raw_exit_price}


def run_backtest(start_date, end_date):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if end_date >= TEST_WINDOW_START or start_date >= TEST_WINDOW_START:
        print("=" * 60)
        print("WARNING: TEST WINDOW (2025-07-01 onward) INCLUDED IN THIS RUN.")
        print("Do NOT re-tune parameters based on this result. Holdout only.")
        print("=" * 60)

    trades = []
    daily_pnls = []
    submode_counts = {}
    submode_stats = {}

    equity = STARTING_CAPITAL_USD
    peak = equity
    halted = False
    day = start_date

    while day <= end_date and not halted:
        submode, spot_entry, entry_time = detect_submode(day)
        if submode is None:
            day += timedelta(days=1)
            continue

        atm_strike = round_to_nearest(spot_entry, STRIKE_ROUND)
        legs, lot_size, sl_pct, exit_hours = get_legs_for_submode(submode, atm_strike)
        submode_counts[submode] = submode_counts.get(submode, 0) + 1
        submode_stats.setdefault(submode, {"pnl": 0.0, "fees": 0.0, "days": 0})

        day_pnl = 0.0
        day_fees = 0.0
        for option_type, strike in legs:
            result = simulate_leg(option_type, strike, day, entry_time, lot_size, sl_pct, exit_hours, spot_entry)
            result.update({"date": day.isoformat(), "submode": submode})
            trades.append(result)
            if result["status"] != "NO_DATA":
                day_pnl += result["pnl_usd"]
                day_fees += result.get("fees_usd", 0.0)

        daily_cap_breached = day_pnl < -DAILY_LOSS_CAP_USD

        submode_stats[submode]["pnl"] += day_pnl
        submode_stats[submode]["fees"] += day_fees
        submode_stats[submode]["days"] += 1

        equity += day_pnl
        peak = max(peak, equity)
        dd_pct = (peak - equity) / STARTING_CAPITAL_USD * 100 if STARTING_CAPITAL_USD > 0 else 0

        daily_pnls.append({"date": day.isoformat(), "submode": submode, "pnl_usd": day_pnl,
                            "fees_usd": day_fees, "equity": equity, "cap_breached": daily_cap_breached})

        flag = " [DAILY CAP BREACHED]" if daily_cap_breached else ""
        print(f"{day.isoformat()} submode={submode} day_pnl=${day_pnl:.2f} fees=${day_fees:.2f} "
              f"equity=${equity:.2f}{flag}")

        if dd_pct >= ACCOUNT_DD_STOP_PCT * 100:
            print(f"\n*** ACCOUNT DRAWDOWN STOP TRIGGERED: {dd_pct:.1f}% >= {ACCOUNT_DD_STOP_PCT*100:.0f}% ***")
            print("*** HALTING BACKTEST - MANUAL REVIEW REQUIRED ***\n")
            halted = True

        day += timedelta(days=1)
        time.sleep(0.3)

    write_trade_log(trades)
    write_summary(daily_pnls, submode_counts, submode_stats, halted)
    return daily_pnls


def write_trade_log(trades):
    with open(TRADE_LOG_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date", "submode", "symbol", "status", "entry_price", "exit_price", "pnl_usd", "fees_usd"
        ])
        writer.writeheader()
        writer.writerows(trades)


def write_summary(daily_pnls, submode_counts, submode_stats, halted):
    with open(SUMMARY_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "submode", "pnl_usd", "fees_usd", "equity", "cap_breached"])
        writer.writeheader()
        writer.writerows(daily_pnls)

    pnls = [d["pnl_usd"] for d in daily_pnls]
    fees = [d["fees_usd"] for d in daily_pnls]
    n = len(pnls)
    if n == 0:
        print("No trading days processed.")
        return

    total_pnl = sum(pnls)
    total_fees = sum(fees)
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

    print("\n==================== PORTFOLIO REPORT (v2, all-scenario) ====================")
    print(f"Days traded          : {n}")
    print(f"Total PnL net of fees: {total_pnl:.2f} USD")
    print(f"Total fees paid      : {total_fees:.2f} USD")
    print(f"Avg PnL/day (USD)    : {mean_pnl:.2f}")
    print(f"Sharpe (ann.)        : {sharpe:.2f}")
    print(f"Max Drawdown USD     : {max_dd:.2f} ({max_dd_pct:.1f}% of capital)")
    print(f"Final equity USD     : {equity:.2f}")
    print(f"Submode occurrence   : {submode_counts}")
    print(f"Backtest halted early: {halted}")
    print("\n--- PER-SUBMODE BREAKDOWN (isolated, not hidden in combined number) ---")
    for mode, stats in submode_stats.items():
        avg = stats["pnl"] / stats["days"] if stats["days"] > 0 else 0
        print(f"  {mode:12s} days={stats['days']:3d} total_pnl=${stats['pnl']:8.2f} "
              f"avg/day=${avg:7.2f} fees=${stats['fees']:7.2f}")
    print("\nGate check: Sharpe>=3.0 ->", "PASS" if sharpe >= 3.0 else "FAIL")
    print("Gate check: MaxDD<=10%  ->", "PASS" if max_dd_pct <= 10.0 else "FAIL")
    print("================================================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="All-scenario BTC option portfolio backtest v2.")
    parser.add_argument("--start", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", type=str, required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()

    run_backtest(start_date, end_date)

