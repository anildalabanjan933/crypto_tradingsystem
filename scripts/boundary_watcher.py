#!/usr/bin/env python3
import time, os, logging
from datetime import datetime, timezone

REPO = "/home/anildalabanjan933/crypto_trading_system"
os.chdir(REPO)
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("logs/boundary_watcher.log", mode="a")]
)
log = logging.getLogger(__name__)

TRIGGER_S4 = "logs/boundary_trigger_s4.txt"
TRIGGER_S4V2 = "logs/boundary_trigger_s4v2.txt"
TRIGGER_S4V3 = "logs/boundary_trigger_s4v3.txt"

def last_closed_tf(minutes):
    now = datetime.now(timezone.utc)
    total = int(now.timestamp())
    interval = minutes * 60
    last = (total // interval) * interval
    return datetime.fromtimestamp(last, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

try:
    last_s4_fired = last_closed_tf(120)
    last_s4v2_fired = last_closed_tf(30)
    last_s4v3_fired = last_closed_tf(240)
    log.info(f"[WATCHER] Started | S4 last={last_s4_fired} | S4V2 last={last_s4v2_fired} | S4V3 last={last_s4v3_fired}")
except Exception as e:
    log.critical(f"[WATCHER] STARTUP CRASH: {e}", exc_info=True)
    raise

while True:
    try:
        cur_s4 = last_closed_tf(120)
        cur_s4v2 = last_closed_tf(30)
        cur_s4v3 = last_closed_tf(240)

        if cur_s4 > last_s4_fired:
            if not os.path.exists(TRIGGER_S4):
                open(TRIGGER_S4, "w").write(cur_s4)
                log.info(f"[WATCHER] S4 trigger written: {cur_s4}")
            last_s4_fired = cur_s4

        if cur_s4v2 > last_s4v2_fired:
            if not os.path.exists(TRIGGER_S4V2):
                open(TRIGGER_S4V2, "w").write(cur_s4v2)
                log.info(f"[WATCHER] S4V2 trigger written: {cur_s4v2}")
            last_s4v2_fired = cur_s4v2

        if cur_s4v3 > last_s4v3_fired:
            if not os.path.exists(TRIGGER_S4V3):
                open(TRIGGER_S4V3, "w").write(cur_s4v3)
                log.info(f"[WATCHER] S4V3 trigger written: {cur_s4v3}")
            last_s4v3_fired = cur_s4v3

    except Exception as e:
        log.error(f"[WATCHER] Loop error: {e}", exc_info=True)

    time.sleep(1)
