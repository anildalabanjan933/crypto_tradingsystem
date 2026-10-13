#!/usr/bin/env python3
import sys, time, shutil, py_compile
FILES = ["scripts/signal_replay_s4.py", "scripts/signal_replay_s4v2.py", "scripts/signal_replay_s4v3.py"]

H_OLD = "def _write_open_fill_log(csv_path"
H_NEW = '''def _fill_log_fallback(ets, xts, exit_px, tag):
    """Bug6: write a fill_prices row on paths that close without the normal EXIT branch."""
    global open_entry_price, prod_entry_fill
    try:
        import csv as _c, os as _o
        _p = SIGNAL_CSV.replace('signals_', 'fill_prices_')
        _op = SIGNAL_CSV.replace('signals_', 'fill_prices_open_')
        if _o.path.exists(_p):
            with open(_p, newline="") as _f:
                for _r in _c.reader(_f):
                    if _r and _r[0] == ets:
                        _clear_open_fill_log(_op)
                        return
        _bt = None
        if _o.path.exists(SIGNAL_CSV):
            with open(SIGNAL_CSV, newline="") as _f:
                for _r in _c.reader(_f):
                    if len(_r) >= 5 and _r[0] == ets:
                        _bt = _r
        def _num(v):
            try:
                v = str(v).strip()
                return float(v) if v not in ("", "PENDING") else "PENDING"
            except Exception:
                return "PENDING"
        _dir = _bt[2] if _bt else ""
        _lots = _bt[3] if (_bt and len(_bt) > 3) else LOT_SIZE
        _bt_ep = _num(_bt[4]) if _bt else "PENDING"
        _bt_xp = _num(_bt[5]) if (_bt and len(_bt) > 5) else "PENDING"
        _lv_ep = open_entry_price if (open_entry_price and open_entry_price > 0) else "PENDING"
        _lv_xp = round(float(exit_px), 2) if exit_px else "PENDING"
        _chg = float(globals().get("_entry_commission", 0.0) or 0.0)
        _pef = prod_entry_fill.get("v") if isinstance(prod_entry_fill, dict) else prod_entry_fill
        _append_fill_log(_p, ets, xts, _dir, _lots, _bt_ep, _lv_ep, _bt_xp, _lv_xp, _chg, _pef, None)
        _clear_open_fill_log(_op)
        open_entry_price = 0.0
        prod_entry_fill = None
        log.warning(f"[FILL-LOG] {tag} close logged: entry={ets} exit={xts} lv_exit={_lv_xp}")
    except Exception as _fe:
        log.warning(f"[FILL-LOG] {tag} fallback failed: {_fe}")

''' + H_OLD

A_OLD = "                if _manual_exit_ts:\n                    save_ts_file(TS_FILE, _manual_exit_ts)\n"
A_NEW = ("                if _manual_exit_ts:\n"
         "                    _fill_log_fallback(last_known_ts, _manual_exit_ts, None, 'SYNC-MANUAL-EXIT')\n"
         "                    save_ts_file(TS_FILE, _manual_exit_ts)\n")

B_OLD = ("                    if _ex_size == 0:\n                        position = None\n"
         "                        save_ts_file(TS_FILE, _next_row[\"entry_time\"])\n")
B_NEW = ("                    if _ex_size == 0:\n"
         "                        _fill_log_fallback(sig_ts, _next_row[\"entry_time\"], None, 'SELF-HEAL-FLAT')\n"
         "                        position = None\n"
         "                        save_ts_file(TS_FILE, _next_row[\"entry_time\"])\n")

C_OLD = '                    log.info(f"[ORDER] EXIT skipped - exchange already FLAT | ts={_xt}")\n'
C_NEW = C_OLD + "                    _fill_log_fallback(sig_ts, _xt, None, 'EXIT-SKIPPED-FLAT')\n"

ANCH = [(H_OLD, H_NEW), (A_OLD, A_NEW), (B_OLD, B_NEW), (C_OLD, C_NEW)]
srcs = {}
for f in FILES:
    s = open(f).read()
    for i, (o, _) in enumerate(ANCH, 1):
        n = s.count(o)
        if n != 1:
            print(f"ABORT: {f} anchor {i} matched {n}x (need 1). Nothing written."); sys.exit(1)
    srcs[f] = s
ts = time.strftime("%Y%m%d_%H%M%S")
for f, s in srcs.items():
    shutil.copy(f, f"{f}.bak_bug6_{ts}")
    for o, n in ANCH:
        s = s.replace(o, n)
    open(f, "w").write(s)
    py_compile.compile(f, doraise=True)
    print("patched + compiled OK:", f)
print("DONE. Restart live_s4 / live_s4v2 / live_s4v3 only when FLAT. Log in planned_restarts.txt first.")
