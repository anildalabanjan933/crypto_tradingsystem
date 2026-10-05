import sys, datetime
sys.path.insert(0, '.')
import dashboard.trade_audit_tab as tat
import dashboard.streamlit_app as app
import pandas as pd

from_date = datetime.date(2026,9,12)
to_date   = datetime.date.today() + datetime.timedelta(days=1)
inr_rate = 84.0

TF_MINUTES = {'S4': 120, 'S4V2': 30, 'S4V3': 240}
MATCH_TOLERANCE_SEC = 300

def num(v):
    try: return float(v)
    except Exception: return 0.0

def parse_ts(raw):
    try: return pd.to_datetime(str(raw).replace('T',' ').replace('Z',''))
    except Exception: return None

print(f'AUDIT CHECK (BASELINE #12): {from_date} to {to_date}')
print('='*90)

for strat in ['S4','S4V2','S4V3']:
    tf_min = TF_MINUTES[strat]
    bt_raw = tat._get_bt_rows_audit(strat, from_date, to_date, app._load14, inr_rate)
    bt_rows = tat._apply_bt_adjustments_audit(bt_raw, 100, 5, inr_rate)
    lv_rows = tat._get_live_rows_audit(strat, from_date, to_date, app._fetch_account_fills_cached_audit, inr_rate)
    bt_pnl = sum(num(r.get('net_pnl_inr')) for r in bt_rows)
    lv_pnl = sum(num(r.get('net_pnl_inr')) for r in lv_rows)

    print(f'\n{strat} | BT trades={len(bt_rows)} | LV trades={len(lv_rows)} | BT_PnL=Rs{round(bt_pnl,2)} | LV_PnL=Rs{round(lv_pnl,2)} | GAP=Rs{round(bt_pnl-lv_pnl,2)}')
    print('-'*90)

    used = set()
    missed = 0
    for bt in bt_rows:
        bt_et_raw = parse_ts(bt.get('entry_ts_raw'))
        if bt_et_raw is None:
            print(f'  OPEN/PENDING | BT {bt.get("dir")} entry={bt.get("entry_ts_raw")} (no exit yet)')
            continue
        bt_et_shifted = bt_et_raw + pd.Timedelta(minutes=tf_min)
        best=None; bi=None; bd=None
        for i, lv in enumerate(lv_rows):
            if i in used: continue
            lv_et = parse_ts(lv.get('entry_ts_raw'))
            if lv_et is None: continue
            diff = abs((bt_et_shifted - lv_et).total_seconds())
            if diff < MATCH_TOLERANCE_SEC and (bd is None or diff < bd):
                best, bi, bd = lv, i, diff

        if best is None:
            missed += 1
            print(f'  MISSED TRADE | BT {bt.get("dir")} label={bt.get("entry_ts_raw")} exit={bt.get("exit_ts_raw")} (expected live fire ~{bt_et_shifted}) | BT_PnL=Rs{round(num(bt.get("net_pnl_inr")),2)}')
        else:
            used.add(bi)
            dir_match = 'OK' if bt.get('dir')==best.get('dir') else 'MISMATCH'
            bt_ep = num(bt.get('entry_p')); lv_ep = num(best.get('entry_p'))
            bt_xp = num(bt.get('exit_p'));  lv_xp = num(best.get('exit_p'))
            entry_slip = round((lv_ep - bt_ep) * 100 * 0.001, 2)
            exit_slip  = round((lv_xp - bt_xp) * 100 * 0.001, 2)
            pnl_gap = round(num(bt.get('net_pnl_inr')) - num(best.get('net_pnl_inr')), 2)
            print(f'  MATCHED [{dir_match}] | {bt.get("dir")} | BT entry={bt_ep} exit={bt_xp} | LV entry={lv_ep} exit={lv_xp} | EntrySlip=${entry_slip} ExitSlip=${exit_slip} | PnL_Gap=Rs{pnl_gap}')

    for i, lv in enumerate(lv_rows):
        if i not in used:
            print(f'  EXTRA LIVE (no BT match) | {lv.get("dir")} entry={lv.get("entry_ts_raw")} exit={lv.get("exit_ts_raw")}')

    print(f'  >> {strat} SUMMARY: matched={len(used)} missed={missed} extra_live={len(lv_rows)-len(used)}')

print('\n'+'='*90)
print('DONE')
