#!/usr/bin/env python3
"""Standalone orphan-row detector. Run manually, NOT auto-wired to bots/watchdog yet."""
import csv, os, sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.expanduser("~/crypto_trading_system"))
from engine.order_manager import OrderManager

BOTS = {
    "S4":   ("logs/signals_s4.csv",   "S4_API_KEY",   "S4_API_SECRET",   120),
    "S4V2": ("logs/signals_s4v2.csv", "S4V2_API_KEY", "S4V2_API_SECRET", 30),
    "S4V3": ("logs/signals_s4v3.csv", "S4V3_API_KEY", "S4V3_API_SECRET", 240),
}
BUFFER_MIN = 60  # safety margin over tf before flagging

now = datetime.utcnow()
for name, (path, kkey, skey, tf) in BOTS.items():
    if not os.path.exists(path):
        print(f"{name}: no signals csv, skip"); continue
    with open(path) as f:
        rows = list(csv.reader(f))
    if not rows:
        print(f"{name}: empty csv, skip"); continue
    last = rows[-1]
    entry_ts, exit_ts, direction = last[0], last[1], last[2]
    if exit_ts != "PENDING":
        print(f"{name}: last row not PENDING, skip"); continue
    entry_dt = datetime.fromisoformat(entry_ts)
    elapsed_min = (now - entry_dt).total_seconds() / 60
    if elapsed_min <= tf + BUFFER_MIN:
        print(f"{name}: PENDING but within tf+buffer ({elapsed_min:.0f}min), legit, skip")
        continue
    k = os.getenv(kkey); s = os.getenv(skey)
    if not k or not s:
        print(f"{name}: no API keys, skip"); continue
    om = OrderManager(k, s, testnet=True)
    pos = om.get_position()
    ex_dir = pos.get("direction", "FLAT")
    csv_dir = direction.upper()
    if ex_dir == csv_dir:
        print(f"{name}: elapsed {elapsed_min:.0f}min but exchange matches CSV ({ex_dir}), legit open, skip")
        continue
    print(f"{name}: ORPHAN CONFIRMED - CSV={csv_dir} exchange={ex_dir} elapsed={elapsed_min:.0f}min")
    print(f"  -> would close row: entry={entry_ts} exit={now.isoformat()} exit_price=UNKNOWN(manual fill needed)")
    print(f"  ACTION REQUIRED: manually confirm+patch this row, same as prior fixes (04/05-Sep)")
