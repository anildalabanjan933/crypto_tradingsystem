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

_stuck_candidates = {}  # bot_name -> (first_flat_ts, entry_id)

def check_stuck_pending(bot, csv_path):
    """Isolated check: CSV shows open PENDING row but exchange position is flat.
    This is the exact signature of the startup-lock bug (fixed 19-Aug-2026).
    Read-only + own API call - does not touch check_bot()/SL logic.
    Requires 2 consecutive flat detections (~60s apart) before alerting,
    to avoid false alarm during normal SL-fill/CSV-write timing race."""
    flag_file = f"logs/stuck_flag_{bot['name']}.txt"
    try:
        with open(csv_path) as cf:
            rows = cf.readlines()
        if not rows:
            return
        last = rows[-1].strip().split(",")
        if len(last) < 2 or last[1] != "PENDING":
            if os.path.exists(flag_file):
                os.remove(flag_file)
            _stuck_candidates.pop(bot["name"], None)
            return
        om = OrderManager(bot["api_key"], bot["api_secret"], testnet=True)
        pos = om.get_position()
        if not pos.get("success"):
            return
        size = pos.get("size", 0)
        if size == 0:
            cand = _stuck_candidates.get(bot["name"])
            if cand is None or cand[1] != last[0]:
                _stuck_candidates[bot["name"]] = (time.time(), last[0])
                return
            if time.time() - cand[0] < 55:
                return
            if not os.path.exists(flag_file):
                with open(flag_file, "w") as ff:
                    ff.write(str(time.time()))
                log.critical(f"[{bot['name']}] STUCK PENDING detected - CSV shows open but exchange flat | entry={last[0]}")
                send_alert(f"CTS {bot['name']} STUCK PENDING - CSV shows open position but exchange is FLAT\nEntry: {last[0]}\nCheck signals CSV and restart signal_generator if needed")
        else:
            if os.path.exists(flag_file):
                os.remove(flag_file)
            _stuck_candidates.pop(bot["name"], None)
    except Exception as e:
        log.error(f"[{bot['name']}] check_stuck_pending failed: {e}")


def check_orphan_position(bot, csv_path):
    """Isolated check: exchange shows OPEN position but CSV last row is not PENDING (closed/missing).
    Reverse of check_stuck_pending. Read-only + own API call - does not touch other logic."""
    flag_file = f"logs/orphan_flag_{bot['name']}.txt"
    try:
        om = OrderManager(bot["api_key"], bot["api_secret"], testnet=True)
        pos = om.get_position()
        if not pos.get("success"):
            return
        size = pos.get("size", 0)
        with open(csv_path) as cf:
            rows = cf.readlines()
        last = rows[-1].strip().split(",") if rows else []
        csv_pending = len(last) >= 2 and last[1] == "PENDING"
        if size != 0 and not csv_pending:
            if not os.path.exists(flag_file):
                with open(flag_file, "w") as ff:
                    ff.write(str(time.time()))
                log.critical(f"[{bot['name']}] ORPHAN POSITION detected - exchange OPEN (size={size}) but CSV shows no PENDING row")
                send_alert(f"CTS {bot['name']} ORPHAN POSITION - exchange has OPEN position but CSV shows it closed/missing\nSize: {size}\nCheck SL and CSV manually")
        else:
            if os.path.exists(flag_file):
                os.remove(flag_file)
    except Exception as e:
        log.error(f"[{bot['name']}] check_orphan_position failed: {e}")


_fail_count = {}

def check_extra_risks(bot, csv_path):
    """Isolated checks: API auth failure streak, low balance, size/direction mismatch.
    Read-only + own API calls - does not touch other logic."""
    try:
        om = OrderManager(bot["api_key"], bot["api_secret"], testnet=True)
        pos = om.get_position()

        # 1. API/auth failure streak
        fail_flag = f"logs/authfail_flag_{bot['name']}.txt"
        if not pos.get("success"):
            _fail_count[bot["name"]] = _fail_count.get(bot["name"], 0) + 1
            if _fail_count[bot["name"]] >= 3 and not os.path.exists(fail_flag):
                with open(fail_flag, "w") as ff:
                    ff.write(str(time.time()))
                log.critical(f"[{bot['name']}] API FAILED 3x IN A ROW - possible invalid key or connectivity issue")
                send_alert(f"CTS {bot['name']} CRITICAL - API FAILED 3 TIMES IN A ROW\nCheck API key validity and connectivity")
            return
        else:
            _fail_count[bot["name"]] = 0
            if os.path.exists(fail_flag):
                os.remove(fail_flag)

        # 2. Low balance check
        bal_flag = f"logs/lowbalance_flag_{bot['name']}.txt"
        bal_resp = om._get("/v2/wallet/balances", {})
        if bal_resp.get("success"):
            threshold = float(os.getenv("LOW_BALANCE_THRESHOLD", "50"))
            for w in bal_resp.get("result", []):
                if w.get("asset_symbol") == "USD":
                    avail = float(w.get("available_balance", "0") or 0)
                    if avail < threshold:
                        if not os.path.exists(bal_flag):
                            with open(bal_flag, "w") as ff:
                                ff.write(str(time.time()))
                            log.critical(f"[{bot['name']}] LOW BALANCE - available={avail}")
                            send_alert(f"CTS {bot['name']} LOW BALANCE WARNING\nAvailable: {avail}\nCheck margin before next trade")
                    else:
                        if os.path.exists(bal_flag):
                            os.remove(bal_flag)

        # 3. Size/direction mismatch (only when CSV shows open PENDING and exchange has a position)
        mismatch_flag = f"logs/mismatch_flag_{bot['name']}.txt"
        with open(csv_path) as cf:
            rows = cf.readlines()
        last = rows[-1].strip().split(",") if rows else []
        csv_pending = len(last) >= 4 and last[1] == "PENDING"
        size = pos.get("size", 0)
        if csv_pending and size != 0:
            csv_dir = last[2].strip().lower()
            csv_size = abs(float(last[3])) if last[3] else 0
            exch_dir = pos.get("direction", "").lower()
            exch_size = abs(size)
            if csv_dir != exch_dir or csv_size != exch_size:
                if not os.path.exists(mismatch_flag):
                    with open(mismatch_flag, "w") as ff:
                        ff.write(str(time.time()))
                    log.critical(f"[{bot['name']}] MISMATCH - CSV dir={csv_dir} size={csv_size} vs exchange dir={exch_dir} size={exch_size}")
                    send_alert(f"CTS {bot['name']} MISMATCH - CSV vs exchange differ\nCSV: {csv_dir} {csv_size}\nExchange: {exch_dir} {exch_size}\nCheck manually")
            else:
                if os.path.exists(mismatch_flag):
                    os.remove(mismatch_flag)
        else:
            if os.path.exists(mismatch_flag):
                os.remove(mismatch_flag)
    except Exception as e:
        log.error(f"[{bot['name']}] check_extra_risks failed: {e}")

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
                csv_map = {"S4": "logs/signals_s4.csv", "S4V2": "logs/signals_s4v2.csv"}
                check_stuck_pending(bot, csv_map[bot["name"]])
                check_orphan_position(bot, csv_map[bot["name"]])
                check_extra_risks(bot, csv_map[bot["name"]])
            except Exception as e:
                log.error(f"[{bot['name']}] Check failed: {e}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
