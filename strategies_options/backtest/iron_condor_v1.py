import requests
import time
import csv
import os
import argparse
from datetime import datetime, timedelta, timezone

BASE_URL = "https://api.india.delta.exchange"
CANDLE_PATH = "/v2/history/candles"
UNDERLYING_SYMBOL = ".DEXBTUSD"

OUTPUT_DIR = "output_options"
REQUEST_TIMEOUT = (3, 27)

STARTING_CAPITAL_USD = 227.0
STRIKE_ROUND = 1000
RESOLUTION = "5m"

TARGET_PREMIUM_WEEKLY = 200
TARGET_PREMIUM_MONTHLY = 1000
HEDGE_PREMIUM_RATIO = 0.45

parser = argparse.ArgumentParser()
parser.add_argument("--start", required=True)
parser.add_argument("--end", required=True)
parser.add_argument("--expiry", required=True, choices=["weekly", "monthly"])
parser.add_argument("--variant", required=True, choices=["5pct", "10pct", "host", "leg05", "leg03"])
args = parser.parse_args()

TRADE_LOG_FILE = os.path.join(OUTPUT_DIR, f"iron_condor_v1_{args.expiry}_{args.variant}_trades.csv")
SUMMARY_FILE = os.path.join(OUTPUT_DIR, f"iron_condor_v1_{args.expiry}_{args.variant}_summary.csv")

def fetch_candles(symbol, start_ts, end_ts, resolution=RESOLUTION):
    all_candles = []
    cursor = start_ts
    while cursor < end_ts:
        chunk_end = min(cursor + 86400 * 10, end_ts)
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "start": cursor,
            "end": chunk_end,
        }
        try:
            resp = requests.get(
                BASE_URL + CANDLE_PATH,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            data = resp.json()
        except Exception as e:
            print(f"ERROR fetching {symbol}: {e}")
            return []

        if not data.get("success", False):
            cursor = chunk_end
            continue

        result = data.get("result", [])
        all_candles.extend(result)
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

def find_strike_for_target_premium(option_type, expiry_date, spot_price, target_premium, entry_ts):
    base_strike = round_strike(spot_price)
    direction = 1 if option_type == "C" else -1

    for step in range(0, 20):
        candidate_strike = base_strike + direction * step * STRIKE_ROUND
        symbol = build_option_symbol(option_type, candidate_strike, expiry_date)
        candles = fetch_candles(symbol, entry_ts, entry_ts + 3600)
        if not candles:
            continue
        premium = candles[0].get("close")
        if premium is None:
            continue
        if premium <= target_premium:
            return candidate_strike, premium, symbol

    return None, None, None

def find_hedge_strike(option_type, expiry_date, sold_strike, sold_premium, entry_ts):
    target_hedge_premium = sold_premium * HEDGE_PREMIUM_RATIO
    direction = 1 if option_type == "C" else -1

    for step in range(1, 20):
        candidate_strike = sold_strike + direction * step * STRIKE_ROUND
        symbol = build_option_symbol(option_type, candidate_strike, expiry_date)
        candles = fetch_candles(symbol, entry_ts, entry_ts + 3600)
        if not candles:
            continue
        premium = candles[0].get("close")
        if premium is None:
            continue
        if premium <= target_hedge_premium:
            return candidate_strike, premium, symbol

    return None, None, None

def calc_fee(spot_price, premium):
    fee = min(0.00015 * spot_price, 0.05 * premium) * 1.18
    return fee

def apply_slippage_sell(premium):
    return premium * (1 - 0.05)

def apply_slippage_buy(premium):
    return premium * (1 + 0.05)

def enter_iron_condor(expiry_date, spot_price, target_premium, entry_ts):
    sold_call_strike, sold_call_raw, sold_call_symbol = find_strike_for_target_premium(
        "C", expiry_date, spot_price, target_premium, entry_ts
    )
    sold_put_strike, sold_put_raw, sold_put_symbol = find_strike_for_target_premium(
        "P", expiry_date, spot_price, target_premium, entry_ts
    )

    if sold_call_strike is None or sold_put_strike is None:
        return None

    hedge_call_strike, hedge_call_raw, hedge_call_symbol = find_hedge_strike(
        "C", expiry_date, sold_call_strike, sold_call_raw, entry_ts
    )
    hedge_put_strike, hedge_put_raw, hedge_put_symbol = find_hedge_strike(
        "P", expiry_date, sold_put_strike, sold_put_raw, entry_ts
    )

    if hedge_call_strike is None or hedge_put_strike is None:
        return None

    sold_call_fill = apply_slippage_sell(sold_call_raw)
    sold_put_fill = apply_slippage_sell(sold_put_raw)
    hedge_call_fill = apply_slippage_buy(hedge_call_raw)
    hedge_put_fill = apply_slippage_buy(hedge_put_raw)

    fee_sold_call = calc_fee(spot_price, sold_call_fill)
    fee_sold_put = calc_fee(spot_price, sold_put_fill)
    fee_hedge_call = calc_fee(spot_price, hedge_call_fill)
    fee_hedge_put = calc_fee(spot_price, hedge_put_fill)

    net_credit = (sold_call_fill + sold_put_fill) - (hedge_call_fill + hedge_put_fill)
    total_fees = fee_sold_call + fee_sold_put + fee_hedge_call + fee_hedge_put

    call_width = hedge_call_strike - sold_call_strike
    put_width = sold_put_strike - hedge_put_strike
    max_loss = max(call_width, put_width) - net_credit

    return {
        "expiry_date": expiry_date,
        "entry_ts": entry_ts,
        "spot_price": spot_price,
        "sold_call_strike": sold_call_strike,
        "sold_call_symbol": sold_call_symbol,
        "sold_call_premium": sold_call_fill,
        "sold_put_strike": sold_put_strike,
        "sold_put_symbol": sold_put_symbol,
        "sold_put_premium": sold_put_fill,
        "hedge_call_strike": hedge_call_strike,
        "hedge_call_symbol": hedge_call_symbol,
        "hedge_call_premium": hedge_call_fill,
        "hedge_put_strike": hedge_put_strike,
        "hedge_put_symbol": hedge_put_symbol,
        "hedge_put_premium": hedge_put_fill,
        "net_credit": net_credit,
        "max_loss": max_loss,
        "total_fees": total_fees,
    }

def get_sl_target_pct(variant):
    if variant == "5pct":
        return 0.05, 0.05
    elif variant == "10pct":
        return 0.10, 0.10
    elif variant == "host":
        return None, 0.075
    return None, None

def check_exit(position, current_sold_call, current_sold_put, current_hedge_call, current_hedge_put, variant):
    net_credit = position["net_credit"]
    max_loss = position["max_loss"]

    current_value = (current_sold_call + current_sold_put) - (current_hedge_call + current_hedge_put)
    pnl = net_credit - current_value

    sl_pct, tgt_pct = get_sl_target_pct(variant)

    if variant == "host":
        sl_level = -(max_loss * 0.5)
        if pnl <= sl_level:
            return "SL", pnl
        tgt_level = net_credit * tgt_pct
        if pnl >= tgt_level:
            return "TARGET", pnl
    else:
        max_profit = net_credit
        sl_level = -(max_profit * sl_pct)
        if pnl <= sl_level:
            return "SL", pnl
        tgt_level = max_profit * tgt_pct
        if pnl >= tgt_level:
            return "TARGET", pnl

    return None, pnl

def date_to_ts(d, hour=12, minute=0):
    return int(datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc).timestamp())

