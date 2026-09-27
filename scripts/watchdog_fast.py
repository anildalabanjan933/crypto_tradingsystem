import os
import time
import csv
import signal
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from engine.order_manager import OrderManager
from engine.telegram_alert import send_alert

MISMATCH_CRITICAL_SEC = 1200
HEALTH_FILE_STALE_SEC = 180

BOTS = [
    {"name": "S4",   "api_key": os.getenv("S4_API_KEY", ""),   "api_secret": os.getenv("S4_API_SECRET", ""),
     "log": "logs/live_trading_s4.log", "fill_csv": "logs/fill_prices_s4.csv"},
    {"name": "S4V2", "api_key": os.getenv("S4V2_API_KEY", ""), "api_secret": os.getenv("S4V2_API_SECRET", ""),
     "log": "logs/live_trading_s4v2.log", "fill_csv": "logs/fill_prices_s4v2.csv"},
    {"name": "S4V3", "api_key": os.getenv("S4V3_API_KEY", ""), "api_secret": os.getenv("S4V3_API_SECRET", ""),
     "log": "logs/live_trading_s4v3.log", "fill_csv": "logs/fill_prices_s4v3.csv"},
]

POLL_SECONDS = 30
OUT_CSV = "logs/watchdog_fast_events.csv"
HEARTBEAT_FILE = "logs/watchdog_fast_heartbeat.txt"
API_TIMEOUT_SEC = 10

_log_positions = {}
_mismatch_streak = {}

class TimeoutException(Exception):
    pass

def _timeout_handler(signum, frame):
    raise TimeoutException("API call exceeded timeout")

def call_with_timeout(func, timeout_sec, *args, **kwargs):
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_sec)
    try:
        return func(*args, **kwargs)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

def write_heartbeat():
    with open(HEARTBEAT_FILE, "w") as f:
        f.write(str(int(time.time())))

def ensure_csv_header():
    if not os.path.exists(OUT_CSV):
        with open(OUT_CSV, "w", newline="") as f:
            csv.writer(f).writerow(["detected_at_utc", "bot", "check_class", "detail"])

MAX_LOG_SIZE = 20 * 1024 * 1024

def log_event(bot_name, check_class, detail):
    if os.path.exists(OUT_CSV) and os.path.getsize(OUT_CSV) > MAX_LOG_SIZE:
        os.rename(OUT_CSV, OUT_CSV + ".1")
    now = datetime.now(timezone.utc).isoformat()
    with open(OUT_CSV, "a", newline="") as f:
        w = csv.writer(f)
        w.writerow([now, bot_name, check_class, detail])
        f.flush()
        os.fsync(f.fileno())
    print(f"[watchdog_fast] {check_class} | {bot_name} | {detail}")

# ---------- Class C: missed/skipped signal detection ----------
def check_missed_signals(bot):
    path = bot["log"]
    if not os.path.exists(path):
        return
    size = os.path.getsize(path)
    last_pos = _log_positions.get(path, size)
    if size < last_pos:
        last_pos = 0
    if size > last_pos:
        with open(path, "r", errors="ignore") as f:
            f.seek(last_pos)
            new_data = f.read()
        _log_positions[path] = size
        for line in new_data.splitlines():
            if "MISSED TRADE" in line:
                log_event(bot["name"], "C_MISSED_SIGNAL", line.strip()[:200])
                send_alert(f"WATCHDOG [{bot['name']}] Class C - MISSED TRADE detected:\n{line.strip()[:200]}")
    else:
        _log_positions[path] = size


# ---------- Class A: state desync (reads state_health JSON written by renko_state_engine.py) ----------
def check_state_desync(bot):
    fname = f"logs/state_health_{bot['name']}.json"
    if not os.path.exists(fname):
        return
    try:
        import json
        with open(fname, 'r') as f:
            data = json.load(f)
    except Exception as e:
        log_event(bot['name'], 'A_ERROR', f'failed to read {fname}: {e}')
        return

    now = time.time()
    written_at = data.get('written_at')
    if written_at is not None and (now - written_at) > HEALTH_FILE_STALE_SEC:
        log_event(bot['name'], 'A_HEALTHFILE_STALE', f"state_health file not updated in {now - written_at:.0f}s - engine may be dead")
        send_alert(f"WATCHDOG [{bot['name']}] Class A - state_health file STALE for {now - written_at:.0f}s, engine may be dead")
        return

    mismatch_since = data.get('mismatch_since')
    mismatch_count = data.get('mismatch_count', 0)
    if mismatch_since is not None:
        stale_sec = now - mismatch_since
        if stale_sec > MISMATCH_CRITICAL_SEC:
            detail = f"mismatch_since age={stale_sec:.0f}s (count={mismatch_count}) exceeds critical threshold {MISMATCH_CRITICAL_SEC}s - auto-resync may be failing"
            log_event(bot['name'], 'A_STATE_DESYNC', detail)
            send_alert(f"WATCHDOG [{bot['name']}] Class A - STATE DESYNC CRITICAL:\n{detail}")

