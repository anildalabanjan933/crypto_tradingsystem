import time, os
from datetime import datetime, timezone

LOG_SRC = "/home/anildalabanjan7/crypto_tradingsystem/logs/renko_state_engine.log"
LOG_OUT = "/home/anildalabanjan7/crypto_tradingsystem/logs/repaint_guard_watch.log"
CHECK_INTERVAL = 60

def log_flag(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(LOG_OUT, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}")

def main():
    log_flag("REPAINT GUARD WATCHER STARTED")
    last_pos = os.path.getsize(LOG_SRC) if os.path.exists(LOG_SRC) else 0
    while True:
        try:
            if os.path.exists(LOG_SRC):
                size = os.path.getsize(LOG_SRC)
                if size > last_pos:
                    with open(LOG_SRC, "r") as f:
                        f.seek(last_pos)
                        new_lines = f.readlines()
                    last_pos = size
                    for line in new_lines:
                        if "REPAINT GUARD" in line:
                            log_flag(f"DETECTED: {line.strip()}")
                elif size < last_pos:
                    last_pos = 0
        except Exception as e:
            log_flag(f"WATCHER ERROR: {e}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