def run_backtest():
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()

    if args.expiry == "weekly":
        expiries = get_weekly_expiries(start_date, end_date)
        target_premium = TARGET_PREMIUM_WEEKLY
    else:
        expiries = get_monthly_expiries(start_date, end_date)
        target_premium = TARGET_PREMIUM_MONTHLY

    equity = STARTING_CAPITAL_USD
    trades = []

    for expiry_date in expiries:
        entry_ts = date_to_ts(expiry_date - timedelta(days=1 if args.expiry == "weekly" else 7))

        spot_candles = fetch_candles(UNDERLYING_SYMBOL, entry_ts, entry_ts + 3600)
        if not spot_candles:
            print(f"{expiry_date} submode=NO_DATA day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue
        spot_price = spot_candles[0].get("close")

        position = enter_iron_condor(expiry_date, spot_price, target_premium, entry_ts)
        if position is None:
            print(f"{expiry_date} submode=NO_DATA day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue

        exit_reason = "EXPIRY"
        pnl = position["net_credit"]
        expiry_ts = date_to_ts(expiry_date, hour=17, minute=30)

        cursor_ts = entry_ts
        while cursor_ts < expiry_ts:
            sc = fetch_candles(position["sold_call_symbol"], cursor_ts, cursor_ts + 3600)
            sp = fetch_candles(position["sold_put_symbol"], cursor_ts, cursor_ts + 3600)
            hc = fetch_candles(position["hedge_call_symbol"], cursor_ts, cursor_ts + 3600)
            hp = fetch_candles(position["hedge_put_symbol"], cursor_ts, cursor_ts + 3600)

            if sc and sp and hc and hp:
                cur_sc = sc[0].get("close")
                cur_sp = sp[0].get("close")
                cur_hc = hc[0].get("close")
                cur_hp = hp[0].get("close")
                if args.variant in ["leg05", "leg03"]:
                    reason, running_pnl = check_exit_perleg(position, cur_sc, cur_sp, cur_hc, cur_hp, args.variant)
                else:
                    reason, running_pnl = check_exit(position, cur_sc, cur_sp, cur_hc, cur_hp, args.variant)
                if reason:
                    exit_reason = reason
                    pnl = running_pnl
                    break

            cursor_ts += 3600

        net_pnl = pnl - position["total_fees"]
        equity += net_pnl

        trades.append({
            "expiry_date": expiry_date,
            "exit_reason": exit_reason,
            "net_credit": position["net_credit"],
            "max_loss": position["max_loss"],
            "fees": position["total_fees"],
            "pnl": net_pnl,
            "equity": equity,
        })

        print(f"{expiry_date} submode={exit_reason} day_pnl=${net_pnl:.2f} fees=${position['total_fees']:.2f} equity=${equity:.2f}")

    return trades


def check_exit_perleg(position, current_sold_call, current_sold_put, current_hedge_call, current_hedge_put, variant):
    sold_call_credit = position["sold_call_premium"]
    sold_put_credit = position["sold_put_premium"]

    if variant == "leg05":
        tgt_mult = 0.5
    elif variant == "leg03":
        tgt_mult = 0.3
    else:
        tgt_mult = 0.5

    call_sl_level = sold_call_credit * 2
    put_sl_level = sold_put_credit * 2
    call_tgt_level = sold_call_credit * tgt_mult
    put_tgt_level = sold_put_credit * tgt_mult

    current_value = (current_sold_call + current_sold_put) - (current_hedge_call + current_hedge_put)
    pnl = position["net_credit"] - current_value

    if current_sold_call >= call_sl_level:
        return "SL_CALL", pnl
    if current_sold_put >= put_sl_level:
        return "SL_PUT", pnl
    if current_sold_call <= call_tgt_level:
        return "TARGET_CALL", pnl
    if current_sold_put <= put_tgt_level:
        return "TARGET_PUT", pnl

    return None, pnl
if __name__ == "__main__":
    run_backtest()
