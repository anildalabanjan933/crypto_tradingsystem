import time
import os
import argparse
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = "https://api.india.delta.exchange"
CANDLE_PATH = "/v2/history/candles"
UNDERLYING_SYMBOL = ".DEXBTUSD"

OUTPUT_DIR = "output_options"
REQUEST_TIMEOUT = (3, 27)

STARTING_CAPITAL_USD = 227.0
STRIKE_ROUND = 1000
RESOLUTION = "5m"

parser = argparse.ArgumentParser()
parser.add_argument("--start", required=True)
parser.add_argument("--end", required=True)
parser.add_argument("--combo", required=True, choices=["weekly_monthly", "monthly_monthly"])
parser.add_argument("--variant", required=True, choices=["5pct", "10pct", "host", "leg05", "leg03"])
args = parser.parse_args()

def fetch_candles(symbol, start_ts, end_ts, resolution=RESOLUTION):
    all_candles = []
    cursor = start_ts
    while cursor < end_ts:
        chunk_end = min(cursor + 86400 * 10, end_ts)
        params = {"symbol": symbol, "resolution": resolution, "start": cursor, "end": chunk_end}
        try:
            resp = requests.get(BASE_URL + CANDLE_PATH, params=params, timeout=REQUEST_TIMEOUT)
            data = resp.json()
        except Exception as e:
            print(f"ERROR fetching {symbol}: {e}")
            return []
        if not data.get("success", False):
            cursor = chunk_end
            continue
        all_candles.extend(data.get("result", []))
        cursor = chunk_end
        time.sleep(0.1)
    return all_candles

def get_weekly_expiries(start_date, end_date):
    expiries = []
    d = start_date
    while d.weekday() != 4:
        d += timedelta(days=1)
    while d <= end_date:
        expiries.append(d)
        d += timedelta(days=7)
    return expiries

def get_monthly_expiries(start_date, end_date):
    expiries = []
    d = start_date.replace(day=1)
    while d <= end_date:
        if d.month == 12:
            next_month = d.replace(year=d.year + 1, month=1, day=1)
        else:
            next_month = d.replace(month=d.month + 1, day=1)
        last_day = next_month - timedelta(days=1)
        while last_day.weekday() != 4:
            last_day -= timedelta(days=1)
        if last_day >= start_date and last_day <= end_date:
            expiries.append(last_day)
        d = next_month
    return expiries

def build_option_symbol(option_type, strike, expiry_date):
    ddmmyy = expiry_date.strftime("%d%m%y")
    return f"{option_type}-BTC-{strike}-{ddmmyy}"

def round_strike(spot_price):
    return int(round(spot_price / STRIKE_ROUND) * STRIKE_ROUND)

def calc_fee(spot_price, premium):
    return min(0.00015 * spot_price, 0.05 * premium) * 1.18

def apply_slippage_sell(premium):
    return premium * (1 - 0.05)

def apply_slippage_buy(premium):
    return premium * (1 + 0.05)

def get_leg_premium(option_type, strike, expiry_date, ts):
    symbol = build_option_symbol(option_type, strike, expiry_date)
    candles = fetch_candles(symbol, ts, ts + 300)
    if not candles:
        return None, symbol
    premium = candles[0].get("close")
    return premium, symbol

def enter_calendar(near_expiry, far_expiry, spot_price, entry_ts):
    atm_strike = round_strike(spot_price)

    call_near_raw, call_near_symbol = get_leg_premium("C", atm_strike, near_expiry, entry_ts)
    call_far_raw, call_far_symbol = get_leg_premium("C", atm_strike, far_expiry, entry_ts)
    put_near_raw, put_near_symbol = get_leg_premium("P", atm_strike, near_expiry, entry_ts)
    put_far_raw, put_far_symbol = get_leg_premium("P", atm_strike, far_expiry, entry_ts)

    if None in (call_near_raw, call_far_raw, put_near_raw, put_far_raw):
        return None

    call_debit = call_far_raw - call_near_raw
    put_debit = put_far_raw - put_near_raw

    if call_debit <= put_debit:
        option_type = "C"
        near_raw, far_raw = call_near_raw, call_far_raw
        near_symbol, far_symbol = call_near_symbol, call_far_symbol
    else:
        option_type = "P"
        near_raw, far_raw = put_near_raw, put_far_raw
        near_symbol, far_symbol = put_near_symbol, put_far_symbol

    near_fill = apply_slippage_sell(near_raw)
    far_fill = apply_slippage_buy(far_raw)

    fee_near = calc_fee(spot_price, near_fill)
    fee_far = calc_fee(spot_price, far_fill)

    net_debit = far_fill - near_fill
    total_fees = fee_near + fee_far

    return {
        "option_type": option_type,
        "strike": atm_strike,
        "near_expiry": near_expiry,
        "far_expiry": far_expiry,
        "near_symbol": near_symbol,
        "far_symbol": far_symbol,
        "near_premium": near_fill,
        "far_premium": far_fill,
        "net_debit": net_debit,
        "total_fees": total_fees,
    }

