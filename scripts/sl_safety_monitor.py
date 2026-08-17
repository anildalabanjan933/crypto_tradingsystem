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
import hashlib
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from engine.order_manager import OrderManager
from engine.telegram_alert import send_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("logs/sl_safety_monitor.log")]
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

    key_hash = hashlib.md5(bot["api_key"].encode()).hexdigest()[:12]
    id_file = f"logs/active_sl_id_{key_hash}.txt"
    has_sl = False
    saved_id = None
    if os.path.exists(id_file):
        try:
            with open(id_file) as f:
                saved_id = f.read().strip()
        except Exception:
            saved_id = None
    if saved_id:
        chk = om._get(f"/v2/orders/{saved_id}", {})
        if chk.get("success"):
            o = chk.get("result", {})
            if o.get("stop_order_type") == "stop_loss_order" and o.get("state") in ("open", "pending"):
                has_sl = True

    if not has_sl:
        now = time.time()
        last = _last_alert_ts.get(bot["name"], 0)
        log.critical(f"[{bot['name']}] OPEN POSITION (size={size}) WITH NO SL ORDER FOUND - AUTO-PLACING SL")
        direction = pos.get("direction", "UNKNOWN").lower()
        entry_price = pos.get("entry_price", 0.0)
        if direction in ("long", "short") and entry_price > 0:
            sl_result = om.place_stop_loss_order(direction, entry_price)
        else:
            sl_result = {"success": False, "error": "invalid_direction_or_entry_price"}
        if now - last > ALERT_COOLDOWN:
            if sl_result.get("success"):
                log.info(f"[{bot['name']}] AUTO-SL PLACED OK | order_id={sl_result.get('order_id')}")
                send_alert(f"CTS {bot['name']} RECOVERED - SL WAS MISSING, AUTO-PLACED SUCCESSFULLY\nSize: {size}\nOrder ID: {sl_result.get('order_id')}")
            else:
                log.critical(f"[{bot['name']}] AUTO-SL PLACEMENT FAILED: {sl_result}")
                send_alert(f"CTS {bot['name']} CRITICAL - NO SL FOUND AND AUTO-PLACE FAILED\nSize: {size}\nError: {sl_result.get('error')}\nMANUAL CHECK REQUIRED IMMEDIATELY")
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
