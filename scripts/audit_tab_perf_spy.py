"""
Profiles audit tab fetch calls to pinpoint slow path.
Run: .venv/bin/python3 scripts/audit_tab_perf_spy.py --range week
"""
import sys, os, time, argparse, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv()
from dashboard import trade_audit_tab as tat

p = argparse.ArgumentParser()
p.add_argument("--range", default="week", choices=["today", "2day", "week", "month"])
args = p.parse_args()

today = datetime.datetime.utcnow().date()
if args.range == "today":
    from_date = today
elif args.range == "2day":
    from_date = today - datetime.timedelta(days=2)
elif args.range == "week":
    from_date = today - datetime.timedelta(days=7)
else:
    from_date = today - datetime.timedelta(days=30)
to_date = today

print(f"=== PERF SPY | range={args.range} from={from_date} to={to_date} ===")

for strat in ["S4", "S4V2", "S4V3"]:
    acc = strat
    window_hours = max(24, (today - from_date).days * 24 + 48)
    t0 = time.time()
    fills = tat._fetch_account_fills_cached_audit(acc, 84, window_hours)
    t1 = time.time()
    orders = tat._fetch_account_orders_history_cached_audit(acc, 84, window_hours)
    t2 = time.time()
    print(f"[{strat}] window_hours={window_hours} fills_fetch={t1-t0:.2f}s ({len(fills)} rows) orders_fetch={t2-t1:.2f}s ({len(orders)} rows) TOTAL={t2-t0:.2f}s")

print("=== DONE ===")
