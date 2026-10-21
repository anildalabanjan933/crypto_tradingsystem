import time
import argparse
import requests
import bisect
from datetime import datetime, timedelta, timezone

BASE_URL = "https://api.india.delta.exchange"
CANDLE_PATH = "/v2/history/candles"
PRODUCT_PATH = "/v2/products"
UNDERLYING_SYMBOL = ".DEXBTUSD"

STARTING_CAPITAL_USD = 227.0
STRIKE_ROUND = 1000
RESOLUTION = "5m"
STEP_SECONDS = 300
RETRY_COUNT = 3

MAX_FILL_GAP = 1800
MAX_MARK_AGE = 1800
CONTRACT_VALUE_BTC = 0.001

TARGET_PREMIUM_WEEKLY = 200
TARGET_PREMIUM_MONTHLY = 1000

parser = argparse.ArgumentParser()
parser.add_argument("--start", required=True)
parser.add_argument("--end", required=True)
parser.add_argument("--expiry", required=True, choices=["weekly", "monthly"])
parser.add_argument("--dte", required=True, type=int)
parser.add_argument("--variant", required=True, choices=["5pct", "10pct", "30pct", "50pct", "host", "leg05", "leg03"])
parser.add_argument("--lots", type=int, default=100)
parser.add_argument("--max-skew", type=int, default=1800)
parser.add_argument("--require-target", action="store_true",
                    help="skip the week if either leg could not reach its target premium")
parser.add_argument("--debug", action="store_true", help="print per-exit DEBUG line")
args = parser.parse_args()
MAX_LEG_SKEW = args.max_skew


class FetchError(Exception):
    pass


def fetch_candles_range(symbol, start_ts, end_ts, resolution=RESOLUTION):
    seen = {}
    cursor = start_ts
    while cursor < end_ts:
        chunk_end = min(cursor + 86400 * 5, end_ts)
        params = {"symbol": symbol, "resolution": resolution, "start": cursor, "end": chunk_end}
        ok = False
        for attempt in range(1, RETRY_COUNT + 1):
            try:
                resp = requests.get(BASE_URL + CANDLE_PATH, params=params, timeout=(3, 27))
                data = resp.json()
                if data.get("success", False):
                    for c in data.get("result", []):
                        seen[c["time"]] = c
                    ok = True
                    break
                print(f"WARNING fetch {symbol} [{cursor}-{chunk_end}] attempt {attempt}/{RETRY_COUNT} "
                      f"success=false: {str(data)[:200]}")
            except Exception as e:
                print(f"WARNING fetch {symbol} [{cursor}-{chunk_end}] attempt {attempt}/{RETRY_COUNT} failed: {e}")
            time.sleep(attempt * 1.0)
        if not ok:
            raise FetchError(f"{symbol} chunk {cursor}-{chunk_end} failed after {RETRY_COUNT} attempts")
        cursor = chunk_end
    return [seen[t] for t in sorted(seen)]


def fetch_product(symbol):
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            resp = requests.get(f"{BASE_URL}{PRODUCT_PATH}/{symbol}", timeout=(3, 27))
            if resp.status_code == 429 or resp.status_code >= 500:
                print(f"WARNING product {symbol} attempt {attempt}/{RETRY_COUNT} HTTP {resp.status_code}")
                time.sleep(attempt * 1.0)
                continue
            data = resp.json()
            if data.get("success", False):
                return data.get("result", {}) or {}
            return None
        except Exception as e:
            print(f"WARNING product {symbol} attempt {attempt}/{RETRY_COUNT} failed: {e}")
            time.sleep(attempt * 1.0)
    return None


def fetch_settlement_price(symbol):
    res = fetch_product(symbol)
    if res is None:
        print(f"WARNING settlement lookup failed for {symbol}")
        return None
    sp = res.get("settlement_price")
    if sp is None:
        print(f"WARNING settlement_price missing for {symbol}")
        return None
    return float(sp)


class CandleSeries:
    def __init__(self, candles):
        self.candles = candles
        self.times = [c["time"] for c in candles]

    def mark_price(self, ts):
        idx = bisect.bisect_right(self.times, ts) - 1
        if idx < 0:
            return None
        return self.candles[idx]["close"]

    def mark_with_age(self, ts):
        idx = bisect.bisect_right(self.times, ts) - 1
        if idx < 0:
            return None, None
        return self.candles[idx]["close"], ts - self.times[idx]

    def fill_at(self, ts, max_gap=MAX_FILL_GAP):
        idx = bisect.bisect_right(self.times, ts)
        if idx >= len(self.candles):
            return None, None
        c = self.candles[idx]
        if c["time"] - ts > max_gap:
            return None, None
        return c["open"], c["time"]


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
        if start_date <= last_day <= end_date:
            expiries.append(last_day)
        d = next_month
    return expiries


