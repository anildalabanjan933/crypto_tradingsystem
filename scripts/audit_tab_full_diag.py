"""
One-shot diagnosis: times every fetch path the audit tab uses for ALL STRATEGY view,
including the duplicate equity-curve fetch, across all 3 strategies.
Run: .venv/bin/python3 scripts/audit_tab_full_diag.py --range week
"""
import sys, os, time, argparse, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv()
from dashboard import trade_audit_tab as tat

p = argparse.ArgumentParser()
p.add_argument("--range", default="week", choices=["today", "2day", "week", "month"])
args = p.parse_args()

today = datetime.datetime.now(datetime.timezone.utc).date()
days_map = {"today": 0, "2day": 2, "week": 7, "month": 30}
from_date = today - datetime.timedelta(days=days_map[args.range])
to_date = today

eq_from = today.replace(day=1)
eq_to = today

print(f"=== FULL DIAG | range={args.range} table=[{from_date}..{to_date}] eq=[{eq_from}..{eq_to}] ===")

grand_total = 0.0
for strat in ["S4", "S4V2", "S4V3"]:
    t0 = time.time()
    lv_rows = tat._get_live_rows_audit(strat, from_date, to_date, tat._fetch_account_fills_cached_audit, 1.0)
    t1 = time.time()
    lv_open = tat._get_open_live_rows_audit(strat, from_date, to_date, tat._fetch_account_fills_cached_audit)
    t2 = time.time()
    eq_lv_rows = tat._get_live_rows_audit(strat, eq_from, eq_to, tat._fetch_account_fills_cached_audit, 1.0)
    t3 = time.time()
    eq_lv_open = tat._get_open_live_rows_audit(strat, eq_from, eq_to, tat._fetch_account_fills_cached_audit)
    t4 = time.time()
    strat_total = t4 - t0
    grand_total += strat_total
    print(f"[{strat}] table_closed={t1-t0:.2f}s table_open={t2-t1:.2f}s eq_closed(DUPLICATE)={t3-t2:.2f}s eq_open(DUPLICATE)={t4-t3:.2f}s | strat_total={strat_total:.2f}s")

print(f"=== GRAND TOTAL (serial, as dashboard does today) = {grand_total:.2f}s ===")
print("NOTE: eq_closed/eq_open above are DUPLICATE fetches of the same account data")
print("      already fetched for the table - this is the main fixable waste.")
