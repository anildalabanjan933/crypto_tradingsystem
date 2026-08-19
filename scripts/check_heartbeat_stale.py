"""
Standalone liveness checker for check_box_drift.py.
Reads logs/box_drift_heartbeat.txt written by check_box_drift.py's main().
Alerts via Telegram if heartbeat is missing or older than 30 hours
(gives buffer past the 24h daily cycle before flagging as stale).
Does NOT modify or depend on check_box_drift.py's drift-detection logic.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HEARTBEAT_FILE = "logs/box_drift_heartbeat.txt"
STALE_HOURS = 30

def main():
    try:
        from engine.telegram_alert import send_telegram_alert
    except Exception:
        send_telegram_alert = None

    if not os.path.exists(HEARTBEAT_FILE):
        msg = f"[HEARTBEAT] {HEARTBEAT_FILE} not found - check_box_drift.py may have never run"
        print(msg)
        if send_telegram_alert:
            try: send_telegram_alert(msg)
            except Exception: pass
        return

    try:
        with open(HEARTBEAT_FILE) as f:
            last_run = datetime.datetime.strptime(f.read().strip(), "%Y-%m-%dT%H:%M:%S")
    except Exception as e:
        print(f"[HEARTBEAT] Could not parse heartbeat file: {e}")
        return

    age_hours = (datetime.datetime.utcnow() - last_run).total_seconds() / 3600
    if age_hours > STALE_HOURS:
        msg = f"[HEARTBEAT] check_box_drift.py stale - last ran {age_hours:.1f} hours ago (threshold {STALE_HOURS}h)"
        print(msg)
        if send_telegram_alert:
            try: send_telegram_alert(msg)
            except Exception: pass
    else:
        print(f"[HEARTBEAT] OK - last ran {age_hours:.1f} hours ago")

if __name__ == "__main__":
    main()
