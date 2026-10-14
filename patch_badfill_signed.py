#!/usr/bin/env python3
import sys, shutil, time, py_compile

STAMP = time.strftime("%Y%m%d_%H%M%S")

def patch(path, old, new):
    src = open(path).read()
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT {path}: expected 1 match of old block, found {n}")
    shutil.copy(path, f"{path}.bak_badfill_{STAMP}")
    open(path, "w").write(src.replace(old, new))
    py_compile.compile(path, doraise=True)
    print(f"OK  {path}")

OLD1 = """                _dev = abs(_avg - _ref_price)
                if _dev > _band:"""
NEW1 = """                _dev = (_avg - _ref_price) if side == "buy" else (_ref_price - _avg)
                if _dev > _band:"""
patch("engine/order_manager.py", OLD1, NEW1)

OLD2 = """_sync_exit_ts = _dt3.now(_tz3.utc).strftime("%Y-%m-%dT%H:%M:%S")"""
NEW2 = """_now3 = _dt3.now(_tz3.utc)
                        _mod3 = ((_now3.hour * 60 + _now3.minute) // _BG_TF_MIN) * _BG_TF_MIN
                        _sync_exit_ts = _now3.replace(hour=_mod3 // 60, minute=_mod3 % 60, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")"""
for f in ("scripts/signal_replay_s4.py", "scripts/signal_replay_s4v3.py"):
    patch(f, OLD2, NEW2)

print("Done.")