# ---------- Class E: position mismatch vs believed state (fill_prices CSV) ----------
def _read_last_fill_row(fill_csv):
    if not os.path.exists(fill_csv):
        return None
    try:
        with open(fill_csv, "r") as f:
            rows = f.readlines()
        if not rows:
            return None
        return rows[-1].strip().split(",")
    except Exception:
        return None

def check_position_mismatch(bot):
    om = OrderManager(bot["api_key"], bot["api_secret"], testnet=True)
    try:
        pos = call_with_timeout(om.get_position, API_TIMEOUT_SEC)
    except TimeoutException:
        log_event(bot["name"], "E_ERROR", f"get_position() timed out after {API_TIMEOUT_SEC}s")
        return
    except Exception as e:
        log_event(bot["name"], "E_ERROR", f"get_position() failed: {e}")
        return

    if not pos.get("success"):
        log_event(bot["name"], "E_ERROR", f"get_position() returned success=False: {pos}")
        return

    exch_size = abs(pos.get("size", 0))
    exch_dir = (pos.get("direction") or "").strip().lower()

    last = _read_last_fill_row(bot["fill_csv"])
    if not last or len(last) < 4:
        _mismatch_streak[bot["name"]] = 0
        return

    csv_pending = last[1].strip().upper() == "PENDING"
    if not csv_pending:
        _mismatch_streak[bot["name"]] = 0
        return

    try:
        csv_dir = last[2].strip().lower()
        csv_size = abs(float(last[3])) if last[3] else 0
    except Exception:
        _mismatch_streak[bot["name"]] = 0
        return

    mismatch = (csv_dir != exch_dir) or (csv_size != exch_size)

    if mismatch:
        _mismatch_streak[bot["name"]] = _mismatch_streak.get(bot["name"], 0) + 1
        if _mismatch_streak[bot["name"]] >= 2:
            detail = f"CSV believed={csv_dir}/{csv_size} vs exchange={exch_dir}/{exch_size} (2 consecutive polls)"
            log_event(bot["name"], "E_POSITION_MISMATCH", detail)
            send_alert(f"WATCHDOG [{bot['name']}] Class E - POSITION MISMATCH (2 consecutive polls):\n{detail}")
    else:
        _mismatch_streak[bot["name"]] = 0

def main():
    ensure_csv_header()
    for bot in BOTS:
        if os.path.exists(bot["log"]):
            _log_positions[bot["log"]] = os.path.getsize(bot["log"])
    print(f"[watchdog_fast] started, {len(BOTS)} bots, poll={POLL_SECONDS}s")
    while True:
        write_heartbeat()
        for bot in BOTS:
            try:
                check_missed_signals(bot)
            except Exception as e:
                log_event(bot["name"], "C_ERROR", str(e))
            try:
                check_state_desync(bot)
            except Exception as e:
                log_event(bot["name"], "A_ERROR", str(e))
            try:
                check_position_mismatch(bot)
            except Exception as e:
                log_event(bot["name"], "E_ERROR", str(e))
            time.sleep(1)
        try:
            run_canary()
        except Exception as e:
            log_event("SYSTEM", "CANARY_ERROR", str(e))
        time.sleep(POLL_SECONDS)

def run_canary():
    try:
        with open("logs/canary_ping.txt", "w") as f:
            f.write(str(time.time()))
        time.sleep(5)
        if not os.path.exists("logs/canary_pong.txt"):
            log_event("SYSTEM", "CANARY_FAIL", "No response within 5s")
            return False
        with open("logs/canary_pong.txt") as f:
            pong_ts = float(f.read().strip())
        if time.time() - pong_ts > 10:
            log_event("SYSTEM", "CANARY_STALE", "Response too old")
            return False
        return True
    except Exception as e:
        log_event("SYSTEM", "CANARY_CHECK_FAILED", str(e))
        return False
if __name__ == "__main__":
    main()

import os, time

MAX_LOG_SIZE = 20 * 1024 * 1024
FAST_LOG = "logs/watchdog_fast_events.csv"

def _rotate_if_needed(path):
    if os.path.exists(path) and os.path.getsize(path) > MAX_LOG_SIZE:
        os.rename(path, path + ".1")


