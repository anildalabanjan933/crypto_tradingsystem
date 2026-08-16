"""
SL Safety Monitor - Phase 1 (monitor-only, no auto-action)
Checks every 60s: does every OPEN position have a live SL order
on the exchange? If not, sends a critical Telegram alert.
Does NOT touch signal_replay_s4.py / s4v2.py / renko_state_engine.py
or any entry/exit/signal logic - read-only checks only.
"""
import os
import sys
import time
import logging
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from engine.order_manager import OrderManager
from engine.telegram_alert import send_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("logs/sl_safety_monitor.log"), logging.StreamHandler()]
)
log = logging.getLogger("sl_monitor")

BOTS = [
    {"name": "S4",   "api_key": os.getenv("S4_API_KEY", ""),   "api_secret": os.getenv("S4_API_SECRET", "")},
    {"name": "S4V2", "api_key": os.getenv("S4V2_API_KEY", ""), "api_secret": os.getenv("S4V2_API_SECRET", "")},
]

CHECK_INTERVAL = 60
_last_alert_ts = {}
ALERT_COOLDOWN = 300  # don't spam same bot alert more than once per 5 min

def check_bot(bot):
    om = OrderManager(bot["api_key"], bot["api_secret"], testnet=True)
    pos = om.get_position()
    if not pos.get("success"):
        log.warning(f"[{bot['name']}] Could not fetch position: {pos}")
        return
    size = pos.get("size", 0)
    if size == 0:
        return  # flat, nothing to check

    resp = om._get("/v2/orders", {
        "product_ids": str(om.PRODUCT_ID),
        "states": "open,pending",
        "order_types": "stop_market,stop_limit,all_stop"
    })
    has_sl = False
    if resp.get("success"):
        orders = resp.get("result", [])
        has_sl = any(o.get("stop_order_type") == "stop_loss_order" for o in orders)

    if not has_sl:
        now = time.time()
        last = _last_alert_ts.get(bot["name"], 0)
        if now - last > ALERT_COOLDOWN:
            log.critical(f"[{bot['name']}] OPEN POSITION (size={size}) WITH NO SL ORDER FOUND")
            send_alert(f"CTS {bot['name']} CRITICAL - NO SL FOUND ON OPEN POSITION\nSize: {size}\nManual check required immediately")
            _last_alert_ts[bot["name"]] = now
    else:
        log.info(f"[{bot['name']}] position size={size} - SL confirmed present")

def main():
    log.info("SL Safety Monitor started - monitor-only, no auto-action")
    while True:
        for bot in BOTS:
            try:
                check_bot(bot)
            except Exception as e:
                log.error(f"[{bot['name']}] Check failed: {e}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
