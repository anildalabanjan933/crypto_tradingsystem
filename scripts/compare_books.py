import requests
from datetime import datetime

TESTNET_URL = "https://cdn-ind.testnet.deltaex.org"
PROD_URL = "https://api.india.delta.exchange"
SYMBOL = "BTCUSD"
DEPTH = 20
TEST_SIZE = 100


def fetch_book_and_ticker(base_url, symbol, depth):
    result = {"mark_price": None, "best_bid": None, "best_ask": None,
              "buy_levels": [], "sell_levels": [], "error": None}
    try:
        ticker_resp = requests.get(f"{base_url}/v2/tickers/{symbol}", timeout=(3, 10))
        ticker_resp.raise_for_status()
        ticker_json = ticker_resp.json()
        if ticker_json.get("success"):
            ticker_result = ticker_json.get("result", {})
            result["mark_price"] = ticker_result.get("mark_price")
            quotes = ticker_result.get("quotes", {})
            result["best_bid"] = quotes.get("best_bid")
            result["best_ask"] = quotes.get("best_ask")
        else:
            result["error"] = f"ticker call failed: {ticker_json}"
            return result
    except requests.exceptions.RequestException as e:
        result["error"] = f"ticker request error: {e}"
        return result

    try:
        book_resp = requests.get(
            f"{base_url}/v2/l2orderbook/{symbol}", params={"depth": depth}, timeout=(3, 10)
        )
        book_resp.raise_for_status()
        book_json = book_resp.json()
        if book_json.get("success"):
            book_result = book_json.get("result", {})
            result["buy_levels"] = book_result.get("buy", [])
            result["sell_levels"] = book_result.get("sell", [])
        else:
            result["error"] = f"orderbook call failed: {book_json}"
    except requests.exceptions.RequestException as e:
        result["error"] = f"orderbook request error: {e}"

    return result


def calc_slippage(levels, size, mark_price):
    if not levels or mark_price is None:
        return None

    remaining = size
    total_cost = 0.0
    filled = 0

    for level in levels:
        try:
            level_price = float(level.get("price"))
            level_size = int(level.get("size"))
        except (TypeError, ValueError):
            continue
        take = min(remaining, level_size)
        total_cost += take * level_price
        filled += take
        remaining -= take
        if remaining <= 0:
            break

    if filled == 0:
        return {"avg_price": None, "filled_size": 0, "requested_size": size,
                 "slippage_dollars": None, "slippage_pct": None, "fully_filled": False}

    avg_price = total_cost / filled
    mark = float(mark_price)
    slippage_dollars = avg_price - mark
    slippage_pct = (slippage_dollars / mark) * 100

    return {
        "avg_price": round(avg_price, 2),
        "filled_size": filled,
        "requested_size": size,
        "slippage_dollars": round(slippage_dollars, 2),
        "slippage_pct": round(slippage_pct, 4),
        "fully_filled": (filled >= size)
    }


def print_side_by_side(testnet_data, prod_data, symbol, depth, test_size):
    print(f"\n=== {symbol} Comparison | depth={depth} | {datetime.utcnow().isoformat()}Z ===\n")

    print(f"{'':25} {'TESTNET':>20} {'PRODUCTION':>20}")
    print(f"{'Mark Price':25} {str(testnet_data.get('mark_price')):>20} {str(prod_data.get('mark_price')):>20}")
    print(f"{'Best Bid':25} {str(testnet_data.get('best_bid')):>20} {str(prod_data.get('best_bid')):>20}")
    print(f"{'Best Ask':25} {str(testnet_data.get('best_ask')):>20} {str(prod_data.get('best_ask')):>20}")

    if testnet_data.get("error"):
        print(f"\nTESTNET ERROR: {testnet_data['error']}")
    if prod_data.get("error"):
        print(f"\nPRODUCTION ERROR: {prod_data['error']}")

    print("\n--- SELL SIDE (asks) ---")
    print(f"{'Level':>6} {'TESTNET price':>15} {'TESTNET size':>13} {'PROD price':>15} {'PROD size':>13}")
    max_sell_levels = max(len(testnet_data.get("sell_levels", [])), len(prod_data.get("sell_levels", [])))
    for i in range(max_sell_levels):
        t = testnet_data.get("sell_levels", [])[i] if i < len(testnet_data.get("sell_levels", [])) else {}
        p = prod_data.get("sell_levels", [])[i] if i < len(prod_data.get("sell_levels", [])) else {}
        print(f"{i+1:>6} {str(t.get('price','-')):>15} {str(t.get('size','-')):>13} {str(p.get('price','-')):>15} {str(p.get('size','-')):>13}")

    print("\n--- BUY SIDE (bids) ---")
    print(f"{'Level':>6} {'TESTNET price':>15} {'TESTNET size':>13} {'PROD price':>15} {'PROD size':>13}")
    max_buy_levels = max(len(testnet_data.get("buy_levels", [])), len(prod_data.get("buy_levels", [])))
    for i in range(max_buy_levels):
        t = testnet_data.get("buy_levels", [])[i] if i < len(testnet_data.get("buy_levels", [])) else {}
        p = prod_data.get("buy_levels", [])[i] if i < len(prod_data.get("buy_levels", [])) else {}
        print(f"{i+1:>6} {str(t.get('price','-')):>15} {str(t.get('size','-')):>13} {str(p.get('price','-')):>15} {str(p.get('size','-')):>13}")

    print(f"\n--- SLIPPAGE ESTIMATE for a {test_size}-lot order ---\n")

    testnet_buy_slip = calc_slippage(testnet_data.get("sell_levels", []), test_size, testnet_data.get("mark_price"))
    prod_buy_slip = calc_slippage(prod_data.get("sell_levels", []), test_size, prod_data.get("mark_price"))
    testnet_sell_slip = calc_slippage(testnet_data.get("buy_levels", []), test_size, testnet_data.get("mark_price"))
    prod_sell_slip = calc_slippage(prod_data.get("buy_levels", []), test_size, prod_data.get("mark_price"))

    def fmt_slip(label, slip):
        if slip is None:
            print(f"{label}: no data")
            return
        if slip["filled_size"] == 0:
            print(f"{label}: NO FILL POSSIBLE within depth={depth} (requested {slip['requested_size']}, filled 0)")
            return
        fill_note = "FULL FILL" if slip["fully_filled"] else f"PARTIAL FILL ({slip['filled_size']}/{slip['requested_size']})"
        print(f"{label}: avg_price=${slip['avg_price']} | slippage=${slip['slippage_dollars']} ({slip['slippage_pct']}%) | {fill_note}")

    print("If BUYING (eating the sell side / asks):")
    fmt_slip("  TESTNET   ", testnet_buy_slip)
    fmt_slip("  PRODUCTION", prod_buy_slip)

    print("\nIf SELLING (eating the buy side / bids):")
    fmt_slip("  TESTNET   ", testnet_sell_slip)
    fmt_slip("  PRODUCTION", prod_sell_slip)

    print()


if __name__ == "__main__":
    testnet_data = fetch_book_and_ticker(TESTNET_URL, SYMBOL, DEPTH)
    prod_data = fetch_book_and_ticker(PROD_URL, SYMBOL, DEPTH)
    print_side_by_side(testnet_data, prod_data, SYMBOL, DEPTH, TEST_SIZE)