def get_sl_target_pct(variant):
    if variant == "5pct":
        return 0.05, 0.05
    elif variant == "10pct":
        return 0.10, 0.10
    elif variant == "host":
        return 0.075, 0.075
    return None, None

def check_exit(position, current_near, current_far, variant):
    net_debit = position["net_debit"]
    current_value = current_far - current_near
    pnl = current_value - net_debit

    sl_pct, tgt_pct = get_sl_target_pct(variant)
    sl_level = -(net_debit * sl_pct)
    tgt_level = net_debit * tgt_pct

    if pnl <= sl_level:
        return "SL", pnl
    if pnl >= tgt_level:
        return "TARGET", pnl
    return None, pnl

def check_exit_perleg(position, current_near, current_far, variant):
    near_credit = position["near_premium"]
    tgt_mult = 0.5 if variant == "leg05" else 0.3

    near_sl_level = near_credit * 2
    near_tgt_level = near_credit * tgt_mult

    current_value = current_far - current_near
    pnl = current_value - position["net_debit"]

    if current_near >= near_sl_level:
        return "SL_NEAR", pnl
    if current_near <= near_tgt_level:
        return "TARGET_NEAR", pnl
    return None, pnl

def date_to_ts(d, hour=12, minute=0):
    return int(datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc).timestamp())

def run_backtest():
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()

    if args.combo == "weekly_monthly":
        near_expiries = get_weekly_expiries(start_date, end_date)
        monthly_expiries = get_monthly_expiries(start_date, end_date + timedelta(days=35))
    else:
        monthly_expiries = get_monthly_expiries(start_date, end_date + timedelta(days=65))
        near_expiries = [m for m in monthly_expiries if m <= end_date]

    equity = STARTING_CAPITAL_USD

    for near_expiry in near_expiries:
        far_candidates = [m for m in monthly_expiries if m > near_expiry]
        if not far_candidates:
            print(f"{near_expiry} submode=NO_DATA day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue
        far_expiry = far_candidates[0]

        entry_ts = date_to_ts(near_expiry - timedelta(days=1))

        spot_candles = fetch_candles(UNDERLYING_SYMBOL, entry_ts, entry_ts + 3600)
        if not spot_candles:
            print(f"{near_expiry} submode=NO_DATA day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue
        spot_price = spot_candles[0].get("close")

        position = enter_calendar(near_expiry, far_expiry, spot_price, entry_ts)
        if position is None:
            print(f"{near_expiry} submode=NO_DATA day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue

        exit_reason = "EXPIRY"
        pnl = 0.0
        expiry_ts = date_to_ts(near_expiry, hour=17, minute=30)

        cursor_ts = entry_ts
        while cursor_ts < expiry_ts:
            nc = fetch_candles(position["near_symbol"], cursor_ts, cursor_ts + 3600)
            fc = fetch_candles(position["far_symbol"], cursor_ts, cursor_ts + 3600)

            if nc and fc:
                cur_near = nc[0].get("close")
                cur_far = fc[0].get("close")
                if args.variant in ["leg05", "leg03"]:
                    reason, running_pnl = check_exit_perleg(position, cur_near, cur_far, args.variant)
                else:
                    reason, running_pnl = check_exit(position, cur_near, cur_far, args.variant)
                if reason:
                    exit_reason = reason
                    pnl = running_pnl
                    break

            cursor_ts += 3600

        net_pnl = pnl - position["total_fees"]
        equity += net_pnl

        print(f"{near_expiry} submode={exit_reason} day_pnl=${net_pnl:.2f} fees=${position['total_fees']:.2f} equity=${equity:.2f}")

if __name__ == "__main__":
    run_backtest()
