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





import hashlib
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
