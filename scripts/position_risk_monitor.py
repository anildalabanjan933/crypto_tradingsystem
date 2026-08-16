"""
Position Risk Monitor - Phase 2 Task 2 (monitor-only, no auto-action)
Checks every 30s: for each OPEN position, how close is mark price to
liquidation_price, and how thin is available_balance vs required margin?
Sends critical Telegram alert if thresholds breached. Does NOT touch
signal_replay_s4.py / s4v2.py / renko_state_engine.py or any entry/exit/
signal logic - read-only checks only, same pattern as sl_safety_monitor.py.

THRESHOLDS BELOW ARE PLACEHOLDERS (per Claude's design note, 16-Aug-2026) -
no confirmed real liquidation event data was available to calibrate these.
Revisit once real margin-ratio data near a genuine liquidation is available.
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
    handlers=[logging.FileHandler("logs/position_risk_monitor.log"), logging.StreamHandler()]
)
log = logging.getLogger("risk_monitor")

BOTS = [
    {"name": "S4",   "api_key": os.getenv("S4_API_KEY", ""),   "api_secret": os.getenv("S4_API_SECRET", "")},
    {"name": "S4V2", "api_key": os.getenv("S4V2_API_KEY", ""), "api_secret": os.getenv("S4V2_API_SECRET", "")},
]

CHECK_INTERVAL = 30
ALERT_COOLDOWN = 300  # 5 min between repeat alerts per bot
_last_alert_ts = {}

# PLACEHOLDER THRESHOLDS - revisit with real data
WARN_DIST_PCT = 15.0
CRITICAL_DIST_PCT = 8.0
MIN_BALANCE_MULTIPLE = 1.5

def check_bot(bot):
    om = OrderManager(bot["api_key"], bot["api_secret"], testnet=True)

    pos_resp = om._get("/v2/positions/margined", {"product_ids": str(om.PRODUCT_ID)})
    if not pos_resp.get("success"):
        log.warning(f"[{bot['name']}] Could not fetch margined position: {pos_resp}")
        return

    positions = pos_resp.get("result", [])
    if not positions:
        return  # flat, nothing to check

    for p in positions:
        size = p.get("size", 0)
        if size == 0:
            continue

        liq_price = float(p.get("liquidation_price") or 0)
        margin    = float(p.get("margin") or 0)
        mark_price = om.get_current_price()

        if liq_price <= 0 or mark_price <= 0:
            log.warning(f"[{bot['name']}] Missing liq_price or mark_price - skipping this cycle")
            continue

        dist_pct = abs(mark_price - liq_price) / mark_price * 100

        bal_resp = om._get("/v2/wallet/balances", {})
        available_balance = 0.0
        if bal_resp.get("success"):
            for b in bal_resp.get("result", []):
                if b.get("asset_symbol") == "USD":
                    available_balance = float(b.get("available_balance") or 0)
                    break

        bal_ratio = (available_balance / margin) if margin > 0 else 999

        now = time.time()
        last = _last_alert_ts.get(bot["name"], 0)
        cooldown_ok = (now - last) > ALERT_COOLDOWN

        if dist_pct <= CRITICAL_DIST_PCT or bal_ratio <= 1.0:
            log.critical(f"[{bot['name']}] LIQUIDATION RISK CRITICAL | dist_to_liq={dist_pct:.1f}% mark={mark_price} liq={liq_price} bal_ratio={bal_ratio:.2f}")
            if cooldown_ok:
                send_alert(
                    f"CTS {bot['name']} CRITICAL - LIQUIDATION RISK\n"
                    f"Mark price: ${mark_price:,.1f}\n"
                    f"Liquidation price: ${liq_price:,.1f}\n"
                    f"Distance: {dist_pct:.1f}%\n"
                    f"Available balance / margin ratio: {bal_ratio:.2f}\n"
                    f"ACTION: Check position manually, consider adding margin or closing"
                )
                _last_alert_ts[bot["name"]] = now
        elif dist_pct <= WARN_DIST_PCT or bal_ratio <= MIN_BALANCE_MULTIPLE:
            log.warning(f"[{bot['name']}] Liquidation risk warning | dist_to_liq={dist_pct:.1f}% bal_ratio={bal_ratio:.2f}")
            if cooldown_ok:
                send_alert(
                    f"CTS {bot['name']} WARNING - Liquidation risk rising\n"
                    f"Distance to liquidation: {dist_pct:.1f}%\n"
                    f"Balance/margin ratio: {bal_ratio:.2f}"
                )
                _last_alert_ts[bot["name"]] = now
        else:
            log.info(f"[{bot['name']}] size={size} dist_to_liq={dist_pct:.1f}% bal_ratio={bal_ratio:.2f} - healthy")

def main():
    log.info("Position Risk Monitor started - monitor-only, no auto-action")
    while True:
        for bot in BOTS:
            try:
                check_bot(bot)
            except Exception as e:
                log.error(f"[{bot['name']}] Check failed: {e}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
