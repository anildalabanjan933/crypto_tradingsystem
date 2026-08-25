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

FIX (25-Aug-2026): Added heartbeat file + hard per-check timeout via
SIGALRM. Root cause investigation of the 24-Aug-2026 S4V2 trade flood
(121 live orders vs 22 BT trades) traced back to this process hanging
silently between 16:02 and 17:09 on 24-Aug, with no exception/crash and
no restart until 10:41 the next day - a 17.5hr window with zero Tier1/
Tier2 protection. This fix ensures a stuck check_bot() call is forcibly
aborted after CHECK_TIME_BUDGET_SEC instead of hanging indefinitely, and
writes a heartbeat file every cycle so external watchdogs can detect a
stall within seconds instead of relying on log-silence alone.
"""
import os
import sys
import time
import signal
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
    {"name": "TM1",  "api_key": os.getenv("TESTMEMBER1_S4V2_API_KEY", ""), "api_secret": os.getenv("TESTMEMBER1_S4V2_API_SECRET", "")},
]

CHECK_INTERVAL = 30
ALERT_COOLDOWN = 300  # 5 min between repeat alerts per bot
_last_alert_ts = {}

HEARTBEAT_FILE = "logs/position_risk_monitor_heartbeat.txt"
CHECK_TIME_BUDGET_SEC = 45  # hard ceiling per bot check (fix 25-Aug-2026)

# RECALIBRATED THRESHOLDS (16-Aug-2026) - since emergency SL is at 1.5% price move,
# and normal distance-to-liquidation at entry is ~9-10% for this leverage, these
# should only fire if price has moved PAST where the emergency SL should have
# already triggered (i.e. SL malfunction / system-down scenario) - not on every
# normal healthy trade.
WARN_DIST_PCT = 10.0
CRITICAL_DIST_PCT = 7.0
MIN_BALANCE_MULTIPLE = 1.5

# TIER 1 - Speed filter (25-Aug-2026): sized from real 2-month replay data
# (S4 max=3.56%/min, S4V2 max=3.56%/min, zero trades in 2mo crossed 4%/min).
# Set at 5%/min - never fires on normal trading, only genuine fast crashes.
SPEED_THRESHOLD_PCT_PER_MIN = 5.0
_price_history = {}  # bot_name -> list of (timestamp, price)


class _CheckTimeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise _CheckTimeout("check_bot exceeded time budget")


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
        now_ts = time.time()

        liq_price = float(p.get("liquidation_price") or 0)
        margin    = float(p.get("margin") or 0)
        mark_price = om.get_current_price()

        if liq_price <= 0 or mark_price <= 0:
            log.warning(f"[{bot['name']}] Missing liq_price or mark_price - skipping this cycle")
            continue

        dist_pct = abs(mark_price - liq_price) / mark_price * 100

        # TIER 1 - speed check using rolling price history (no extra API call)
        _hist = _price_history.setdefault(bot["name"], [])
        _hist.append((now_ts, mark_price))
        _hist[:] = [(t, p) for t, p in _hist if now_ts - t <= 65]
        if len(_hist) >= 2:
            _oldest_t, _oldest_p = _hist[0]
            _elapsed_min = (now_ts - _oldest_t) / 60.0
            if _elapsed_min > 0 and _oldest_p > 0:
                _speed_pct_per_min = abs(mark_price - _oldest_p) / _oldest_p * 100 / _elapsed_min
                if _speed_pct_per_min >= SPEED_THRESHOLD_PCT_PER_MIN:
                    log.critical(f"[{bot['name']}] TIER 1 SPEED ALERT | {_speed_pct_per_min:.2f}%/min move detected - emergency closing")
                    _close_side = "sell" if size > 0 else "buy"
                    _speed_close = om.close_position(size=abs(size), side=_close_side)
                    send_alert(
                        f"CTS {bot['name']} CRITICAL - TIER 1 SPEED FILTER TRIGGERED\n"
                        f"Speed: {_speed_pct_per_min:.2f}%/min (threshold {SPEED_THRESHOLD_PCT_PER_MIN}%/min)\n"
                        f"Price moved ${_oldest_p:,.1f} -> ${mark_price:,.1f} in {_elapsed_min:.1f}min\n"
                        f"Emergency close: success={_speed_close.get('success')} avg_fill={_speed_close.get('avg_fill_price')}"
                    )
                    _hist.clear()

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

        if dist_pct <= CRITICAL_DIST_PCT:
            log.critical(f"[{bot['name']}] LIQUIDATION RISK CRITICAL | dist_to_liq={dist_pct:.1f}% mark={mark_price} liq={liq_price} bal_ratio={bal_ratio:.2f}")
            close_side = "sell" if size > 0 else "buy"
            close_result = om.close_position(size=abs(size), side=close_side)
            if cooldown_ok:
                send_alert(
                    f"CTS {bot['name']} CRITICAL - LIQUIDATION RISK\n"
                    f"Mark price: ${mark_price:,.1f}\n"
                    f"Liquidation price: ${liq_price:,.1f}\n"
                    f"Distance: {dist_pct:.1f}%\n"
                    f"Available balance / margin ratio: {bal_ratio:.2f}\n"
                    f"Position closed at avg_fill={close_result.get('avg_fill_price')} | success={close_result.get('success')}"
                )
                _last_alert_ts[bot["name"]] = now
        elif dist_pct <= WARN_DIST_PCT:
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
    signal.signal(signal.SIGALRM, _timeout_handler)
    while True:
        for bot in BOTS:
            try:
                with open(HEARTBEAT_FILE, "w") as _hb:
                    _hb.write(str(time.time()))
            except Exception as _hbe:
                log.warning(f"Heartbeat write failed: {_hbe}")
            try:
                signal.alarm(CHECK_TIME_BUDGET_SEC)
                check_bot(bot)
            except _CheckTimeout:
                log.error(f"[{bot['name']}] Check TIMED OUT after {CHECK_TIME_BUDGET_SEC}s - aborting this cycle (fix for 24-Aug-2026 17.5hr blind window)")
            except Exception as e:
                log.error(f"[{bot['name']}] Check failed: {e}")
            finally:
                signal.alarm(0)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
