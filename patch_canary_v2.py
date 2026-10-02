# patch_canary_v2.py  -- run from repo root
import re
p="scripts/renko_state_engine.py"; s=open(p).read()

old1='''    s4=StrategyState("S4",S4_PARAMS)
    s4v2=StrategyState("S4V2",S4V2_PARAMS)
    s4v3=StrategyState("S4V3",S4V3_PARAMS)
    update_market_data()
    load_history(s4)
    load_history(s4v2)
    load_history(s4v3)
'''
new1='''    def _hb_write():
        try:
            with open("logs/engine_heartbeat.txt","w") as _hf: _hf.write(str(time.time()))
        except Exception: pass
    def _canary_pong_thread():
        while True:
            try:
                if os.path.exists("logs/canary_ping.txt"):
                    _tmp="logs/canary_pong.txt.tmp"
                    with open(_tmp,"w") as _pf: _pf.write(str(time.time()))
                    os.replace(_tmp,"logs/canary_pong.txt")
            except Exception: pass
            time.sleep(1)
    threading.Thread(target=_canary_pong_thread,daemon=True).start()
    _hb_write()
    s4=StrategyState("S4",S4_PARAMS)
    s4v2=StrategyState("S4V2",S4V2_PARAMS)
    s4v3=StrategyState("S4V3",S4V3_PARAMS)
    update_market_data(); _hb_write()
    load_history(s4); _hb_write()
    load_history(s4v2); _hb_write()
    load_history(s4v3); _hb_write()
'''
old2='''        try:
            if os.path.exists("logs/canary_ping.txt"):
                with open("logs/canary_pong.txt", "w") as _f:
                    _f.write(str(time.time()))
        except Exception:
            pass
'''
new2='''        # canary pong now written by _canary_pong_thread (process-alive proof)
'''
for o,n in [(old1,new1),(old2,new2)]:
    assert s.count(o)==1, "engine anchor missing"; s=s.replace(o,n)
# empty trigger-file guard (ValueError '' bug, lost boundary trigger)
for v in ("s4","s4v2","s4v3"):
    o=f"if os.path.exists(_trig_{v}):"
    assert s.count(o)==1, o
    s=s.replace(o,f"if os.path.exists(_trig_{v}) and os.path.getsize(_trig_{v})>0:")
open(p,"w").write(s)

p="scripts/watchdog_fast.py"; w=open(p).read()
new='''def run_canary():
    try:
        ping_ts = time.time()
        with open("logs/canary_ping.txt", "w") as f:
            f.write(str(ping_ts))
        deadline = ping_ts + 20
        while time.time() < deadline:
            time.sleep(1)
            try:
                with open("logs/canary_pong.txt") as f:
                    if float(f.read().strip()) >= ping_ts:
                        return True
            except Exception:
                continue
        log_event("SYSTEM", "CANARY_FAIL", "No fresh pong within 20s of ping")
        return False
    except Exception as e:
        log_event("SYSTEM", "CANARY_CHECK_FAILED", str(e))
        return False
'''
w2,n=re.subn(r'def run_canary\(\):.*?\n        return False\n',lambda m:new,w,count=1,flags=re.S)
assert n==1, "run_canary not found"
open(p,"w").write(w2); print("patched")
