import sys, os, csv, datetime as dt
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()
import issue_tracker as it

TRADES_CSV = it.TRADES_CSV
BOTS = ["S4", "S4V2", "S4V3"]
from_date = dt.date(2026, 9, 8)
to_date = dt.date(2026, 10, 4)

# Build corrected gap lookup: (bot, entry_ts_str) -> new pnl_gap
corrections = {}
for bot in BOTS:
    bt_rows = it.get_bt_rows(bot, from_date, to_date)
    lv_rows = it.get_live_rows(bot, from_date, to_date)
    matched, _ = it.pair_bt_lv(bt_rows, lv_rows, bot)
    for bt, lv in matched:
        if lv is None:
            continue
        gap = round((bt["net_pnl_inr"] / it.INR_RATE) - (lv.get("pnl_usd", 0) - lv.get("charges", 0)), 2)
        corrections[(bot, str(bt["entry_ts_raw"]))] = gap

print(f"Computed {len(corrections)} corrected gap values across {BOTS}")

# Rewrite CSV, only updating bt_lv_pnl_gap_$ column where a correction exists
rows = []
with open(TRADES_CSV) as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for r in reader:
        key = (r.get("bot"), r.get("entry_ts"))
        if key in corrections:
            old_val = r["bt_lv_pnl_gap_$"]
            r["bt_lv_pnl_gap_$"] = corrections[key]
            if str(old_val) != str(corrections[key]):
                print(f"UPDATED {key}: {old_val} -> {corrections[key]}")
        rows.append(r)

with open(TRADES_CSV, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print("Backfill complete.")
