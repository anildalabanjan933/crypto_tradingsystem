#!/usr/bin/env python3
import sys, time, shutil, py_compile

FILES = ["scripts/signal_replay_s4.py",
         "scripts/signal_replay_s4v2.py",
         "scripts/signal_replay_s4v3.py"]

A1_OLD = "                        _updated3 = False\n"
A1_NEW = ("                        _updated3 = False\n"
          "                        _fl_snap = None\n")

A2_OLD = "                                _r3[1] = _sync_exit_ts\n"
A2_NEW = ("                                _fl_snap = (_r3[0], _r3[2] if len(_r3) > 2 else '', "
          "_r3[3] if len(_r3) > 3 else '', _r3[4] if len(_r3) > 4 else '')\n"
          "                                _r3[1] = _sync_exit_ts\n")

A3_OLD = ('                        log.info(f"[SYNC] Lock advanced past synced-flat signal '
          'to exit_time={_sync_exit_ts}")\n')
A3_NEW = (
"                        if _fl_snap is not None:\n"
"                            try:\n"
"                                _fl_ets, _fl_dir, _fl_lots, _fl_bt_ep = _fl_snap\n"
"                                _fl_path = _sig_csv.replace('signals_', 'fill_prices_')\n"
"                                _fl_open = _sig_csv.replace('signals_', 'fill_prices_open_')\n"
"                                _fl_bt_ep = float(_fl_bt_ep) if str(_fl_bt_ep).strip() not in ('', 'PENDING') else 'PENDING'\n"
"                                _fl_lv_ep = open_entry_price if (open_entry_price and open_entry_price > 0) else 'PENDING'\n"
"                                _fl_lv_xp = round(float(_sync_price), 2) if _sync_price else 'PENDING'\n"
"                                _fl_chg = float(_entry_commission) if '_entry_commission' in dir() else 0.0\n"
"                                _fl_pef = (prod_entry_fill.get('v') if isinstance(prod_entry_fill, dict) else prod_entry_fill)\n"
"                                # lv_exit = price at SYNC detection (estimate, NOT a real fill); prod_exit = NA (no bot exit happened)\n"
"                                _append_fill_log(_fl_path, _fl_ets, _sync_exit_ts, _fl_dir, _fl_lots, _fl_bt_ep, _fl_lv_ep, 'PENDING', _fl_lv_xp, _fl_chg, _fl_pef, None)\n"
"                                _clear_open_fill_log(_fl_open)\n"
"                                open_entry_price = 0.0\n"
"                                prod_entry_fill = None\n"
"                                log.warning(f'[FILL-LOG] SYNC-flat close logged: entry={_fl_ets} exit={_sync_exit_ts} lv_exit=ESTIMATE({_fl_lv_xp})')\n"
"                            except Exception as _fl_e:\n"
"                                log.warning(f'[FILL-LOG] SYNC-flat fill log failed: {_fl_e}')\n"
+ A3_OLD)

ANCHORS = [(A1_OLD, A1_NEW), (A2_OLD, A2_NEW), (A3_OLD, A3_NEW)]

srcs = {}
for f in FILES:
    s = open(f).read()
    for i, (old, _) in enumerate(ANCHORS, 1):
        n = s.count(old)
        if n != 1:
            print(f"ABORT: {f} anchor {i} matched {n}x (need exactly 1). Nothing written.")
            sys.exit(1)
    srcs[f] = s

ts = time.strftime("%Y%m%d_%H%M%S")
for f, s in srcs.items():
    shutil.copy(f, f"{f}.bak_bug3_{ts}")
    for old, new in ANCHORS:
        s = s.replace(old, new)
    open(f, "w").write(s)
    py_compile.compile(f, doraise=True)
    print(f"patched + compiled OK: {f}")
print("DONE. Restart live_s4 / live_s4v2 / live_s4v3 only when FLAT.")
