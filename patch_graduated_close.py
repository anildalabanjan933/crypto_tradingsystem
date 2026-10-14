#!/usr/bin/env python3
"""
patch_graduated_close.py - graduated final-stage band in close_position().
After 180s of failed closing: final resting band widens to 2% of mark,
after 300s to 3% of mark (always a limit order, never market). Sits between
the $1000 capped stage and the 10% Tier 0 SL.
Target: engine/order_manager.py. Anchor must match EXACTLY ONCE, else abort.
Backup: <file>.bak_gradclose_<ts>. py_compile after patching.
Run from ~/crypto_tradingsystem:  python3 patch_graduated_close.py
"""
import sys, time, shutil, py_compile

F = "engine/order_manager.py"
OLD = '            limit_price = round(ref_price - _current_band, 1) if side == "sell" else round(ref_price + _current_band, 1)\n'
NEW = (
'            if _final_cap_active:\n'
'                _stage_pct = 0.0\n'
'                if _elapsed_total >= 300:\n'
'                    _stage_pct = 0.03\n'
'                elif _elapsed_total >= 180:\n'
'                    _stage_pct = 0.02\n'
'                if _stage_pct > 0:\n'
'                    _wide_band = round(ref_price * _stage_pct, 1)\n'
'                    if _wide_band > _current_band:\n'
'                        _current_band = _wide_band\n'
'                        logging.critical(f"[OrderManager] CLOSE GRADUATED ESCALATION - elapsed={_elapsed_total:.0f}s band widened to ${_current_band:.0f} ({_stage_pct*100:.0f}% of mark, limit order, capped well below 10% SL)")\n'
'                        try:\n'
'                            send_alert(f"CTS CLOSE ESCALATION (stage {int(_stage_pct*100)}%)\\nExit still not filled after {_elapsed_total:.0f}s - widening limit band to ${_current_band:.0f} (still a limit order, far below 10% emergency SL)\\nSide: {side.upper()} | Size: {close_size}")\n'
'                        except Exception:\n'
'                            pass\n'
) + OLD

s = open(F).read()
n = s.count(OLD)
if n != 1:
    print(f"ABORT: {F} anchor matched {n}x (need exactly 1). Nothing written.")
    sys.exit(1)

ts = time.strftime("%Y%m%d_%H%M%S")
shutil.copy(F, f"{F}.bak_gradclose_{ts}")
open(F, "w").write(s.replace(OLD, NEW))
py_compile.compile(F, doraise=True)
print(f"patched + compiled OK: {F}")
print("DONE. Restart live_s4 / live_s4v2 / live_s4v3 / position_risk_monitor only when FLAT.")
