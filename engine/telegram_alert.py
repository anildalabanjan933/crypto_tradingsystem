import os
import json
import time
import requests
import logging
from dotenv import load_dotenv

load_dotenv(dotenv_path="/home/anildalabanjan933/crypto_trading_system/.env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

_RATE_STATE_FILE = "/home/anildalabanjan933/crypto_trading_system/logs/alert_rate_state.json"
_RATE_MAX_COUNT  = 1
_RATE_WINDOW_SEC = 1800  # 30 minutes

def _rate_limited(message: str) -> bool:
    """Return True if this message-type has already hit the alert cap in the current window."""
    try:
        key = message.strip().split("\n")[0][:60]
        now = time.time()
        state = {}
        if os.path.exists(_RATE_STATE_FILE):
            try:
                state = json.load(open(_RATE_STATE_FILE))
            except Exception:
                state = {}
        entries = [t for t in state.get(key, []) if now - t < _RATE_WINDOW_SEC]
        if len(entries) >= _RATE_MAX_COUNT:
            state[key] = entries
            json.dump(state, open(_RATE_STATE_FILE, "w"))
            return True
        entries.append(now)
        state[key] = entries
        json.dump(state, open(_RATE_STATE_FILE, "w"))
        return False
    except Exception:
        return False  # never block alert on rate-limit internal error

def send_alert(message: str) -> bool:
    """Send Telegram alert message."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("[TELEGRAM] Token or Chat ID not configured")
        return False
    if _rate_limited(message):
        logging.info(f"[TELEGRAM] Rate-limited (max {_RATE_MAX_COUNT}/{_RATE_WINDOW_SEC}s) - suppressed: {message[:50]}")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code == 200:
            logging.info(f"[TELEGRAM] Alert sent: {message[:50]}")
            return True
        else:
            logging.warning(f"[TELEGRAM] Failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logging.warning(f"[TELEGRAM] Exception: {e}")
        return False
