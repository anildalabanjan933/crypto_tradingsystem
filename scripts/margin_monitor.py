"""
scripts/margin_monitor.py
Standalone margin/balance monitor - READ ONLY.
Does NOT place, close, or modify any order or position.
Checks each subaccount's USD available_balance every CHECK_INTERVAL_SEC
and sends a rate-limited Telegram alert if balance falls below its
configured safe threshold.
"""
import os
import time
import hmac
import hashlib
import requests
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(dotenv_path="/home/anildalabanjan933/crypto_trading_system/.env")

import sys
sys.path.insert(0, "/home/anildalabanjan933/crypto_trading_system")
from engine.telegram_alert import send_alert

logging.basicConfig(
    filename="/home/anildalabanjan933/crypto_trading_system/logs/margin_monitor.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("margin_monitor")

BASE_URL = "https://cdn-ind.testnet.deltaex.org"
CHECK_INTERVAL_SEC = 1800  # 30 minutes

# label -> (api_key env var, api_secret env var, safe_threshold_usd)
# safe_threshold_usd = (backtest MAX DRAWDOWN, not single-trade loss) x 3
# EDIT THESE THRESHOLDS MANUALLY based on each strategy's actual backtest max drawdown
ACCOUNTS = {
    "S4":   ("S4_API_KEY",   "S4_API_SECRET",   612.0),
    "S4V2": ("S4V2_API_KEY", "S4V2_API_SECRET", 3075.0),
    "TM1":  ("TESTMEMBER1_S4V2_API_KEY", "TESTMEMBER1_S4V2_API_SECRET", 3075.0),
}

ALERT_COOLDOWN_SEC = 4 * 3600  # 4 hours - avoid repeat spam while still below threshold
_last_alert_ts = {}   # label -> last time a LOW MARGIN alert was sent
_was_below = {}        # label -> bool, was balance below threshold last check

def get_usd_balance(api_key, api_secret):
    path = "/v2/wallet/balances"
    timestamp = str(int(time.time()))
    message = "GET" + timestamp + path
    signature = hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "api-key": api_key,
        "timestamp": timestamp,
        "signature": signature,
        "User-Agent": "python-rest-client"
    }
    resp = requests.get(BASE_URL + path, headers=headers, timeout=(3, 15))
    data = resp.json()
    if not data.get("success"):
        return None, None, data.get("error")
    for w in data.get("result", []):
        if w.get("asset_symbol") == "USD":
            return float(w.get("balance", 0)), float(w.get("available_balance", 0)), None
    return None, None, "USD wallet not found"

def check_all():
    now = time.time()
    for label, (key_env, secret_env, threshold) in ACCOUNTS.items():
        api_key = os.getenv(key_env, "")
        api_secret = os.getenv(secret_env, "")
        if not api_key or not api_secret:
            log.warning(f"[{label}] API key/secret not configured - skipping")
            continue
        bal, avail_bal, err = get_usd_balance(api_key, api_secret)
        if err:
            log.warning(f"[{label}] Balance check failed: {err}")
            continue
        log.info(f"[{label}] balance(equity)=${bal:.2f} | available_balance=${avail_bal:.2f} | threshold=${threshold:.2f}")
        if bal < threshold:
            last_sent = _last_alert_ts.get(label, 0)
            if now - last_sent >= ALERT_COOLDOWN_SEC:
                send_alert(
                    f"LOW MARGIN WARNING - {label}\n"
                    f"Available balance: ${bal:.2f}\n"
                    f"Safe threshold: ${threshold:.2f}\n"
                    f"Action: Top up this subaccount before next signal fires\n"
                    f"(repeats every {ALERT_COOLDOWN_SEC//3600}h while still low, not spam)"
                )
                _last_alert_ts[label] = now
            _was_below[label] = True
        else:
            if _was_below.get(label):
                send_alert(
                    f"MARGIN RECOVERED - {label}\n"
                    f"Available balance: ${bal:.2f} (back above ${threshold:.2f})"
                )
            _was_below[label] = False

if __name__ == "__main__":
    log.info("[STARTUP] Margin monitor started (read-only, no order actions)")
    while True:
        try:
            check_all()
        except Exception as e:
            log.error(f"[ERROR] {e}", exc_info=True)
        time.sleep(CHECK_INTERVAL_SEC)
