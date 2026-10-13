#!/usr/bin/env python3
import sys, time, shutil, py_compile
F = "scripts/generate_signals.py"
OLD = '    trades = result.get("trades", [])\n    log.info(f"[GENERATE] {label}: {len(trades)} trades generated")\n'
NEW = '''    trades = result.get("trades", [])
    # BUG7: drop trades whose exit bar has not closed yet (forming candle) - trade_log only
    try:
        import pandas as _pd_b7
        _tfm_b7 = {"30m": 30, "1h": 60, "2h": 120, "4h": 240}.get(params.get("renko_timeframe"), 0)
        if _tfm_b7:
            _now_b7 = _pd_b7.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
            _kept_b7 = []
            for _t7 in trades:
                try:
                    _x7 = _pd_b7.Timestamp(str(_t7.get("exit_datetime", "")).replace("T", " ")[:19])
                    if _x7 + _pd_b7.Timedelta(minutes=_tfm_b7) > _now_b7:
                        log.info(f"[GENERATE] {label}: BUG7 dropped trade with unclosed exit bar entry={_t7.get('entry_datetime')} exit={_t7.get('exit_datetime')}")
                        continue
                except Exception:
                    pass
                _kept_b7.append(_t7)
            trades = _kept_b7
    except Exception as _e7:
        log.warning(f"[GENERATE] {label}: BUG7 filter failed (trades kept as-is): {_e7}")
    log.info(f"[GENERATE] {label}: {len(trades)} trades generated")
'''
s = open(F).read()
n = s.count(OLD)
if n != 1:
    print(f"ABORT: anchor matched {n}x (need 1). Nothing written."); sys.exit(1)
ts = time.strftime("%Y%m%d_%H%M%S")
shutil.copy(F, f"{F}.bak_bug7_{ts}")
open(F, "w").write(s.replace(OLD, NEW))
py_compile.compile(F, doraise=True)
print("patched + compiled OK:", F)
