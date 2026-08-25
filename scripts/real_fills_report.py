import hmac, hashlib, time, requests, csv, glob, sys
from datetime import datetime, timezone, timedelta

TF_MIN = {"s4": 120, "s4v2": 30}

def load_env(bot):
    env = {}
    with open(".env") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    if bot == "s4":
        return env.get("S4_API_KEY") or env.get("DELTA_API_KEY_S4") or env.get("API_KEY"), \
               env.get("S4_API_SECRET") or env.get("DELTA_API_SECRET_S4") or env.get("API_SECRET")
    else:
        return env.get("S4V2_API_KEY") or env.get("DELTA_API_KEY_S4V2"), \
               env.get("S4V2_API_SECRET") or env.get("DELTA_API_SECRET_S4V2")

def sign(secret, message):
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

def get_fills(api_key, api_secret, base_url, start_us, end_us):
    method, path, all_fills, after = "GET", "/v2/fills", [], None
    while True:
        qs_parts = [f"start_time={start_us}", f"end_time={end_us}", "page_size=100"]
        if after:
            qs_parts.append(f"after={after}")
        query_string = "?" + "&".join(qs_parts)
        timestamp = str(int(time.time()))
        signature = sign(api_secret, method + timestamp + path + query_string)
        headers = {"api-key": api_key, "timestamp": timestamp, "signature": signature,
                   "User-Agent": "python-verify-script", "Content-Type": "application/json"}
        r = requests.get(base_url + path + query_string, headers=headers, timeout=15)
        data = r.json()
        if not data.get("success"):
            print("API ERROR:", data); break
        all_fills.extend(data.get("result", []))
        after = data.get("meta", {}).get("after")
        if not after:
            break
    return all_fills

def aggregate_by_order(fills):
    """Group raw partial fills by order_id -> one synthetic fill per order
    (weighted avg price, summed size, earliest fill time as execution start)."""
    orders = {}
    for f in fills:
        oid = f["order_id"]
        size = float(f["size"])
        price = float(f["price"])
        if oid not in orders:
            orders[oid] = {"side": f["side"], "size": 0.0, "notional": 0.0,
                            "first_time": f["created_at"], "last_time": f["created_at"]}
        o = orders[oid]
        o["size"] += size
        o["notional"] += size * price
        if f["created_at"] < o["first_time"]:
            o["first_time"] = f["created_at"]
        if f["created_at"] > o["last_time"]:
            o["last_time"] = f["created_at"]
    agg = []
    for oid, o in orders.items():
        agg.append({
            "order_id": oid,
            "side": o["side"],
            "size": o["size"],
            "price": o["notional"] / o["size"] if o["size"] else 0.0,
            "created_at": o["first_time"],
        })
    return sorted(agg, key=lambda x: x["created_at"])

def reconstruct_trades(fills):
    """Build trade lifecycles from order-aggregated fills via running signed position."""
    fills = sorted(fills, key=lambda f: f["created_at"])
    trades = []
    pos = 0.0
    entry_notional = 0.0
    entry_size = 0.0
    entry_time = None
    for f in fills:
        side = f["side"]
        size = float(f["size"])
        price = float(f["price"])
        signed = size if side == "buy" else -size
        prev_pos = pos
        pos += signed

        if prev_pos == 0 and pos != 0:
            entry_time = f["created_at"]
            entry_notional = price * size
            entry_size = size
        elif prev_pos != 0 and pos == 0:
            avg_entry = entry_notional / entry_size if entry_size else price
            trades.append({
                "direction": "long" if prev_pos > 0 else "short",
                "entry_time": entry_time, "entry_price": round(avg_entry, 2),
                "exit_time": f["created_at"], "exit_price": price,
                "size": abs(prev_pos)
            })
            entry_time, entry_notional, entry_size = None, 0.0, 0.0
        elif prev_pos != 0 and pos != 0 and (prev_pos > 0) != (pos > 0):
            avg_entry = entry_notional / entry_size if entry_size else price
            trades.append({
                "direction": "long" if prev_pos > 0 else "short",
                "entry_time": entry_time, "entry_price": round(avg_entry, 2),
                "exit_time": f["created_at"], "exit_price": price,
                "size": abs(prev_pos)
            })
            entry_time = f["created_at"]
            entry_notional = price * abs(pos)
            entry_size = abs(pos)
        elif prev_pos != 0 and pos != 0 and (prev_pos > 0) == (pos > 0):
            entry_notional += price * size
            entry_size += size
        else:
            entry_time = f["created_at"]
            entry_notional = price * size
            entry_size = size
    return trades

BT_GLOB = {
    "s4": "output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv",
    "s4v2": "output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv",
}

def load_bt(bot, start_date):
    f = sorted(glob.glob(BT_GLOB[bot]))[-1]
    rows = []
    with open(f) as fh:
        for r in csv.DictReader(fh):
            if r["entry_datetime"] >= start_date:
                rows.append(r)
    return rows

def dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if "Z" in s else datetime.fromisoformat(s)

def main():
    start_date = sys.argv[1] if len(sys.argv) > 1 else "2026-08-21"
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.now(timezone.utc)
    start_us = int(start_dt.timestamp() * 1_000_000)
    end_us = int(end_dt.timestamp() * 1_000_000)
    base_url = "https://cdn-ind.testnet.deltaex.org"

    report = {}
    for bot in ["s4", "s4v2"]:
        api_key, api_secret = load_env(bot)
        raw_fills = get_fills(api_key, api_secret, base_url, start_us, end_us)
        agg_fills = aggregate_by_order(raw_fills)
        real_trades = reconstruct_trades(agg_fills)
        bt_rows = load_bt(bot, start_date)
        tf_sec = TF_MIN[bot] * 60

        for t in real_trades:
            date = t["entry_time"][:10]
            report.setdefault(date, {"s4": {"bt": 0, "lv": 0, "rows": []},
                                      "s4v2": {"bt": 0, "lv": 0, "rows": []}})
            report[date][bot]["lv"] += 1

        for r in bt_rows:
            date = r["entry_datetime"][:10]
            report.setdefault(date, {"s4": {"bt": 0, "lv": 0, "rows": []},
                                      "s4v2": {"bt": 0, "lv": 0, "rows": []}})
            report[date][bot]["bt"] += 1

        matched_lv = list(real_trades)
        for r in bt_rows:
            bt_entry_t = dt(r["entry_datetime"].replace("Z","")).replace(tzinfo=timezone.utc)
            bt_entry_close = bt_entry_t + timedelta(seconds=tf_sec)
            best, best_diff = None, None
            for lv in matched_lv:
                if lv["direction"] != r["direction"]:
                    continue
                lv_entry_t = dt(lv["entry_time"])
                diff = abs((lv_entry_t - bt_entry_t).total_seconds())
                if diff < 3*3600 and (best_diff is None or diff < best_diff):
                    best, best_diff = lv, diff
            date = r["entry_datetime"][:10]
            if best:
                matched_lv.remove(best)
                entry_delay = int((dt(best["entry_time"]) - bt_entry_t).total_seconds()) - tf_sec
                bt_xt = dt(r["exit_datetime"].replace("Z","")).replace(tzinfo=timezone.utc)
                bt_exit_close = bt_xt + timedelta(seconds=tf_sec)
                lv_xt = dt(best["exit_time"])
                exit_delay = int((lv_xt - bt_xt).total_seconds()) - tf_sec
                sign_ = 1 if r["direction"] == "long" else -1
                slip = round(((best["entry_price"]-float(r["entry_price"]))*(-sign_) +
                              (best["exit_price"]-float(r["exit_price"]))*sign_) * 100 * 0.001, 2)
                issues = []
                if abs(entry_delay) > 5: issues.append("ENTRY_DELAY")
                if abs(exit_delay) > 5: issues.append("EXIT_DELAY")
                if abs(slip) > 5: issues.append("SLIPPAGE")
                issue_str = ",".join(issues) if issues else "OK"
                report[date][bot]["rows"].append(
                    f"| {r['direction']} | {bt_entry_close.strftime('%H:%M')}/{r['entry_price']} vs {best['entry_time'][11:16]}/{best['entry_price']} "
                    f"| {bt_exit_close.strftime('%H:%M')}/{r['exit_price']} vs {best['exit_time'][11:16]}/{best['exit_price']} "
                    f"| {entry_delay}s | {exit_delay}s | ${slip} | {issue_str} |"
                )
            else:
                report[date][bot]["rows"].append(
                    f"| {r['direction']} | {bt_entry_close.strftime('%H:%M')}/{r['entry_price']} vs MISSED | - | - | - | - | MISSED_NO_LIVE_FILL |"
                )

    out_lines = [f"REAL DELTA FILLS-BASED REPORT: {start_date} to {end_dt.date()} (UTC)"]
    for date in sorted(report):
        out_lines.append(f"\n=== DATE: {date} ===")
        for bot in ["s4", "s4v2"]:
            b, l = report[date][bot]["bt"], report[date][bot]["lv"]
            out_lines.append(f"\n{bot.upper()} | BT trades: {b} | LIVE trades: {l}")
            if report[date][bot]["rows"]:
                out_lines.append("| direction | entry BT vs LV (time/price) | exit BT vs LV (time/price) | entry delay | exit delay | net slippage | issue |")
                out_lines.append("|---|---|---|---|---|---|---|")
                out_lines.extend(report[date][bot]["rows"])

    text = "\n".join(out_lines)
    print(text)
    with open("output/real_fills_report.txt", "w") as f:
        f.write(text)

if __name__ == "__main__":
    main()
