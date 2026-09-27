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



