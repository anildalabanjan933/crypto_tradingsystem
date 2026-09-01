"""
Maintenance Watcher - monitors Delta Exchange public WebSocket system_status
channel and pauses/resumes bot entries around exchange maintenance windows.

Behaviour (Claude-approved design, 01-Sep-2026):
- maintenance_scheduled : schedule a close-all-positions action 10 minutes
  before the estimated maintenance_start_time.
- maintenance_started   : close all positions immediately (covers unplanned
  maintenance, or scheduled maintenance that started before our pre-close
  timer fired). Sets logs/maintenance_active.txt.
- maintenance_finished  : wait 15 minutes, then require 3 consecutive
  successful price-fetch checks (30s apart) before clearing
  logs/maintenance_active.txt to resume entries.
- maintenance_cancelled : cancel any pending scheduled pre-close timer.

logs/maintenance_active.txt is a shared flag file. Bot replay scripts check
it ONLY on their ENTRY branch (never on EXIT/close branches), failing open
(allow entry) if the file cannot be read, per design decision.

Does NOT touch _pair_fills_audit(), today_trades_app.py, trade_audit_tab.py,
or any CSV-reconciled logic. Read/act only on live positions via OrderManager.
"""
import os
import sys
import json
import time
import threading
import logging

sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

import websocket
from engine.order_manager import OrderManager
from engine.telegram_alert import send_alert

WS_URL = "wss://public-socket.india.delta.exchange"
FLAG_FILE = "logs/maintenance_active.txt"
HEARTBEAT_FILE = "logs/maintenance_watcher_heartbeat.txt"
HEARTBEAT_TIMEOUT_SEC = 35
PRECLOSE_LEAD_SEC = 600          # 10 minutes before maintenance_start_time
RESUME_WAIT_SEC = 900            # 15 minutes after maintenance_finished
RESUME_CHECK_INTERVAL_SEC = 30
RESUME_REQUIRED_CONSECUTIVE = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("logs/maintenance_watcher.log"), logging.StreamHandler()]
)
log = logging.getLogger("maintenance_watcher")

BOTS = {
    "S4":             (os.getenv("S4_API_KEY", ""), os.getenv("S4_API_SECRET", "")),
    "S4V2":           (os.getenv("S4V2_API_KEY", ""), os.getenv("S4V2_API_SECRET", "")),
    "S4V3":           (os.getenv("S4V3_API_KEY", ""), os.getenv("S4V3_API_SECRET", "")),
    "TESTMEMBER1_S4": (os.getenv("TESTMEMBER1_S4_API_KEY", ""), os.getenv("TESTMEMBER1_S4_API_SECRET", "")),
}

_state_lock = threading.Lock()
_pending_preclose_timer = None
_last_heartbeat_ts = time.time()
_current_ws = None


def write_heartbeat():
    try:
        with open(HEARTBEAT_FILE, "w") as f:
            f.write(str(time.time()))
    except Exception as e:
        log.warning(f"[MaintenanceWatcher] Could not write heartbeat file: {e}")


def set_maintenance_flag(reason):
    try:
        os.makedirs(os.path.dirname(FLAG_FILE), exist_ok=True)
        with open(FLAG_FILE, "w") as f:
            f.write(f"{time.time()}|{reason}")
        log.info(f"[MaintenanceWatcher] FLAG SET | reason={reason}")
    except Exception as e:
        log.error(f"[MaintenanceWatcher] Failed to write flag file: {e}")


def clear_maintenance_flag():
    try:
        if os.path.exists(FLAG_FILE):
            os.remove(FLAG_FILE)
        log.info("[MaintenanceWatcher] FLAG CLEARED - entries resumed")
    except Exception as e:
        log.error(f"[MaintenanceWatcher] Failed to clear flag file: {e}")


def close_all_positions(trigger_reason):
    log.info(f"[MaintenanceWatcher] close_all_positions triggered | reason={trigger_reason}")
    for name, (key, secret) in BOTS.items():
        if not key or not secret:
            log.warning(f"[MaintenanceWatcher] {name} skipped - API key/secret not provisioned")
            continue
        try:
            om = OrderManager(key, secret, testnet=True)
            pos = om.get_position()
            if not pos.get("success"):
                log.error(f"[MaintenanceWatcher] {name} get_position failed: {pos.get('error')}")
                continue
            size = pos.get("size", 0)
            if size == 0:
                log.info(f"[MaintenanceWatcher] {name} already flat, nothing to close")
                continue
            side = "sell" if size > 0 else "buy"
            log.info(f"[MaintenanceWatcher] {name} closing size={size} side={side} due to {trigger_reason}")
            result = om.close_position(size=abs(size), side=side)
            if result.get("success"):
                log.info(f"[MaintenanceWatcher] {name} CLOSED successfully | order_id={result.get('order_id')}")
            else:
                log.critical(f"[MaintenanceWatcher] {name} CLOSE FAILED | error={result.get('error')}")
                send_alert(f"CTS CRITICAL - Maintenance close FAILED for {name}\nReason: {trigger_reason}\nError: {result.get('error')}\nMANUAL INTERVENTION MAY BE REQUIRED")
        except Exception as e:
            log.critical(f"[MaintenanceWatcher] {name} close_all_positions exception: {e}")
            send_alert(f"CTS CRITICAL - Maintenance watcher exception closing {name}\n{e}")


def cancel_pending_preclose():
    global _pending_preclose_timer
    with _state_lock:
        if _pending_preclose_timer is not None:
            _pending_preclose_timer.cancel()
            _pending_preclose_timer = None
            log.info("[MaintenanceWatcher] Pending pre-close timer cancelled")


