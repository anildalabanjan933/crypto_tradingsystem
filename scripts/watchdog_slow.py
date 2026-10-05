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

MAX_LOG_SIZE = 20 * 1024 * 1024

_log_dedup_state = {}  # (bot_name, check_class) -> {"first_ts": float, "count": int, "last_write_ts": float}
_DEDUP_WINDOW_SEC = 300  # fold repeats of same signature into one row per 5min

def log_event(bot_name, check_class, detail):
    if os.path.exists(OUT_CSV) and os.path.getsize(OUT_CSV) > MAX_LOG_SIZE:
        os.rename(OUT_CSV, OUT_CSV + ".1")
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    now_ts = now_dt.timestamp()

    key = (bot_name, check_class)
    state = _log_dedup_state.get(key)
    if state and (now_ts - state["last_write_ts"]) < _DEDUP_WINDOW_SEC:
        state["count"] += 1
        return

    count_suffix = ""
    if state and state["count"] > 0:
        count_suffix = f" (suppressed {state['count']} repeat(s) in prior {_DEDUP_WINDOW_SEC}s)"

    with open(OUT_CSV, "a", newline="") as f:
        w = csv.writer(f)
        w.writerow([now, bot_name, check_class, detail + count_suffix])
        f.flush()
        os.fsync(f.fileno())
    print(f"[watchdog_slow] {check_class} | {bot_name} | {detail}{count_suffix}")
    _log_dedup_state[key] = {"first_ts": now_ts, "count": 0, "last_write_ts": now_ts}

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
        try:
            check_clock_drift()
        except Exception as e:
            log_event("SYSTEM", "CLOCK_DRIFT_ERROR", str(e))
        try:
            check_leverage_drift()
        except Exception as e:
            log_event("SYSTEM", "LEVERAGE_DRIFT_ERROR", str(e))
        try:
            check_env_drift()
        except Exception as e:
            log_event("SYSTEM", "ENV_DRIFT_ERROR", str(e))
        try:
            check_env_hash_drift()
        except Exception as e:
            log_event("SYSTEM", "ENV_HASH_ERROR", str(e))
        time.sleep(POLL_SECONDS)

def check_clock_drift():
    try:
        out = subprocess.run(['chronyc', 'tracking'], capture_output=True, text=True, timeout=5)
        for line in out.stdout.splitlines():
            if 'System time' in line:
                drift = float(line.split(':')[1].strip().split()[0])
                if drift > 2.0:
                    log_event("SYSTEM", "CLOCK_DRIFT", f"Drift {drift}s exceeds 2s threshold")
                return drift
    except Exception as e:
        log_event("SYSTEM", "CLOCK_DRIFT_CHECK_FAILED", str(e))
    return None

import requests, hashlib, hmac

EXPECTED_LEVERAGE = {"S4": 4, "S4V2": 4, "S4V3": 4}
PRODUCT_ID_MAP = {"S4": 84, "S4V2": 84, "S4V3": 84}
TESTNET_BASE_URL = "https://cdn-ind.testnet.deltaex.org"
PORTFOLIO_MODE_BOTS = {"S4V3"}  # accounts on Portfolio margin mode - fixed leverage check not applicable

def _gen_sig(secret, message):
    return hmac.new(bytes(secret, 'utf-8'), bytes(message, 'utf-8'), hashlib.sha256).hexdigest()

def check_leverage_drift():
    key_map = {
        "S4": (os.environ.get("S4_API_KEY", ""), os.environ.get("S4_API_SECRET", "")),
        "S4V2": (os.environ.get("S4V2_API_KEY", ""), os.environ.get("S4V2_API_SECRET", "")),
        "S4V3": (os.environ.get("S4V3_API_KEY", ""), os.environ.get("S4V3_API_SECRET", "")),
    }
    for bot, expected in EXPECTED_LEVERAGE.items():
        if bot in PORTFOLIO_MODE_BOTS:
            log_event("SYSTEM", "LEVERAGE_CHECK_SKIPPED", f"{bot}: portfolio margin mode - fixed leverage check not applicable")
            continue
        pid = PRODUCT_ID_MAP.get(bot)
        api_key, api_secret = key_map.get(bot, ("", ""))
        if pid is None or not api_key or not api_secret:
            log_event("SYSTEM", "LEVERAGE_CHECK_SKIPPED", f"{bot}: missing product_id or credentials")
            continue
        try:
            method = "GET"
            timestamp = str(int(time.time()))
            path = f"/v2/products/{pid}/orders/leverage"
            sig_data = method + timestamp + path
            signature = _gen_sig(api_secret, sig_data)
            headers = {"api-key": api_key, "timestamp": timestamp, "signature": signature}
            r = requests.get(TESTNET_BASE_URL + path, headers=headers, timeout=5)
            data = r.json()
            if not data.get("success"):
                log_event("SYSTEM", "LEVERAGE_CHECK_FAILED", f"{bot}: {data.get('error')}")
                continue
            live = int(float(data["result"]["leverage"]))
            if live != expected:
                log_event("SYSTEM", "LEVERAGE_DRIFT", f"{bot} live={live} expected={expected}")
        except Exception as e:
            log_event("SYSTEM", "LEVERAGE_CHECK_FAILED", f"{bot}: {e}")

def check_env_drift():
    required = ["S4_API_KEY", "S4_API_SECRET", "S4V2_API_KEY", "S4V2_API_SECRET", "S4V3_API_KEY", "S4V3_API_SECRET", "PYTHONPATH"]
    for var in required:
        if not os.environ.get(var):
            log_event("SYSTEM", "ENV_DRIFT", f"Missing env var: {var}")

import subprocess, time
import hashlib

MAX_LOG_SIZE = 20 * 1024 * 1024  # 20MB
SLOW_LOG = "logs/watchdog_slow_events.csv"

# UNUSED - dead code, never called. Do not call, do not delete without care (see 27-Sep incident).
def _rotate_if_needed(path):
    if os.path.exists(path) and os.path.getsize(path) > MAX_LOG_SIZE:
        os.rename(path, path + ".1")

_env_hash_last = None

def check_env_hash_drift():
    global _env_hash_last
    try:
        with open(".env", "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        log_event("SYSTEM", "ENV_HASH_CHECK_ERROR", str(e))
        return
    if _env_hash_last is not None and h != _env_hash_last:
        log_event("SYSTEM", "ENV_FILE_CHANGED", f".env hash changed {_env_hash_last[:8]}->{h[:8]}")
    _env_hash_last = h

if __name__ == "__main__":
    main()
