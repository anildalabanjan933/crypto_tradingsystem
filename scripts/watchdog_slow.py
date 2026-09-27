import os
import time
import csv
import subprocess
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from engine.telegram_alert import send_alert

BOTS = [
    {"name": "S4",   "script": "scripts/signal_replay_s4.py",   "log": "logs/live_trading_s4.log"},
    {"name": "S4V2", "script": "scripts/signal_replay_s4v2.py", "log": "logs/live_trading_s4v2.log"},
    {"name": "S4V3", "script": "scripts/signal_replay_s4v3.py", "log": "logs/live_trading_s4v3.log"},
]

POLL_SECONDS = 300
OUT_CSV = "logs/watchdog_slow_events.csv"
HEARTBEAT_FILE = "logs/watchdog_slow_heartbeat.txt"
LIQ_THRESHOLD = 5
LIQ_WINDOW_MIN = 60

_stale_alerted = {}
_liq_events = {}
_liq_log_positions = {}

def write_heartbeat():
    with open(HEARTBEAT_FILE, "w") as f:
        f.write(str(int(time.time())))

def ensure_csv_header():
    if not os.path.exists(OUT_CSV):
        with open(OUT_CSV, "w", newline="") as f:
            csv.writer(f).writerow(["detected_at_utc", "bot", "check_class", "detail"])

def log_event(bot_name, check_class, detail):
    now = datetime.now(timezone.utc).isoformat()
    with open(OUT_CSV, "a", newline="") as f:
        csv.writer(f).writerow([now, bot_name, check_class, detail])
    print(f"[watchdog_slow] {check_class} | {bot_name} | {detail}")

def get_python_pid(script_name):
    try:
        pids = subprocess.check_output(["pgrep", "-f", script_name]).decode().split()
    except subprocess.CalledProcessError:
        return None
    for pid in pids:
        try:
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip()
            if "python3" in comm:
                return int(pid)
        except Exception:
            continue
    return None

def get_process_start_epoch(pid):
    try:
        out = subprocess.check_output(["ps", "-o", "etimes=", "-p", str(pid)]).decode().strip()
        return time.time() - int(out)
    except Exception:
        return None

# ---------- Class B: stale code running (file modified after process start) ----------
def check_stale_code(bot):
    pid = get_python_pid(bot["script"])
    if pid is None:
        return  # not running - other watchdog covers restart
    proc_start = get_process_start_epoch(pid)
    if proc_start is None:
        return
    try:
        file_mtime = os.path.getmtime(bot["script"])
    except Exception:
        return
    key = f"{bot['name']}_{pid}"
    if file_mtime > proc_start:
        if _stale_alerted.get(key):
            return
        _stale_alerted[key] = True
        age_min = (time.time() - proc_start) / 60
        detail = f"{bot['script']} modified after process start - running {age_min:.0f}m on old code, needs restart"
        log_event(bot["name"], "B_STALE_CODE", detail)
        send_alert(f"WATCHDOG [{bot['name']}] Class B - STALE CODE:\n{detail}")
    else:
        _stale_alerted.pop(key, None)

# ---------- Class D: thin-liquidity IOC cancel frequency ----------
def check_liquidity_frequency(bot):
    path = bot["log"]
    if not os.path.exists(path):
        return
    size = os.path.getsize(path)
    last_pos = _liq_log_positions.get(path, size)
    if size < last_pos:
        last_pos = 0
    if size <= last_pos:
        _liq_log_positions[path] = size
        return
    with open(path, "r", errors="ignore") as f:
        f.seek(last_pos)
        new_data = f.read()
    _liq_log_positions[path] = size

    now = time.time()
    events = _liq_events.setdefault(bot["name"], [])
    for line in new_data.splitlines():
        if "order_size_not_available_in_orderbook" in line:
            events.append(now)

    cutoff = now - LIQ_WINDOW_MIN * 60
    events[:] = [t for t in events if t >= cutoff]

    if len(events) >= LIQ_THRESHOLD:
        detail = f"{len(events)} thin-liquidity IOC cancels in last {LIQ_WINDOW_MIN}m (threshold {LIQ_THRESHOLD})"
        log_event(bot["name"], "D_LIQUIDITY_FREQ", detail)
        send_alert(f"WATCHDOG [{bot['name']}] Class D - HIGH LIQUIDITY-FREQ:\n{detail}")
        events.clear()

def main():
    ensure_csv_header()
    for bot in BOTS:
        if os.path.exists(bot["log"]):
            _liq_log_positions[bot["log"]] = os.path.getsize(bot["log"])
    print(f"[watchdog_slow] started, {len(BOTS)} bots, poll={POLL_SECONDS}s")
    while True:
        write_heartbeat()
        for bot in BOTS:
            try:
                check_stale_code(bot)
            except Exception as e:
                log_event(bot["name"], "B_ERROR", str(e))
            try:
                check_liquidity_frequency(bot)
            except Exception as e:
                log_event(bot["name"], "D_ERROR", str(e))
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()

import subprocess, os, time

MAX_LOG_SIZE = 20 * 1024 * 1024  # 20MB
SLOW_LOG = "logs/watchdog_slow_events.csv"

def _rotate_if_needed(path):
    if os.path.exists(path) and os.path.getsize(path) > MAX_LOG_SIZE:
        os.rename(path, path + ".1")

def log_event(event_type, message, path=SLOW_LOG):
    _rotate_if_needed(path)
    with open(path, "a") as f:
        f.write(f"{time.time()},{event_type},{message}\n")
        f.flush()
        os.fsync(f.fileno())

def check_clock_drift():
    try:
        out = subprocess.run(['chronyc', 'tracking'], capture_output=True, text=True, timeout=5)
        for line in out.stdout.splitlines():
            if 'System time' in line:
                drift = float(line.split(':')[1].strip().split()[0])
                if drift > 2.0:
                    log_event("CLOCK_DRIFT", f"Drift {drift}s exceeds 2s threshold")
                return drift
    except Exception as e:
        log_event("CLOCK_DRIFT_CHECK_FAILED", str(e))
    return None

import requests

EXPECTED_LEVERAGE = {"S4": 4, "S4V2": 4, "S4V3": 4}
PRODUCT_ID_MAP = {"S4": 196, "S4V2": 196, "S4V3": 196}

def check_leverage_drift():
    for bot, expected in EXPECTED_LEVERAGE.items():
        pid = PRODUCT_ID_MAP.get(bot)
        if pid is None:
            log_event("LEVERAGE_CHECK_SKIPPED", f"{bot}: no product_id set")
            continue
        try:
            r = requests.get(f"https://api.india.delta.exchange/v2/products/{pid}/orders/leverage", timeout=5)
            live = int(float(r.json()["result"]["leverage"]))
            if live != expected:
                log_event("LEVERAGE_DRIFT", f"{bot} live={live} expected={expected}")
        except Exception as e:
            log_event("LEVERAGE_CHECK_FAILED", f"{bot}: {e}")

def check_env_drift():
    required = ["DELTA_API_KEY", "DELTA_API_SECRET", "PYTHONPATH"]
    for var in required:
        if not os.environ.get(var):
            log_event("ENV_DRIFT", f"Missing env var: {var}")
