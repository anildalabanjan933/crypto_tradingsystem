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
parser.add_argument("--expiry", required=True, choices=["weekly", "monthly"])
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

def enter_straddle(expiry_date, spot_price, entry_ts):
    atm_strike = round_strike(spot_price)
    call_symbol = build_option_symbol("C", atm_strike, expiry_date)
    put_symbol = build_option_symbol("P", atm_strike, expiry_date)

    call_candles = fetch_candles(call_symbol, entry_ts, entry_ts + 3600)
    put_candles = fetch_candles(put_symbol, entry_ts, entry_ts + 3600)
    if not call_candles or not put_candles:
        return None

    call_raw = call_candles[0].get("close")
    put_raw = put_candles[0].get("close")
    if call_raw is None or put_raw is None:
        return None

    call_fill = apply_slippage_sell(call_raw)
    put_fill = apply_slippage_sell(put_raw)

    fee_call = calc_fee(spot_price, call_fill)
    fee_put = calc_fee(spot_price, put_fill)

    net_credit = call_fill + put_fill
    total_fees = fee_call + fee_put

    return {
        "expiry_date": expiry_date,
        "entry_ts": entry_ts,
        "spot_price": spot_price,
        "strike": atm_strike,
        "call_symbol": call_symbol,
        "put_symbol": put_symbol,
        "call_premium": call_fill,
        "put_premium": put_fill,
        "net_credit": net_credit,
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

def check_exit(position, current_call, current_put, variant):
    net_credit = position["net_credit"]
    current_value = current_call + current_put
    pnl = net_credit - current_value

    sl_pct, tgt_pct = get_sl_target_pct(variant)
    sl_level = -(net_credit * sl_pct)
    tgt_level = net_credit * tgt_pct

    if pnl <= sl_level:
        return "SL", pnl
    if pnl >= tgt_level:
        return "TARGET", pnl
    return None, pnl

def check_exit_perleg(position, current_call, current_put, variant):
    call_credit = position["call_premium"]
    put_credit = position["put_premium"]

    tgt_mult = 0.5 if variant == "leg05" else 0.3

    call_sl_level = call_credit * 2
    put_sl_level = put_credit * 2
    call_tgt_level = call_credit * tgt_mult
    put_tgt_level = put_credit * tgt_mult

    pnl = position["net_credit"] - (current_call + current_put)

    if current_call >= call_sl_level:
        return "SL_CALL", pnl
    if current_put >= put_sl_level:
        return "SL_PUT", pnl
    if current_call <= call_tgt_level:
        return "TARGET_CALL", pnl
    if current_put <= put_tgt_level:
        return "TARGET_PUT", pnl
    return None, pnl

def date_to_ts(d, hour=12, minute=0):
    return int(datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc).timestamp())

def next_monday_on_or_after(d):
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d

def run_backtest():
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()

    if args.expiry == "weekly":
        expiries = get_weekly_expiries(start_date, end_date)
    else:
        expiries = get_monthly_expiries(start_date, end_date)

    equity = STARTING_CAPITAL_USD

    for expiry_date in expiries:
        window_start = expiry_date - timedelta(days=6 if args.expiry == "weekly" else 27)
        entry_date = next_monday_on_or_after(window_start)
        if entry_date >= expiry_date:
            entry_date = expiry_date - timedelta(days=1)
        entry_ts = date_to_ts(entry_date)

        spot_candles = fetch_candles(UNDERLYING_SYMBOL, entry_ts, entry_ts + 3600)
        if not spot_candles:
            print(f"{expiry_date} submode=NO_DATA day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue
        spot_price = spot_candles[0].get("close")

        position = enter_straddle(expiry_date, spot_price, entry_ts)
        if position is None:
            print(f"{expiry_date} submode=NO_DATA day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue

        exit_reason = "EXPIRY"
        pnl = position["net_credit"]
        expiry_ts = date_to_ts(expiry_date, hour=17, minute=30)

        cursor_ts = entry_ts
        while cursor_ts < expiry_ts:
            cc = fetch_candles(position["call_symbol"], cursor_ts, cursor_ts + 3600)
            cp = fetch_candles(position["put_symbol"], cursor_ts, cursor_ts + 3600)

            if cc and cp:
                cur_call = cc[0].get("close")
                cur_put = cp[0].get("close")
                if args.variant in ["leg05", "leg03"]:
                    reason, running_pnl = check_exit_perleg(position, cur_call, cur_put, args.variant)
                else:
                    reason, running_pnl = check_exit(position, cur_call, cur_put, args.variant)
                if reason:
                    exit_reason = reason
                    pnl = running_pnl
                    break

            cursor_ts += 3600

        net_pnl = pnl - position["total_fees"]
        equity += net_pnl

        print(f"{expiry_date} submode={exit_reason} day_pnl=${net_pnl:.2f} fees=${position['total_fees']:.2f} equity=${equity:.2f}")

if __name__ == "__main__":
    run_backtest()
