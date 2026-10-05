#!/usr/bin/env python3
"""Usage: .venv/bin/python3 scripts/drill_tier.py tier1|tier2"""
import os, sys, re, json, time
os.chdir("/home/anildalabanjan7/crypto_tradingsystem"); sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv()
from scripts.cts_env import IS_TESTNET
from datetime import datetime, timezone
if not IS_TESTNET: sys.exit("REFUSED: production")
mode = sys.argv[1] if len(sys.argv) > 1 else ""
assert mode in ("tier1", "tier2"), "arg must be tier1|tier2"
n = datetime.now(timezone.utc)
if (n.hour % 4 == 3 and n.minute >= 57) or (n.hour % 4 == 0 and n.minute < 3):
    sys.exit("REFUSED: within 3 min of an S4V3 4H boundary - rerun later")
from engine.order_manager import OrderManager
import scripts.position_risk_monitor as m
assert hasattr(m, "check_bot") and hasattr(m, "BOTS"), "ABORT: monitor lacks check_bot/BOTS"
bot = next(b for b in m.BOTS if b.get("name") == "S4V3")
om = OrderManager(os.environ["S4V3_API_KEY"], os.environ["S4V3_API_SECRET"], testnet=True)
p0 = om.get_position(); assert p0.get("success") and p0.get("size", 0) == 0, "S4V3 must be FLAT"

real_get, real_pos, real_px = OrderManager._get, OrderManager.get_position, OrderManager.get_current_price
st = {"factor": 1.0, "ref": 0.0}
def inject(k, v):
    try: f = float(v)
    except Exception: return v
    kl = k.lower()
    if mode == "tier1" and kl in ("mark_price", "last_price", "index_price"):
        r = f * st["factor"]
    elif mode == "tier2" and kl in ("liquidation_price", "liq_price") and st["ref"]:
        r = st["ref"] * 0.95
    else: return v
    return str(r) if isinstance(v, str) else r
def rewrite(o):
    if isinstance(o, dict):
        d = {k: (rewrite(v) if isinstance(v, (dict, list)) else inject(k, v)) for k, v in o.items()}
        if mode == "tier2" and st["ref"] and "entry_price" in d and "size" in d:
            d["liquidation_price"] = st["ref"] * 0.95
        return d
    if isinstance(o, list): return [rewrite(x) for x in o]
    return o

LOG = "logs/position_risk_monitor.log"; off = os.path.getsize(LOG) if os.path.exists(LOG) else 0
ok = False; note = ""
try:
    res = om.place_market_order(side="buy", size=1, client_order_id=f"DRILL{mode}{int(time.time())}", attempt=0)
    assert res.get("success"), f"entry failed: {res}"
    entry = res.get("avg_fill_price") or om.get_position().get("entry_price", 0.0)
    st["ref"] = float(entry)
    om.place_stop_loss_order(direction="long", entry_price=float(entry), sl_pct=10.0)
    OrderManager._get = lambda self, *a, **k: rewrite(real_get(self, *a, **k))
    OrderManager.get_position = lambda self, *a, **k: rewrite(real_pos(self, *a, **k))
    OrderManager.get_current_price = lambda self, *a, **k: real_px(self, *a, **k) * (st["factor"] if mode == "tier1" else 1.0)
    m.check_bot(bot)
    if mode == "tier1":
        time.sleep(5); st["factor"] = 0.94
    for _ in range(4):
        m.check_bot(bot); time.sleep(3)
        OrderManager._get, OrderManager.get_position = real_get, real_pos
        flat = real_pos(om).get("size", 1) == 0
        OrderManager._get = lambda self, *a, **k: rewrite(real_get(self, *a, **k))
        OrderManager.get_position = lambda self, *a, **k: rewrite(real_pos(self, *a, **k))
        if flat: ok = True; break
finally:
    OrderManager._get, OrderManager.get_position, OrderManager.get_current_price = real_get, real_pos, real_px
    left = real_pos(om)
    if left.get("size", 0) != 0:
        print("DRILL FAIL: position still open - emergency close"); om.close_position(size=abs(left["size"]), side="sell"); ok = False
    orders = om._get("/v2/orders", {"product_id": str(om.PRODUCT_ID), "state": "open"}).get("result", [])
    print("open orders left:", len(orders))
    new = open(LOG).read()[off:] if os.path.exists(LOG) else ""
    ev = [l for l in new.splitlines() if re.search(r"speed|critical|dist|auto-?close|S4V3", l, re.I)][-8:]
    print("monitor log evidence:\n" + "\n".join(ev) if ev else "no new monitor log lines")
    note = f"{mode} synthetic-price drill on S4V3 testnet 1 lot; monitor auto-closed to FLAT; open orders left={len(orders)}"
    d = json.load(open("logs/drills.json"))
    d[f"{mode}_{'speed' if mode == 'tier1' else 'liqdist'}_autoclose"] = {"passed": bool(ok and not orders), "date": n.strftime("%Y-%m-%d"), "note": note}
    json.dump(d, open("logs/drills.json", "w"), indent=2)
    print("DRILL", "PASSED" if ok and not orders else "FAILED", "-", note)
