#!/usr/bin/env python3
import time, os
from datetime import datetime, timezone

TRIGGER_S2 = "logs/boundary_trigger_s2.txt"
TRIGGER_S4 = "logs/boundary_trigger_s4.txt"
REPO = "/home/anildalabanjan933/crypto_trading_system"
os.chdir(REPO)

def last_closed_tf(minutes):
    now = datetime.now(timezone.utc)
    total = int(now.timestamp())
    interval = minutes * 60
    last = (total // interval) * interval
    return datetime.fromtimestamp(last, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

last_s2_fired = last_closed_tf(30)
last_s4_fired = last_closed_tf(120)

print(f"[WATCHER] Started | S2 last={last_s2_fired} | S4 last={last_s4_fired}", flush=True)

while True:
    try:
        cur_s2 = last_closed_tf(30)
        cur_s4 = last_closed_tf(120)

        if cur_s2 > last_s2_fired:
            if not os.path.exists(TRIGGER_S2):
                open(TRIGGER_S2, "w").write(cur_s2)
                print(f"[WATCHER] S2 trigger written: {cur_s2}", flush=True)
            last_s2_fired = cur_s2

        if cur_s4 > last_s4_fired:
            if not os.path.exists(TRIGGER_S4):
                open(TRIGGER_S4, "w").write(cur_s4)
                print(f"[WATCHER] S4 trigger written: {cur_s4}", flush=True)
            last_s4_fired = cur_s4

    except Exception as e:
        print(f"[WATCHER] Error: {e}", flush=True)

    time.sleep(1)
