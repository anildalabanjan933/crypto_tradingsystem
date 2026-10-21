import requests
import datetime

BASE = "https://api.india.delta.exchange/v2"
LOT_SIZE = 1
CONTRACT_VALUE = 0.001

print("Fetching all expired BTC options (one-time)...")
all_products = []
after_cursor = None
while True:
    params = {
        "contract_types": "call_options,put_options",
        "states": "expired",
        "underlying_asset_symbols": "BTC",
        "page_size": 500
    }
    if after_cursor:
        params["after"] = after_cursor
    r = requests.get(f"{BASE}/products", params=params, timeout=(5,20)).json()
    batch = r.get("result", [])
    if not batch:
        break
    all_products.extend(batch)
    after_cursor = r.get("meta", {}).get("after")
    if not after_cursor:
        break
print(f"Total expired BTC options fetched: {len(all_products)}")

print("Fetching live BTC options...")
live_products = []
after_cursor = None
while True:
    params = {
        "contract_types": "call_options,put_options",
        "states": "live",
        "underlying_asset_symbols": "BTC",
        "page_size": 500
    }
    if after_cursor:
        params["after"] = after_cursor
    r = requests.get(f"{BASE}/products", params=params, timeout=(5,20)).json()
    batch = r.get("result", [])
    if not batch:
        break
    live_products.extend(batch)
    after_cursor = r.get("meta", {}).get("after")
    if not after_cursor:
        break
print(f"Total live BTC options fetched: {len(live_products)}")

all_products.extend(live_products)

def get_candle_close(symbol, ts):
    r = requests.get(f"{BASE}/history/candles", params={
        "symbol": symbol, "resolution": "1m", "start": ts, "end": ts + 1800
    }, timeout=10).json()
    result = r.get("result", [])
    if result:
        return float(result[0]["close"])
    r2 = requests.get(f"{BASE}/history/candles", params={
        "symbol": f"MARK:{symbol}", "resolution": "1m", "start": ts, "end": ts + 1800
    }, timeout=10).json()
    result2 = r2.get("result", [])
    if result2:
        return float(result2[0]["close"])
    return None

def get_chain_for_expiry(expiry_ddmmyyyy):
    expiry_short = expiry_ddmmyyyy[0:2] + expiry_ddmmyyyy[3:5] + expiry_ddmmyyyy[-2:]
    return [p for p in all_products if p["symbol"].endswith(f"-{expiry_short}")]

def nearest_strike_symbol(chain, target, opt_type):
    candidates = [p for p in chain if p["contract_type"] == opt_type]
    if not candidates:
        return None
    best = min(candidates, key=lambda p: abs(float(p["strike_price"]) - target))
    return best["symbol"], float(best["strike_price"])

start_date = datetime.date(2025, 10, 17)
end_date = datetime.date(2026, 10, 9)

results = []
d = start_date
while d <= end_date:
    if d.weekday() == 4:
        expiry_date = d + datetime.timedelta(days=7)
        exit_date = d + datetime.timedelta(days=5)

        entry_dt = datetime.datetime(d.year, d.month, d.day, 9, 46, tzinfo=datetime.timezone.utc)
        exit_dt = datetime.datetime(exit_date.year, exit_date.month, exit_date.day, 9, 46, tzinfo=datetime.timezone.utc)

        entry_ts = int(entry_dt.timestamp())
        exit_ts = int(exit_dt.timestamp())

        expiry_api = expiry_date.strftime("%d-%m-%Y")
        chain = get_chain_for_expiry(expiry_api)

        if not chain:
            print(f"{d} SKIP no option chain for expiry {expiry_api}")
            d += datetime.timedelta(days=1)
            continue

        spot = get_candle_close("BTCUSD", entry_ts)
        if spot is None:
            print(f"{d} SKIP no spot price at entry")
            d += datetime.timedelta(days=1)
            continue

        sell_pe = nearest_strike_symbol(chain, spot - 4000, "put_options")
        buy_pe = nearest_strike_symbol(chain, spot - 1000, "put_options")
        sell_ce = nearest_strike_symbol(chain, spot + 4000, "call_options")
        buy_ce = nearest_strike_symbol(chain, spot + 1000, "call_options")

        if not all([sell_pe, buy_pe, sell_ce, buy_ce]):
            print(f"{d} SKIP missing strikes in chain")
            d += datetime.timedelta(days=1)
            continue

        sell_pe_sym, sell_pe_strike = sell_pe
        buy_pe_sym, buy_pe_strike = buy_pe
        sell_ce_sym, sell_ce_strike = sell_ce
        buy_ce_sym, buy_ce_strike = buy_ce

        legs = {
            "sell_pe": (sell_pe_sym, "sell"),
            "buy_pe": (buy_pe_sym, "buy"),
            "sell_ce": (sell_ce_sym, "sell"),
            "buy_ce": (buy_ce_sym, "buy"),
        }

        entry_prices = {}
        exit_prices = {}
        missing = False
        for leg, (sym, side) in legs.items():
            ep = get_candle_close(sym, entry_ts)
            xp = get_candle_close(sym, exit_ts)
            if ep is None or xp is None:
                missing = True
                break
            entry_prices[leg] = ep
            exit_prices[leg] = xp

        if missing:
            print(f"{d} SKIP missing candle data for one or more legs")
            d += datetime.timedelta(days=1)
            continue

        pnl_usd = 0.0
        for leg, (sym, side) in legs.items():
            ep = entry_prices[leg]
            xp = exit_prices[leg]
            if side == "sell":
                leg_pnl = (ep - xp) * LOT_SIZE * CONTRACT_VALUE
            else:
                leg_pnl = (xp - ep) * LOT_SIZE * CONTRACT_VALUE
            pnl_usd += leg_pnl

        results.append({
            "entry_date": str(d),
            "expiry": expiry_api,
            "spot": spot,
            "pnl": pnl_usd
        })

        print(f"{d} TRADE spot={spot:.0f} [{buy_pe_strike:.0f}P/{sell_pe_strike:.0f}P/{sell_ce_strike:.0f}C/{buy_ce_strike:.0f}C] PnL={pnl_usd:.2f}")

    d += datetime.timedelta(days=1)

if results:
    total_pnl = sum(r["pnl"] for r in results)
    avg_pnl = total_pnl / len(results)
    print(f"\nTotal trades: {len(results)}")
    print(f"Total PnL: {total_pnl:.2f}")
    print(f"Avg PnL/trade: {avg_pnl:.2f}")
else:
    print("No trades")
