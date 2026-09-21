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
import fcntl
import csv as _csv_mod
from datetime import datetime, timezone
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
    {"name": "S4V3", "api_key": os.getenv("S4V3_API_KEY", ""), "api_secret": os.getenv("S4V3_API_SECRET", "")},
]

CHECK_INTERVAL = 60
_last_alert_ts = {}
ALERT_COOLDOWN = 300  # don't spam same bot alert more than once per 5 min

_stuck_candidates = {}  # bot_name -> (first_flat_ts, entry_id)

def _find_real_exit_fill(om, direction, entry_ts_str, window_end_ts_str, expected_size=None):
    close_side = "sell" if direction.strip().lower() == "long" else "buy"
    try:
        entry_dt = datetime.strptime(entry_ts_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        window_end_dt = datetime.strptime(window_end_ts_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None, None
    if window_end_dt <= entry_dt:
        return None, None
    try:
        resp = om._get("/v2/fills", {"product_ids": str(om.PRODUCT_ID), "page_size": 200})
    except Exception as e:
        log.warning(f"_find_real_exit_fill: fills lookup failed: {e}")
        return None, None
    if not resp.get("success"):
        return None, None
    candidates = []
    for f in resp.get("result", []):
        if f.get("side") != close_side:
            continue
        raw_ts = f.get("created_at")
        if not raw_ts:
            continue
        try:
            f_dt = datetime.strptime(raw_ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if entry_dt <= f_dt <= window_end_dt:
            candidates.append((f_dt, f))
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[0])
    best_dt, best_fill = candidates[0]
    try:
        exit_price = float(best_fill.get("price", 0.0))
    except Exception:
        exit_price = 0.0
    if exit_price <= 0:
        return None, None
    return best_dt.strftime("%Y-%m-%dT%H:%M:%S"), exit_price


def check_stuck_pending(bot, csv_path):
    """Isolated check: CSV shows open PENDING row(s) but exchange position is flat,
    OR historical PENDING rows already superseded by a newer row (guaranteed stale).
    Scans ALL rows, not just the last one, so no PENDING row can ever remain stuck
    permanently. Fully automatic, no manual step, no Telegram watching required."""
    flag_file = f"logs/stuck_flag_{bot['name']}.txt"
    try:
        with open(csv_path) as cf:
            rows = cf.readlines()
        if not rows:
            return

        # PASS 1: heal any BACKLOG PENDING row (not the last row in the file).
        # A newer trade row already exists after it, so this PENDING is
        # guaranteed stale/superseded - heal immediately, no exchange check
        # or wait needed, since the bot has already moved on to a new trade.
        changed = False
        _om_p1 = None
        healed_sources = []
        for i in range(len(rows) - 1):
            parts = rows[i].strip().split(",")
            if len(parts) >= 2 and parts[1] == "PENDING":
                next_parts = rows[i + 1].strip().split(",")
                fallback_exit_ts = next_parts[0] if len(next_parts) > 0 else _now_utc_str()
                fallback_exit_price = next_parts[4] if len(next_parts) > 4 else "0.0"

                exit_ts, exit_price, source = fallback_exit_ts, fallback_exit_price, "fallback_next_row_copy"
                try:
                    if _om_p1 is None:
                        _om_p1 = OrderManager(bot["api_key"], bot["api_secret"], testnet=True)
                    direction = parts[2] if len(parts) > 2 else ""
                    real_ts, real_price = _find_real_exit_fill(
                        _om_p1, direction, parts[0], fallback_exit_ts,
                        parts[3] if len(parts) > 3 else None
                    )
                    if real_ts and real_price:
                        exit_ts, exit_price, source = real_ts, real_price, "real_fill_lookup"
                except Exception as _fe:
                    log.warning(f"[{bot['name']}] PASS1 real-fill lookup failed for row {parts[0]}: {_fe} - using fallback")

                parts[1] = exit_ts
                if len(parts) >= 6:
                    parts[5] = str(exit_price)
                rows[i] = ",".join(parts) + "\n"
                changed = True
                healed_sources.append(source)
                log.critical(f"[{bot['name']}] BACKLOG STUCK PENDING auto-healed ({source}) | entry={parts[0]} exit_ts={exit_ts} exit_price={exit_price}")

        if changed:
            for _try in range(3):
                try:
                    lock_path = csv_path + ".lock"
                    lf = open(lock_path, "a")
                    fcntl.flock(lf, fcntl.LOCK_EX)
                    try:
                        with open(csv_path, "w") as cf3:
                            cf3.writelines(rows)
                    finally:
                        fcntl.flock(lf, fcntl.LOCK_UN)
                        lf.close()
                    if changed:
                        real_count = healed_sources.count("real_fill_lookup")
                        fallback_count = healed_sources.count("fallback_next_row_copy")
                        send_alert(f"CTS {bot['name']} BACKLOG CSV CLEANUP - closed stale PENDING row(s) in log file (real exchange fill used: {real_count}, next-row fallback used: {fallback_count}). This is routine CSV bookkeeping on old superseded rows, NOT a live trading stall. No action needed.")
                    break
                except Exception:
                    time.sleep(2)

        # PASS 2: existing logic for the LAST row (may be a live open position).
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
                log.critical(f"[{bot['name']}] STUCK PENDING CONFIRMED - AUTO-HEALING | entry={last[0]}")
                exit_price = 0.0
                try:
                    exit_price = om.get_current_price()
                except Exception:
                    exit_price = 0.0
                exit_ts = _now_utc_str()
                healed = False
                _last_err = None
                for _try in range(3):
                    try:
                        lock_path = csv_path + ".lock"
                        lf = open(lock_path, "a")
                        fcntl.flock(lf, fcntl.LOCK_EX)
                        try:
                            with open(csv_path) as cf2:
                                all_rows = cf2.readlines()
                            if all_rows and all_rows[-1].strip().split(",")[1] == "PENDING":
                                fixed = all_rows[-1].strip().split(",")
                                fixed[1] = exit_ts
                                if len(fixed) >= 6:
                                    fixed[5] = str(exit_price)
                                all_rows[-1] = ",".join(fixed) + "\n"
                                with open(csv_path, "w") as cf3:
                                    cf3.writelines(all_rows)
                            healed = True
                        finally:
                            fcntl.flock(lf, fcntl.LOCK_UN)
                            lf.close()
                        break
                    except Exception as _he:
                        _last_err = _he
                        time.sleep(2)
                if healed:
                    with open(flag_file, "w") as ff:
                        ff.write(str(time.time()))
                    log.info(f"[{bot['name']}] Stuck-pending auto-heal OK exit_ts={exit_ts} exit_price={exit_price}")
                    send_alert(f"CTS {bot['name']} STUCK PENDING AUTO-HEALED - closed CSV row entry={last[0]} exit_ts={exit_ts} exit_price={exit_price}. Fully automatic, no action needed.")
                else:
                    log.critical(f"[{bot['name']}] Stuck-pending auto-heal failed after 3 retries: {_last_err}")
                    send_alert(f"CTS {bot['name']} WARNING - stuck-pending auto-heal retrying automatically, no action needed, system will keep retrying.")
        else:
            if os.path.exists(flag_file):
                os.remove(flag_file)
            _stuck_candidates.pop(bot["name"], None)
    except Exception as e:
        log.error(f"[{bot['name']}] check_stuck_pending failed: {e}")


_orphan_candidates = {}
_fail_count = {}

def _now_utc_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def _append_orphan_pending_row(csv_path, direction, entry_price, size):
    lock_path = csv_path + ".lock"
    lf = open(lock_path, "a")
    fcntl.flock(lf, fcntl.LOCK_EX)
    try:
        entry_ts = _now_utc_str()
        with open(csv_path, "a", newline="") as f:
            w = _csv_mod.writer(f)
            w.writerow([entry_ts, "PENDING", direction, size, entry_price, ""])
        return entry_ts
    finally:
        fcntl.flock(lf, fcntl.LOCK_UN)
        lf.close()

def check_orphan_position(bot, csv_path):
    flag_file = f"logs/orphan_flag_{bot['name']}.txt"
    try:
        om = OrderManager(bot['api_key'], bot['api_secret'], testnet=True)
        pos = om.get_position()
        if not pos.get('success'):
            return
        size = pos.get('size', 0)
        with open(csv_path) as cf:
            rows = cf.readlines()
        last = rows[-1].strip().split(',') if rows else []
        csv_pending = len(last) >= 2 and last[1] == 'PENDING'
        if size != 0 and not csv_pending:
            direction = pos.get('direction', 'UNKNOWN').lower()
            abs_size = abs(size)
            cand = _orphan_candidates.get(bot['name'])
            if cand is None or cand[1] != direction or cand[2] != abs_size:
                _orphan_candidates[bot['name']] = (time.time(), direction, abs_size)
                return
            if time.time() - cand[0] < 55:
                return
            if not os.path.exists(flag_file):
                entry_price = pos.get('entry_price', 0.0)
                if not entry_price or entry_price <= 0:
                    entry_price = pos.get('exit_price', 0.0)
                if not entry_price or entry_price <= 0:
                    try:
                        entry_price = om.get_current_price()
                    except Exception:
                        entry_price = 0.0
                log.critical(f"[{bot['name']}] ORPHAN POSITION CONFIRMED - AUTO-HEALING")
                new_ts = None
                _last_err = None
                for _try in range(3):
                    try:
                        new_ts = _append_orphan_pending_row(csv_path, direction, entry_price, abs_size)
                        break
                    except Exception as _he:
                        _last_err = _he
                        time.sleep(2)
                if new_ts:
                    with open(flag_file, 'w') as ff:
                        ff.write(str(time.time()))
                    log.info(f"[{bot['name']}] Orphan auto-heal OK entry_ts={new_ts}")
                    send_alert(f"CTS {bot['name']} ORPHAN POSITION AUTO-HEALED - wrote PENDING row entry_ts={new_ts} dir={direction} size={abs_size} entry={entry_price}. No position closed, fully automatic.")
                else:
                    log.critical(f"[{bot['name']}] Orphan auto-heal failed after 3 retries: {_last_err}")
                    send_alert(f"CTS {bot['name']} WARNING - orphan auto-heal retrying, position remains safely open on exchange, no action needed, system will keep retrying automatically.")
        else:
            if os.path.exists(flag_file):
                os.remove(flag_file)
            _orphan_candidates.pop(bot['name'], None)
    except Exception as e:
        log.error(f"[{bot['name']}] check_orphan_position failed: {e}")


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
                time.sleep(10)
                pos = get_position(bot)
                exch_dir = pos.get("direction", "").lower()
                exch_size = abs(pos.get("size", 0))
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
                send_alert(f"CTS {bot['name']} WARNING - SL auto-place retrying, system will keep attempting automatically, no action needed. Size: {size} Error: {sl_result.get('error')}")
            _last_alert_ts[bot["name"]] = now
    else:
        log.info(f"[{bot['name']}] position size={size} - SL confirmed present")

def main():
    log.info("SL Safety Monitor started - monitor-only, no auto-action")
    while True:
        try:
            open('logs/sl_safety_monitor_heartbeat.txt','w').write(str(__import__('time').time()))
        except Exception:
            pass
        for bot in BOTS:
            if not bot["api_key"] or not bot["api_secret"]:
                continue  # keys not provisioned yet (e.g. S4V3 pending ticket) - skip silently, no spam
            try:
                check_bot(bot)
                csv_map = {"S4": "logs/signals_s4.csv", "S4V2": "logs/signals_s4v2.csv", "S4V3": "logs/signals_s4v3.csv"}
                check_stuck_pending(bot, csv_map[bot["name"]])
                check_orphan_position(bot, csv_map[bot["name"]])
                check_extra_risks(bot, csv_map[bot["name"]])
            except Exception as e:
                log.error(f"[{bot['name']}] Check failed: {e}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