def schedule_preclose(maintenance_start_time_us):
    global _pending_preclose_timer
    cancel_pending_preclose()
    now_us = time.time() * 1_000_000
    delay_sec = (maintenance_start_time_us - now_us) / 1_000_000 - PRECLOSE_LEAD_SEC
    if delay_sec <= 0:
        log.warning(f"[MaintenanceWatcher] Scheduled maintenance imminent (delay_sec={delay_sec:.1f}), closing now")
        threading.Thread(target=lambda: (close_all_positions("maintenance_scheduled_imminent"), set_maintenance_flag("scheduled")), daemon=True).start()
        return
    log.info(f"[MaintenanceWatcher] Scheduled pre-close in {delay_sec:.1f}s (10min before maintenance_start_time)")

    def _fire():
        close_all_positions("maintenance_scheduled_preclose")
        set_maintenance_flag("scheduled")

    t = threading.Timer(delay_sec, _fire)
    t.daemon = True
    with _state_lock:
        _pending_preclose_timer = t
    t.start()


def handle_maintenance_started():
    cancel_pending_preclose()
    close_all_positions("maintenance_started")
    set_maintenance_flag("started")
    send_alert("CTS INFO - Exchange maintenance STARTED\nAll bot positions closed, entries PAUSED")


def handle_maintenance_finished():
    def _resume_gate():
        log.info(f"[MaintenanceWatcher] Maintenance finished - waiting {RESUME_WAIT_SEC}s before resume checks")
        time.sleep(RESUME_WAIT_SEC)
        consecutive = 0
        probe_key, probe_secret = BOTS.get("S4", ("", ""))
        while consecutive < RESUME_REQUIRED_CONSECUTIVE:
            price = None
            try:
                if probe_key and probe_secret:
                    om = OrderManager(probe_key, probe_secret, testnet=True)
                    price = om.get_current_price()
            except Exception as e:
                log.warning(f"[MaintenanceWatcher] Resume check exception: {e}")
                price = None
            if price and price > 0:
                consecutive += 1
                log.info(f"[MaintenanceWatcher] Resume check {consecutive}/{RESUME_REQUIRED_CONSECUTIVE} OK price={price}")
            else:
                if consecutive > 0:
                    log.warning("[MaintenanceWatcher] Resume check FAILED, resetting consecutive counter")
                consecutive = 0
            time.sleep(RESUME_CHECK_INTERVAL_SEC)
        clear_maintenance_flag()
        send_alert("CTS INFO - Exchange maintenance FINISHED\nEntries RESUMED after 15min + 3 consecutive price checks")

    threading.Thread(target=_resume_gate, daemon=True).start()


def handle_maintenance_cancelled():
    cancel_pending_preclose()
    log.info("[MaintenanceWatcher] Scheduled maintenance CANCELLED, pre-close timer cancelled if pending")


def on_open(ws):
    global _last_heartbeat_ts
    log.info("[MaintenanceWatcher] WebSocket connection opened")
    _last_heartbeat_ts = time.time()
    ws.send(json.dumps({
        "type": "subscribe",
        "payload": {"channels": [{"name": "system_status"}]}
    }))
    ws.send(json.dumps({"type": "enable_heartbeat"}))


def on_message(ws, message):
    global _last_heartbeat_ts
    write_heartbeat()
    try:
        data = json.loads(message)
    except Exception as e:
        log.error(f"[MaintenanceWatcher] Failed to parse message: {e}")
        return

    msg_type = data.get("type")

    if msg_type == "heartbeat":
        _last_heartbeat_ts = time.time()
        return

    if msg_type == "system_status":
        event = data.get("event")
        status = data.get("status")
        log.info(f"[MaintenanceWatcher] system_status | event={event} status={status}")

        if event == "maintenance_scheduled":
            schedule_preclose(data["maintenance_start_time"])
        elif event == "maintenance_started":
            handle_maintenance_started()
        elif event == "maintenance_finished":
            handle_maintenance_finished()
        elif event == "maintenance_cancelled":
            handle_maintenance_cancelled()
        elif event == "snapshot":
            log.info(f"[MaintenanceWatcher] Initial snapshot received | status={status}")
        return

    log.info(f"[MaintenanceWatcher] Unhandled message: {data}")


def on_error(ws, error):
    log.error(f"[MaintenanceWatcher] WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg):
    log.warning(f"[MaintenanceWatcher] WebSocket closed | status={close_status_code} msg={close_msg}")


def heartbeat_watchdog():
    global _current_ws
    while True:
        time.sleep(5)
        if time.time() - _last_heartbeat_ts > HEARTBEAT_TIMEOUT_SEC:
            log.warning(f"[MaintenanceWatcher] No heartbeat in {HEARTBEAT_TIMEOUT_SEC}s, forcing reconnect")
            try:
                if _current_ws is not None:
                    _current_ws.close()
            except Exception as e:
                log.error(f"[MaintenanceWatcher] Error forcing close for reconnect: {e}")


def main():
    global _current_ws, _last_heartbeat_ts
    log.info("[MaintenanceWatcher] Starting maintenance watcher")
    wd_thread = threading.Thread(target=heartbeat_watchdog, daemon=True)
    wd_thread.start()

    while True:
        try:
            _last_heartbeat_ts = time.time()
            ws = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            _current_ws = ws
            ws.run_forever()
        except Exception as e:
            log.error(f"[MaintenanceWatcher] run_forever exception: {e}")

        log.warning("[MaintenanceWatcher] Connection lost, reconnecting in 3s")
        time.sleep(3)


if __name__ == "__main__":
    main()
