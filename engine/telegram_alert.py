import os
import requests
import logging

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

def send_alert(message: str) -> bool:
    """Send Telegram alert message."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("[TELEGRAM] Token or Chat ID not configured")
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
