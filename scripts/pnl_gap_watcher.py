
import csv
import time
import os
from datetime import datetime, timezone

FILES = {
    "S4": "/home/anildalabanjan7/crypto_tradingsystem/logs/fill_prices_s4.csv",
    "S4V2": "/home/anildalabanjan7/crypto_tradingsystem/logs/fill_prices_s4v2.csv",
    "S4V3": "/home/anildalabanjan7/crypto_tradingsystem/logs/fill_prices_s4v3.csv",
}

LOG_FILE = "/home/anildalabanjan7/crypto_tradingsystem/logs/pnl_gap_watch.log"
SLIP_THRESHOLD = 50.0
CHECK_INTERVAL = 60

def log_flag(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)
    print(line, end="")

def safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def check_row(label, row):
    entry_ts = row.get("entry_ts", "")
    dir_ = row.get("dir", "")
    lv_entry = row.get("lv_entry", "")
    lv_exit = row.get("lv_exit", "")
    bt_entry = safe_float(row.get("bt_entry"))
    bt_exit = safe_float(row.get("bt_exit"))
    lv_entry_f = safe_float(lv_entry)
    lv_exit_f = safe_float(lv_exit)

    if lv_entry.strip().upper() == "PENDING":
        log_flag(f"{label} PENDING ENTRY | entry_ts={entry_ts} dir={dir_}")
    elif bt_entry is not None and lv_entry_f is not None:
        slip = abs(bt_entry - lv_entry_f)
        if slip > SLIP_THRESHOLD:
            log_flag(f"{label} HIGH ENTRY SLIP ${slip:.2f} | entry_ts={entry_ts} dir={dir_} bt_entry={bt_entry} lv_entry={lv_entry_f}")

    if lv_exit.strip().upper() == "PENDING":
        log_flag(f"{label} PENDING EXIT | entry_ts={entry_ts} dir={dir_}")
    elif bt_exit is not None and lv_exit_f is not None:
        slip = abs(bt_exit - lv_exit_f)
        if slip > SLIP_THRESHOLD:
            log_flag(f"{label} HIGH EXIT SLIP ${slip:.2f} | entry_ts={entry_ts} dir={dir_} bt_exit={bt_exit} lv_exit={lv_exit_f}")

def get_line_count(path):
    if not os.path.exists(path):
        return 0
    with open(path, "r") as f:
        return sum(1 for _ in f)

def read_new_rows(path, start_line):
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows[max(start_line - 1, 0):]

def main():
    log_flag("PNL GAP WATCHER STARTED")
    last_counts = {label: get_line_count(path) for label, path in FILES.items()}

    while True:
        for label, path in FILES.items():
            current_count = get_line_count(path)
            if current_count > last_counts[label]:
                new_rows = read_new_rows(path, last_counts[label])
                for row in new_rows:
                    check_row(label, row)
                last_counts[label] = current_count
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