def build_option_symbol(option_type, strike, expiry_date):
    ddmmyy = expiry_date.strftime("%d%m%y")
    return f"{option_type}-BTC-{strike}-{ddmmyy}"


def round_strike(spot_price):
    return int(round(spot_price / STRIKE_ROUND) * STRIKE_ROUND)


_LAUNCH_CACHE = {}


def parse_launch_ts(s):
    s = s.split(".")[0].rstrip("Z")
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp())


def is_strike_listed(option_type, strike, expiry_date, entry_ts):
    symbol = build_option_symbol(option_type, strike, expiry_date)
    if symbol not in _LAUNCH_CACHE:
        res = fetch_product(symbol)
        lt = (res or {}).get("launch_time")
        try:
            _LAUNCH_CACHE[symbol] = parse_launch_ts(lt) if lt else None
        except Exception:
            _LAUNCH_CACHE[symbol] = None
    launch_ts = _LAUNCH_CACHE[symbol]
    return launch_ts is not None and launch_ts <= entry_ts


def find_strangle_strike(option_type, spot_price, expiry_date, entry_ts, target_premium, max_steps=20):
    """Walk OTM over tradable strikes; return the strike whose premium is NEAREST the target."""
    base = round_strike(spot_price)
    direction = 1 if option_type == "C" else -1
    prev = None
    for step in range(max_steps):
        strike = base + direction * step * STRIKE_ROUND
        if strike <= 0:
            break
        if not is_strike_listed(option_type, strike, expiry_date, entry_ts):
            continue
        symbol = build_option_symbol(option_type, strike, expiry_date)
        try:
            candles = fetch_candles_range(symbol, entry_ts, entry_ts + 3600)
        except FetchError:
            continue
        if not candles:
            continue
        premium, fill_ts = CandleSeries(candles).fill_at(entry_ts)
        if premium is None or premium <= 0:
            continue
        cand = {"strike": strike, "symbol": symbol, "premium": premium,
                "fill_ts": fill_ts, "target_met": premium <= target_premium}
        if premium <= target_premium:
            if prev is not None and abs(prev["premium"] - target_premium) < abs(premium - target_premium):
                return prev
            return cand
        prev = cand
    return prev


def calc_fee(spot_price, premium):
    return min(0.00015 * spot_price, 0.05 * premium) * 1.18


def apply_slippage_sell(premium):
    return premium * (1 - 0.05)


def apply_slippage_buy(premium):
    return premium * (1 + 0.05)


def date_to_ts(d, hour=12, minute=0):
    return int(datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc).timestamp())


HOST_SL_PCT = 1.00


def get_sl_target_pct(variant):
    """(combined_sl_pct, target_pct). Only HOST_SL_PCT is a combined-credit SL; others use per-leg doubling."""
    tg = {"5pct": 0.05, "10pct": 0.10, "30pct": 0.30, "50pct": 0.50, "host": 0.075}
    if variant not in tg:
        return None, None
    return (HOST_SL_PCT if variant == "host" else None), tg[variant]


def check_exit(raw_credit, call_entry_raw, put_entry_raw, cur_call_mark, cur_put_mark, variant):
    sl_pct, tgt_pct = get_sl_target_pct(variant)
    pnl = raw_credit - (cur_call_mark + cur_put_mark)
    if pnl >= raw_credit * tgt_pct:
        return "TARGET"
    if sl_pct is not None:                      # strangle host: 2x total premium
        return "SL" if pnl <= -(raw_credit * sl_pct) else None
    if cur_call_mark >= call_entry_raw * 2 or cur_put_mark >= put_entry_raw * 2:
        return "SL"                              # per-leg: sold leg doubled
    return None


