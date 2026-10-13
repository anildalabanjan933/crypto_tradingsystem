#!/usr/bin/env python3
"""
patch_bug4_5_orphan_sl.py - Bug 4 (orphan SL) + Bug 5 (stale open fill marker).
Targets: engine/order_manager.py, scripts/signal_replay_s4.py, s4v2.py, s4v3.py
Every anchor must match EXACTLY ONCE per file, else abort with nothing written.
Backups: <file>.bak_bug45_<ts>. py_compile after patching.
Run from ~/crypto_tradingsystem:  python3 patch_bug4_5_orphan_sl.py
"""
import sys, time, shutil, py_compile

OM = "engine/order_manager.py"
BOTS = ["scripts/signal_replay_s4.py", "scripts/signal_replay_s4v2.py", "scripts/signal_replay_s4v3.py"]

# --- order_manager A: cleanup endpoint lacked /v2 (cancel silently failed) ---
OM_A_OLD = '_cleanup = self._delete("/orders/all", {"product_id": self.PRODUCT_ID, "cancel_stop_orders": "true"})'
OM_A_NEW = '_cleanup = self._delete("/v2/orders/all", {"product_id": self.PRODUCT_ID, "cancel_stop_orders": True})'

# --- order_manager B: never place a reduce-only SL on a FLAT account ---
OM_B_OLD = '                _sl_size = abs(int(_pos["size"]))\n'
OM_B_NEW = (
    '                _sl_size = abs(int(_pos["size"]))\n'
    '            elif _pos.get("success") and _pos.get("size", 0) == 0:\n'
    '                logging.warning("[OrderManager] SL SKIPPED - exchange position already FLAT (no orphan SL placed)")\n'
    '                return {"success": True, "skipped": True, "sl_price": 0.0, "order_id": None, "attempts": 0}\n'
)

# --- bots: on SYNC-flat, cancel leftover stop orders + clear open fill marker ---
BOT_OLD = "                position = None\n                if _manual_exit_ts:\n"
BOT_NEW = (
    "                try:\n"
    '                    _cl = om._delete("/v2/orders/all", {"product_id": om.PRODUCT_ID, "cancel_stop_orders": True})\n'
    '                    log.info(f"[CLEANUP] SYNC-flat: orphan orders cancel success={_cl.get(\'success\')}")\n'
    "                except Exception as _ce:\n"
    '                    log.warning(f"[CLEANUP] SYNC-flat cancel failed (non-blocking): {_ce}")\n'
    "                _clear_open_fill_log(SIGNAL_CSV.replace('signals_', 'fill_prices_open_'))\n"
    + BOT_OLD
)

PLAN = {OM: [(OM_A_OLD, OM_A_NEW), (OM_B_OLD, OM_B_NEW)]}
for b in BOTS:
    PLAN[b] = [(BOT_OLD, BOT_NEW)]

srcs = {}
for f, anchors in PLAN.items():
    s = open(f).read()
    for i, (old, _) in enumerate(anchors, 1):
        n = s.count(old)
        if n != 1:
            print(f"ABORT: {f} anchor {i} matched {n}x (need 1). Nothing written.")
            sys.exit(1)
    srcs[f] = s

ts = time.strftime("%Y%m%d_%H%M%S")
for f, s in srcs.items():
    shutil.copy(f, f"{f}.bak_bug45_{ts}")
    for old, new in PLAN[f]:
        s = s.replace(old, new)
    open(f, "w").write(s)
    py_compile.compile(f, doraise=True)
    print(f"patched + compiled OK: {f}")
print("DONE. Restart live_s4/live_s4v2/live_s4v3 only when FLAT.")
print("One-time cleanup of the existing S4V3 orphan SL + stale marker (only while flat):")
print("  rm -f logs/fill_prices_open_s4v3.csv   # and cancel the stop order on S4V3RenkoCross in the Delta UI")
