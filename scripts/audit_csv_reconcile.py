"""
Standing reconciliation script: Delta CSV order history vs Audit Trade tab.

Compares, for S4 and S4V2 over the last N days:
  - Total charges (Trading Fees) USD
  - Total Realised PnL USD
  - Trade/row counts

CSV side: parses the raw Delta "Delta-TransactionLog-OrderHistory" export.
Audit side: calls the SAME _get_live_rows_audit() function the live
Trade Audit tab uses (inr_rate=1.0 forces raw USD output), so this
script can never drift out of sync with what the tab actually displays.

Usage:
    python3 scripts/audit_csv_reconcile.py
"""

import sys
import datetime
import csv

sys.path.insert(0, ".")
import dashboard.trade_audit_tab as tat

# ---- Config: map account label -> CSV file path ----
CSV_FILES = {
    "S4":   "/home/anildalabanjan933/Delta-TransactionLog-OrderHistory (11).csv",
    "S4V2": "/home/anildalabanjan933/Delta-TransactionLog-OrderHistory (12).csv",
}

WINDOW_DAYS = 30
PASS_THRESHOLD_USD = 5.0   # abs diff below this = PASS


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def parse_csv_totals(path):
    total_fees = 0.0
    total_pnl = 0.0
    row_count = 0
    filled_count = 0
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            row_count += 1
            total_fees += _f(row.get("Trading Fees"))
            total_pnl += _f(row.get("Realised P&L"))
            if str(row.get("Status", "")).strip().lower() == "closed":
                filled_count += 1
    return {
        "total_fees": total_fees,
        "total_pnl": total_pnl,
        "row_count": row_count,
        "filled_count": filled_count,
    }


def get_audit_totals(acc_label, from_date, to_date):
    fetch_fills_fn = tat._fetch_account_fills_cached_audit
    rows = tat._get_live_rows_audit(acc_label, from_date, to_date, fetch_fills_fn, inr_rate=1.0)
    total_charges = sum(r["charges"] for r in rows if r.get("charges") is not None)
    total_pnl = sum(r["pnl_usd"] for r in rows if r.get("pnl_usd") is not None)
    return {
        "total_charges": total_charges,
        "total_pnl": total_pnl,
        "trade_count": len(rows),
    }


def verdict(diff):
    return "PASS" if abs(diff) <= PASS_THRESHOLD_USD else "FAIL"


def main():
    today = datetime.datetime.utcnow().date()
    from_date = today - datetime.timedelta(days=WINDOW_DAYS)
    to_date = today

    print(f"Reconciliation window: {from_date} to {to_date} ({WINDOW_DAYS} days, UTC)")
    print(f"Pass threshold: ${PASS_THRESHOLD_USD:.2f} absolute diff\n")

    overall_pass = True

    for acc, csv_path in CSV_FILES.items():
        print(f"===== {acc} =====")
        try:
            csv_totals = parse_csv_totals(csv_path)
        except FileNotFoundError:
            print(f"  CSV NOT FOUND: {csv_path}")
            overall_pass = False
            continue

        audit_totals = get_audit_totals(acc, from_date, to_date)

        fee_diff = audit_totals["total_charges"] - csv_totals["total_fees"]
        pnl_diff = audit_totals["total_pnl"] - csv_totals["total_pnl"]

        fee_verdict = verdict(fee_diff)
        pnl_verdict = verdict(pnl_diff)
        if fee_verdict == "FAIL" or pnl_verdict == "FAIL":
            overall_pass = False

        print(f"  CSV rows: {csv_totals['row_count']} (closed: {csv_totals['filled_count']})")
        print(f"  Audit paired trades: {audit_totals['trade_count']}")
        print(f"  {'Metric':<15}{'CSV':>15}{'Audit':>15}{'Diff':>12}{'Verdict':>10}")
        print(f"  {'Total Fees $':<15}{csv_totals['total_fees']:>15.2f}{audit_totals['total_charges']:>15.2f}{fee_diff:>12.2f}{fee_verdict:>10}")
        print(f"  {'Total PnL $':<15}{csv_totals['total_pnl']:>15.2f}{audit_totals['total_pnl']:>15.2f}{pnl_diff:>12.2f}{pnl_verdict:>10}")
        print()

    print(f"OVERALL: {'PASS' if overall_pass else 'FAIL'}")
    sys.exit(0 if overall_pass else 1)


if __name__ == "__main__":
    main()