def check_exit_perleg(call_entry_raw, put_entry_raw, cur_call_mark, cur_put_mark, variant):
    p = 0.05 if variant == "leg05" else 0.03
    if cur_call_mark >= call_entry_raw * (1 + p):
        return "SL_CALL"
    if cur_put_mark >= put_entry_raw * (1 + p):
        return "SL_PUT"
    if cur_call_mark <= call_entry_raw * (1 - p):
        return "TARGET_CALL"
    if cur_put_mark <= put_entry_raw * (1 - p):
        return "TARGET_PUT"
    return None


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
    multiplier = args.lots * CONTRACT_VALUE_BTC

    for expiry_date in expiries:
        entry_date = expiry_date - timedelta(days=args.dte)
        if entry_date >= expiry_date:
            entry_date = expiry_date - timedelta(days=1)
        if equity <= 0:
            print(f"{expiry_date} submode=LIQUIDATED day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue
        entry_ts = date_to_ts(entry_date)
        settlement_ts = date_to_ts(expiry_date, hour=12, minute=0)

        try:
            spot_full = fetch_candles_range(UNDERLYING_SYMBOL, entry_ts, settlement_ts + STEP_SECONDS)
        except FetchError as e:
            print(f"WARNING {expiry_date} {e}")
            print(f"{expiry_date} submode=FETCH_FAIL day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue
        if not spot_full:
            print(f"{expiry_date} submode=NO_DATA day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue
        spot_series = CandleSeries(spot_full)
        spot_price = spot_series.mark_price(entry_ts)
        if spot_price is None:
            print(f"{expiry_date} submode=NO_DATA day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue

        call_sel = find_strangle_strike("C", spot_price, expiry_date, entry_ts, target_premium)
        put_sel = find_strangle_strike("P", spot_price, expiry_date, entry_ts, target_premium)
        if call_sel is None or put_sel is None:
            print(f"{expiry_date} submode=NO_FILL day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue

        target_met = call_sel["target_met"] and put_sel["target_met"]
        call_strike, call_symbol = call_sel["strike"], call_sel["symbol"]
        put_strike, put_symbol = put_sel["strike"], put_sel["symbol"]
        call_dist = (call_strike - spot_price) / spot_price * 100
        put_dist = (spot_price - put_strike) / spot_price * 100
        sel_info = (f"call_k={call_strike}({call_dist:.1f}%,p={call_sel['premium']:.0f}) "
                    f"put_k={put_strike}({put_dist:.1f}%,p={put_sel['premium']:.0f}) "
                    f"target_met={target_met}")

        if args.require_target and not target_met:
            print(f"{expiry_date} submode=TARGET_NOT_MET day_pnl=$0.00 fees=$0.00 equity=${equity:.2f} {sel_info}")
            continue

        try:
            call_full = fetch_candles_range(call_symbol, entry_ts, settlement_ts + STEP_SECONDS)
            put_full = fetch_candles_range(put_symbol, entry_ts, settlement_ts + STEP_SECONDS)
        except FetchError as e:
            print(f"WARNING {expiry_date} {e}")
            print(f"{expiry_date} submode=FETCH_FAIL day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue
        if not call_full or not put_full:
            print(f"{expiry_date} submode=NO_DATA day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue

        call_series = CandleSeries(call_full)
        put_series = CandleSeries(put_full)

        call_entry_raw, call_fill_ts = call_series.fill_at(entry_ts)
        put_entry_raw, put_fill_ts = put_series.fill_at(entry_ts)
        if call_fill_ts is None or put_fill_ts is None:
            print(f"WARNING {expiry_date} entry leg fill missing "
                  f"(call_fill_ts={call_fill_ts} put_fill_ts={put_fill_ts})")
            print(f"{expiry_date} submode=NO_LIQUIDITY day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
            continue

        entry_leg_skew = abs(call_fill_ts - put_fill_ts)
        if entry_leg_skew > MAX_LEG_SKEW:
            print(f"WARNING {expiry_date} legs filled {entry_leg_skew}s apart "
                  f"(> {MAX_LEG_SKEW}s tolerance), proceeding anyway")
        entry_fill_ts = max(call_fill_ts, put_fill_ts)

        call_entry_fill = apply_slippage_sell(call_entry_raw)
        put_entry_fill = apply_slippage_sell(put_entry_raw)
        entry_fee = calc_fee(spot_price, call_entry_fill) + calc_fee(spot_price, put_entry_fill)
        net_credit = call_entry_fill + put_entry_fill
        raw_credit = call_entry_raw + put_entry_raw

        exit_reason = "EXPIRY"
        exit_pnl_raw = None
        exit_fee = 0.0
        stale_bars = 0

        cursor_ts = entry_fill_ts + STEP_SECONDS
        while cursor_ts < settlement_ts:
            cur_call_mark, call_age = call_series.mark_with_age(cursor_ts)
            cur_put_mark, put_age = put_series.mark_with_age(cursor_ts)
            stale = (call_age is not None and call_age > MAX_MARK_AGE) or \
                    (put_age is not None and put_age > MAX_MARK_AGE)
            if stale:
                stale_bars += 1

            if cur_call_mark is not None and cur_put_mark is not None and not stale:
                if args.variant in ["leg05", "leg03"]:
                    reason = check_exit_perleg(call_entry_raw, put_entry_raw, cur_call_mark, cur_put_mark, args.variant)
                else:
                    reason = check_exit(raw_credit, call_entry_raw, put_entry_raw, cur_call_mark, cur_put_mark, args.variant)

                if reason:
                    call_exit_raw, call_exit_fill_ts = call_series.fill_at(cursor_ts)
                    put_exit_raw, put_exit_fill_ts = put_series.fill_at(cursor_ts)
                    if call_exit_fill_ts is None or put_exit_fill_ts is None:
                        cursor_ts += STEP_SECONDS
                        continue

                    call_exit_fill = apply_slippage_buy(call_exit_raw)
                    put_exit_fill = apply_slippage_buy(put_exit_raw)
                    exit_spot, _age = spot_series.mark_with_age(cursor_ts)
                    exit_spot = exit_spot or spot_price
                    exit_fee = calc_fee(exit_spot, call_exit_fill) + calc_fee(exit_spot, put_exit_fill)
                    exit_pnl_raw = net_credit - (call_exit_fill + put_exit_fill)
                    exit_reason = reason
                    if args.debug:
                        print(f"DEBUG {expiry_date} raw_credit={raw_credit:.4f} net_credit={net_credit:.4f} "
                              f"trigger_call={cur_call_mark:.4f} trigger_put={cur_put_mark:.4f} "
                              f"call_age={call_age} put_age={put_age} "
                              f"call_drift={call_exit_raw - cur_call_mark:.4f} "
                              f"put_drift={put_exit_raw - cur_put_mark:.4f} "
                              f"call_exit_fill={call_exit_fill:.4f} put_exit_fill={put_exit_fill:.4f} "
                              f"exit_pnl_raw={exit_pnl_raw:.4f} entry_fee={entry_fee:.4f} exit_fee={exit_fee:.4f}")
                    break

            cursor_ts += STEP_SECONDS

        if exit_pnl_raw is None:
            if settlement_ts > int(time.time()):
                print(f"{expiry_date} submode=UNSETTLED day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
                continue

            call_settle = fetch_settlement_price(call_symbol)
            put_settle = fetch_settlement_price(put_symbol)
            if call_settle is not None and put_settle is not None:
                exit_pnl_raw = net_credit - (call_settle + put_settle)
                print(f"SETTLE {expiry_date} call_settle={call_settle:.4f} put_settle={put_settle:.4f} "
                      f"call_k={call_strike} put_k={put_strike}")
            else:
                settle_mark, settle_age = spot_series.mark_with_age(settlement_ts)
                if settle_mark is None or settle_age > STEP_SECONDS:
                    print(f"{expiry_date} submode=UNSETTLED day_pnl=$0.00 fees=$0.00 equity=${equity:.2f}")
                    continue
                call_intrinsic = max(settle_mark - call_strike, 0)
                put_intrinsic = max(put_strike - settle_mark, 0)
                exit_pnl_raw = net_credit - (call_intrinsic + put_intrinsic)
                print(f"SETTLE-FALLBACK {expiry_date} spot={settle_mark:.2f} "
                      f"call_intr={call_intrinsic:.4f} put_intr={put_intrinsic:.4f}")
            exit_fee = 0.0

        total_fees_raw = entry_fee + exit_fee
        net_pnl_raw = exit_pnl_raw - total_fees_raw
        net_pnl = net_pnl_raw * multiplier
        total_fees = total_fees_raw * multiplier
        equity += net_pnl

        breach = " BREACH_EQUITY<=0" if equity <= 0 else ""
        print(f"{expiry_date} submode={exit_reason} day_pnl=${net_pnl:.2f} fees=${total_fees:.2f} "
              f"equity=${equity:.2f} stale_bars={stale_bars} entry_leg_skew={entry_leg_skew} "
              f"{sel_info}{breach}")


if __name__ == "__main__":
    run_backtest()
