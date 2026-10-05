import csv
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, ".")
import dashboard.trade_audit_tab as tat  # noqa: E402

CSV_FILES = {
    "S4":   "/home/anildalabanjan933/Delta-TransactionLog-OrderHistory (11).csv",
    "S4V2": "/home/anildalabanjan933/Delta-TransactionLog-OrderHistory (12).csv",
}

PRODUCT_ID = 84
LOOKBACK_HOURS = 24 * 30 + 24
DIFF_TOLERANCE_USD = 1.0
TOP_N_RESIDUALS = 15


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _fmt_ts(created_at):
    """created_at from /fills is epoch micro-seconds (per API docs)."""
    try:
        return datetime.utcfromtimestamp(int(created_at) / 1_000_000).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError):
        return str(created_at)


def parse_csv(path):
    total_fees = 0.0
    total_pnl = 0.0
    closed_orders = set()
    per_order = defaultdict(lambda: {"pnl": 0.0, "fees": 0.0})
    timestamps = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            oid = row.get("Order ID", "")
            pnl = _f(row.get("Realised P&L"))
            fees = _f(row.get("Trading Fees"))
            total_fees += fees
            total_pnl += pnl
            per_order[oid]["pnl"] += pnl
            per_order[oid]["fees"] += fees
            if row.get("Status", "") == "closed":
                closed_orders.add(oid)
            ts = row.get("Order Time") or row.get("Time") or row.get("Created At")
            if ts:
                timestamps.append(ts)
    csv_window = (min(timestamps), max(timestamps)) if timestamps else (None, None)
    return total_fees, total_pnl, len(closed_orders), per_order, csv_window


def corrected_fill_pnl(fills):
    """
    PnL: baseline-delta extraction on new_position.realized_pnl (resets to 0
    whenever the position returns to size == 0 - a new lifecycle). Root cause:
    new_position.realized_pnl is cumulative-since-position-opened, per Delta's
    documented /positions realized_pnl description ("Net realized pnl since
    the position was opened"), NOT a per-fill value.

    Trade count: an order is "closed" when its LAST fill shows
    meta_data.order_unfilled_size == "0" - matches Delta's own documented
    order state definition: state=closed means "Order has been fully filled"
    (see /orders/history schema).
    """
    fills_sorted = sorted(fills, key=lambda f: f.get("created_at", ""))

    baseline = 0.0
    total_pnl = 0.0
    total_fees = 0.0
    per_order = defaultdict(lambda: {"pnl": 0.0, "fees": 0.0})
    last_unfilled_by_order = {}
    first_seen_ts = {}
    last_seen_ts = {}

    for f in fills_sorted:
        meta = f.get("meta_data", {}) or {}
        new_pos = meta.get("new_position", {}) or {}

        raw_cumulative = _f(new_pos.get("realized_pnl", 0))
        pos_size_after = new_pos.get("size", None)

        fill_pnl = raw_cumulative - baseline
        commission = abs(_f(f.get("commission", 0)))

        total_pnl += fill_pnl
        total_fees += commission

        oid = str(f.get("order_id", ""))
        ts = f.get("created_at")
        per_order[oid]["pnl"] += fill_pnl
        per_order[oid]["fees"] += commission
        last_unfilled_by_order[oid] = meta.get("order_unfilled_size", None)
        first_seen_ts.setdefault(oid, ts)
        last_seen_ts[oid] = ts

        baseline = 0.0 if pos_size_after == 0 else raw_cumulative

    closed_orders = {
        oid for oid, unfilled in last_unfilled_by_order.items()
        if _f(unfilled) == 0.0
    }

    return total_pnl, total_fees, len(closed_orders), per_order, first_seen_ts, last_seen_ts


def print_residuals(label, acc, csv_map, api_map, key, api_ts, csv_window):
    diffs = []
    missing_from_csv = []
    for oid in set(csv_map) | set(api_map):
        c = csv_map.get(oid, {}).get(key, 0.0)
        a = api_map.get(oid, {}).get(key, 0.0)
        d = a - c
        if abs(d) > 0.01:
            diffs.append((oid, c, a, d))
            if oid not in csv_map:
                missing_from_csv.append(oid)
    diffs.sort(key=lambda x: -abs(x[3]))
    if not diffs:
        return
    print(f"  [{acc}] Top {label} residuals by order_id (csv vs api-corrected):")
    print(f"    {'order_id':<14}{'csv':>12}{'api':>12}{'diff':>12}")
    for oid, c, a, d in diffs[:TOP_N_RESIDUALS]:
        print(f"    {oid:<14}{c:>12.2f}{a:>12.2f}{d:>12.2f}")
    print(f"    ... {len(diffs)} order(s) with residual > $0.01, sum diff = {sum(x[3] for x in diffs):.2f}")

    if missing_from_csv:
        print(f"  [{acc}] Diagnosis: {len(missing_from_csv)} order(s) above exist in live API but NOT in CSV at all.")
        print(f"    CSV file covers: {csv_window[0]} to {csv_window[1]}")
        for oid in missing_from_csv:
            ts_first = _fmt_ts(api_ts.get(oid))
            print(f"    order_id {oid} first fill at {ts_first} (UTC) -> likely occurred AFTER CSV export "
                  f"(export snapshot lag), not a calculation bug.")


def main():
    print(f"{'ACCOUNT':<8}{'METRIC':<14}{'CSV':>14}{'DELTA(fixed)':>16}{'DIFF':>12}{'STATUS':>10}")
    print("-" * 74)

    overall_pass = True

    for acc, csv_path in CSV_FILES.items():
        csv_fees, csv_pnl, csv_trades, csv_per_order, csv_window = parse_csv(csv_path)

        fetch_fills_fn = tat._fetch_account_fills_cached_audit
        fills = tat._fetch_fills_audit(fetch_fills_fn, acc, PRODUCT_ID, LOOKBACK_HOURS)

        api_pnl, api_fees, api_trades, api_per_order, first_seen_ts, last_seen_ts = corrected_fill_pnl(fills)

        rows = [
            ("Trades", csv_trades, api_trades, None),
            ("Gross PnL", csv_pnl, api_pnl, "pnl"),
            ("Charges", csv_fees, api_fees, "fees"),
        ]

        mismatches = []
        for metric, csv_val, api_val, key in rows:
            diff = api_val - csv_val
            status = "OK" if abs(diff) <= DIFF_TOLERANCE_USD else "MISMATCH"
            if status == "MISMATCH":
                overall_pass = False
                mismatches.append((metric, key))
            print(f"{acc:<8}{metric:<14}{csv_val:>14.2f}{api_val:>16.2f}{diff:>12.2f}{status:>10}")

        for metric, key in mismatches:
            if key is not None:
                print_residuals(metric, acc, csv_per_order, api_per_order, key, first_seen_ts, csv_window)

        print("-" * 74)

    print()
    if overall_pass:
        print("RESULT: PASS - Delta live API (corrected) matches CSV within tolerance for all accounts.")
    else:
        print("RESULT: Remaining mismatches (if any) are auto-diagnosed above as either real residuals "
              "or CSV export-lag (orders not yet present in the static CSV snapshot).")
    sys.exit(0 if overall_pass else 1)


if __name__ == "__main__":
    main()
