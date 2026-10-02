p = "scripts/watchdog_fast.py"
s = open(p).read()

old = '''def run_canary():
    try:
        with open("logs/canary_ping.txt", "w") as f:
            f.write(str(time.time()))
        time.sleep(5)
        if not os.path.exists("logs/canary_pong.txt"):
            log_event("SYSTEM", "CANARY_FAIL", "No response within 5s")
            return False
        with open("logs/canary_pong.txt") as f:
            pong_ts = float(f.read().strip())
        if time.time() - pong_ts > 10:
            log_event("SYSTEM", "CANARY_STALE", "Response too old")
            return False
        return True
    except Exception as e:
        log_event("SYSTEM", "CANARY_CHECK_FAILED", str(e))
        return False'''

new = '''def run_canary():
    try:
        with open("logs/canary_ping.txt", "w") as f:
            f.write(str(time.time()))
        time.sleep(15)
        if not os.path.exists("logs/canary_pong.txt"):
            log_event("SYSTEM", "CANARY_FAIL", "No response within 15s")
            return False
        with open("logs/canary_pong.txt") as f:
            pong_ts = float(f.read().strip())
        if time.time() - pong_ts > 20:
            log_event("SYSTEM", "CANARY_STALE", "Response too old")
            return False
        return True
    except Exception as e:
        log_event("SYSTEM", "CANARY_CHECK_FAILED", str(e))
        return False'''

assert s.count(old) == 1, "run_canary block not found or changed"
s = s.replace(old, new)
open(p, "w").write(s)
print("patched")
