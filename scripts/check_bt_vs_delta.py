"""
check_bt_vs_delta.py - Independent comparison: Backtest (BT) trade_log CSV vs
Delta live fills (paired via Audit tab logic). Prints BOTH lists separately,
no forced pairing - for manual side-by-side comparison only.

Usage:
    python3 scripts/check_bt_vs_delta.py --bot s4 --date 2026-09-01
    python3 scripts/check_bt_vs_delta.py --bot s4v2 --date 2026-09-01
"""
import sys
import os
import glob
import argparse
import hashlib
import hmac
import time
import requests
import pandas as pd
import csv
from datetime import datetime, timezone, date, timedelta
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, '.env'))

BASE_URL = 'https://cdn-ind.testnet.deltaex.org'
KEY_MAP = {
    's4': ('S4_API_KEY', 'S4_API_SECRET'),
    's4v2': ('S4V2_API_KEY', 'S4V2_API_SECRET'),
    's4v3': ('S4V3_API_KEY', 'S4V3_API_SECRET'),
    'testmember1_s4': ('TESTMEMBER1_S4_API_KEY', 'TESTMEMBER1_S4_API_SECRET'),
}
BT_CSV_PATTERN = {
    's4':   "output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv",
    's4v2': "output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv",
    's4v3': "output/trade_log_RenkoSMIIOCrossV3Strategy_BTCUSD_*.csv",
}

def get_delta_fills(bot, date_str):
    k, s = KEY_MAP[bot]
    api_key = os.environ.get(k)
    api_secret = os.environ.get(s)
    if not api_key or not api_secret:
        raise RuntimeError(f"Missing API credentials for bot={bot}")
    y, m, d = map(int, date_str.split('-'))
    IST_OFFSET = timedelta(hours=5, minutes=30)
    # Widened by 1 day each side so overnight trades (entry on prev IST day,
    # exit on target IST day, or vice versa) aren't cut off mid-fetch.
    start_dt = (datetime(y, m, d, 0, 0, 0) - timedelta(days=1) - IST_OFFSET).replace(tzinfo=timezone.utc)
    end_dt = (datetime(y, m, d, 23, 59, 59) + timedelta(days=1) - IST_OFFSET).replace(tzinfo=timezone.utc)
    start_us = int(start_dt.timestamp() * 1_000_000)
    end_us = int(end_dt.timestamp() * 1_000_000)
    method = 'GET'
    timestamp = str(int(time.time()))
    path = '/v2/fills'
    url = f'{BASE_URL}{path}'
    query = {"product_ids": 84, "start_time": start_us, "end_time": end_us, "page_size": 100}
    query_string = '?' + '&'.join([f'{qk}={qv}' for qk, qv in query.items()])
    sig_data = method + timestamp + path + query_string + ''
    signature = hmac.new(api_secret.encode(), sig_data.encode(), hashlib.sha256).hexdigest()
    headers = {'api-key': api_key, 'timestamp': timestamp, 'signature': signature,
               'User-Agent': 'python-rest-client', 'Content-Type': 'application/json'}
    r = requests.get(url, params=query, headers=headers, timeout=(3, 27))
    r.raise_for_status()
    return r.json().get('result', [])

def _merge_partial_fills_local(fills_sorted):
    """
    Independent copy of dashboard/trade_audit_tab.py::_merge_partial_fills_audit.
    Merges same-side fills sharing order_id within 1 second (Delta partial-fill
    splitting) into a single fill. Kept standalone to avoid cross-file coupling.
    """
    if not fills_sorted:
        return fills_sorted
    merged = []
    i = 0
    while i < len(fills_sorted):
        cur = dict(fills_sorted[i])
        j = i + 1
        while j < len(fills_sorted):
            nxt = fills_sorted[j]
            same_side = str(nxt.get("side","")).upper() == str(cur.get("side","")).upper()
            same_order = str(nxt.get("order_id","")) == str(cur.get("order_id",""))
            try:
                t1 = datetime.fromisoformat(str(cur.get("created_at","")).replace("Z",""))
                t2 = datetime.fromisoformat(str(nxt.get("created_at","")).replace("Z",""))
                close_time = abs((t2 - t1).total_seconds()) <= 1.0
            except Exception:
                close_time = False
            if same_side and same_order and close_time:
                s1 = float(cur.get("size",0) or 0)
                s2 = float(nxt.get("size",0) or 0)
                tot = s1 + s2
                if tot > 0:
                    cur["price"] = (float(cur.get("price",0) or 0)*s1 + float(nxt.get("price",0) or 0)*s2) / tot
                cur["size"] = tot
                cur["commission"] = float(cur.get("commission",0) or 0) + float(nxt.get("commission",0) or 0)
                cur["meta_data"] = nxt.get("meta_data", cur.get("meta_data", {}))
                j += 1
            else:
                break
        merged.append(cur)
        i = j
    return merged


def _filter_by_ist_date_local(lv_rows, date_str):
    """
    Keeps a paired trade only if its entry date (IST) OR exit date (IST)
    equals the target date - mirrors the same entry-OR-exit day-boundary
    rule get_bt_rows() already applies, so BT and Delta fills use identical
    day-boundary logic instead of a strict same-day cutoff that silently
    drops overnight trades.
    """
    y, m, d = map(int, date_str.split('-'))
    target = date(y, m, d)
    IST_OFFSET = timedelta(hours=5, minutes=30)
    filtered = []
    for r in lv_rows:
        try:
            et = datetime.fromisoformat(str(r['entry_ts_raw']).replace('Z', '+00:00'))
            xt = datetime.fromisoformat(str(r['exit_ts_raw']).replace('Z', '+00:00'))
            et_ist_date = (et + IST_OFFSET).date()
            xt_ist_date = (xt + IST_OFFSET).date()
            if et_ist_date == target or xt_ist_date == target:
                filtered.append(r)
        except Exception:
            filtered.append(r)  # fail-safe: keep row rather than silently drop on parse error
    return filtered


def _aggregate_partial_exits_local(pairs):
    """
    Merges multiple pairs sharing the same entry (same entry_ts_raw + dir +
    entry_p) into a single trade record. This happens when one entry
    position is closed via multiple separate exit fills (partial closes) -
    without this, one real trade appears as several duplicate-entry rows
    with different exits, which both confuses the printed output and
    pollutes BT-vs-Live matching (only 1 fragment can match the BT row,
    the rest get wrongly counted as extra_live_trade).
    """
    if not pairs:
        return pairs
    groups = {}
    order = []
    for p in pairs:
        key = (p['entry_ts_raw'], p['dir'], p['entry_p'])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(p)

    aggregated = []
    for key in order:
        legs = groups[key]
        if len(legs) == 1:
            aggregated.append(legs[0])
            continue
        legs_sorted = sorted(legs, key=lambda x: x['exit_ts_raw'])
        total_lot = sum(l['lot'] for l in legs_sorted)
        total_pnl = sum(l['pnl_usd'] for l in legs_sorted)
        total_charges = sum(l['charges'] for l in legs_sorted)
        if total_lot > 1e-9:
            weighted_exit_p = sum(l['exit_p'] * l['lot'] for l in legs_sorted) / total_lot
        else:
            weighted_exit_p = legs_sorted[-1]['exit_p']
        last_leg = legs_sorted[-1]
        aggregated.append({
            "dir": last_leg['dir'],
            "entry_ts_raw": last_leg['entry_ts_raw'],
            "exit_ts_raw": last_leg['exit_ts_raw'],
            "entry_p": last_leg['entry_p'],
            "exit_p": weighted_exit_p,
            "lot": total_lot,
            "charges": total_charges,
            "pnl_usd": total_pnl,
            "exit_order_id": last_leg['exit_order_id'],
            "exit_order_closed": last_leg['exit_order_closed'],
        })
    return aggregated


def _pair_fills_local(fills):
    """
    Independent copy of dashboard/trade_audit_tab.py::_pair_fills_audit.
    Uses Delta's per-fill realized PnL (meta_data.new_position.realized_pnl)
    via baseline-delta extraction (cumulative snapshot minus lifecycle
    baseline, reset to 0 whenever position returns to size == 0).
    Kept standalone to avoid cross-file coupling with dashboard code.
    If dashboard/trade_audit_tab.py's pairing logic is ever bugfixed,
    this copy must be manually re-synced.
    """
    fills_sorted = sorted(fills, key=lambda f: f.get("created_at", ""))
    fills_sorted = _merge_partial_fills_local(fills_sorted)

    queue = []
    pairs = []
    baseline = 0.0

    for f in fills_sorted:
        side = str(f.get("side", "")).upper()
        size = float(f.get("size", 0) or 0)
        if size <= 0:
            continue
        price = float(f.get("price", 0) or 0)
        time = f.get("created_at", "")
        commission = abs(float(f.get("commission", 0) or 0))
        comm_per_unit = commission / size if size else 0.0
        meta = f.get("meta_data", {}) or {}
        new_pos = meta.get("new_position", {}) or {}
        raw_cumulative = float(new_pos.get("realized_pnl", 0) or 0)
        pos_size_after = new_pos.get("size", None)
        _fill_order_id = str(f.get("order_id", ""))
        _fill_order_unfilled = float(meta.get("order_unfilled_size", 0) or 0)
        _fill_order_closed = _fill_order_unfilled <= 1e-9

        realized_pnl = raw_cumulative - baseline

        avail_opposite = sum(q["remaining"] for q in queue if q["side"] != side)
        closed_qty = min(size, avail_opposite)
        remaining_to_close = closed_qty

        while remaining_to_close > 1e-9 and queue and queue[0]["side"] != side:
            head = queue[0]
            match_size = min(remaining_to_close, head["remaining"])
            frac = (match_size / closed_qty) if closed_qty > 1e-9 else 0.0
            chunk_pnl = realized_pnl * frac
            chunk_exit_comm = comm_per_unit * match_size
            chunk_entry_comm = head["comm_per_unit"] * match_size
            _dir = "LONG" if head["side"] == "BUY" else "SHORT"
            pairs.append({
                "dir": _dir,
                "entry_ts_raw": head["time"],
                "exit_ts_raw": time,
                "entry_p": head["price"],
                "exit_p": price,
                "lot": match_size,
                "charges": chunk_exit_comm + chunk_entry_comm,
                "pnl_usd": chunk_pnl,
                "exit_order_id": _fill_order_id,
                "exit_order_closed": _fill_order_closed,
            })
            head["remaining"] -= match_size
            remaining_to_close -= match_size
            if head["remaining"] <= 1e-9:
                queue.pop(0)

        opening_qty = size - closed_qty
        if opening_qty > 1e-9 and pos_size_after != 0:
            queue.append({"remaining": opening_qty, "price": price, "time": time,
                          "side": side, "comm_per_unit": comm_per_unit})

        baseline = 0.0 if pos_size_after == 0 else raw_cumulative

    return _aggregate_partial_exits_local(pairs)

def get_bt_rows(bot, date_str):
    pattern = BT_CSV_PATTERN[bot]
    files = sorted(glob.glob(os.path.join(PROJECT_ROOT, pattern)), reverse=True)
    if not files:
        return []
    dfs = []
    for fpath in files:
        try:
            df_part = pd.read_csv(fpath)
            if 'entry_datetime' in df_part.columns:
                dfs.append(df_part)
        except Exception:
            continue
    if not dfs:
        return []
    df = pd.concat(dfs, ignore_index=True)
    df['entry_datetime'] = pd.to_datetime(df['entry_datetime'], errors='coerce')
    df['exit_datetime'] = pd.to_datetime(df['exit_datetime'], errors='coerce')
    y, m, d = map(int, date_str.split('-'))
    target = date(y, m, d)
    IST_OFFSET = timedelta(hours=5, minutes=30)
    entry_ist_date = (df['entry_datetime'] + IST_OFFSET).dt.date
    exit_ist_date = (df['exit_datetime'] + IST_OFFSET).dt.date
    df = df[(entry_ist_date == target) | (exit_ist_date == target)]
    df = df.drop_duplicates(subset=['entry_datetime', 'exit_datetime', 'entry_price', 'exit_price'])
    df = df.sort_values('entry_datetime')
    tf_min = 120 if bot == 's4' else 30
    if bot == 's4v3':
        tf_min = 240
    _off = timedelta(minutes=tf_min)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            'dir': str(r.get('direction', '')).upper(),
            'entry_ts': str(r.get('entry_datetime', pd.NaT) + _off),
            'exit_ts': str(r.get('exit_datetime', pd.NaT) + _off),
            'entry_p': float(r.get('entry_price', 0)),
            'exit_p': float(r.get('exit_price', 0)),
            'net_pnl_usd': float(r.get('net_pnl', 0)),
        })
    return rows

# ===== Additional checks: entry/exit delay + big loss flag =====
def analyze_live_trades(lv_rows, bot):
    """Adds delay_sec (vs nearest clean boundary) and big_loss flag to each live trade."""
    tf_min = 120 if bot == 's4' else 30
    if bot == 's4v3':
        tf_min = 240
    BIG_LOSS_USD = 40.0  # ~Rs4,000 backtest single-trade ceiling / ~84 INR rate

    for r in lv_rows:
        try:
            entry_dt = datetime.fromisoformat(r['entry_ts_raw'].replace('Z', '+00:00'))
            minute = entry_dt.minute
            hour = entry_dt.hour
            total_min = hour * 60 + minute
            nearest_boundary_min = round(total_min / tf_min) * tf_min
            boundary_dt = entry_dt.replace(hour=0, minute=0, second=0, microsecond=0) + \
                __import__('datetime').timedelta(minutes=nearest_boundary_min)
            delay_sec = (entry_dt - boundary_dt).total_seconds()
            r['entry_delay_sec'] = round(delay_sec, 1)
        except Exception:
            r['entry_delay_sec'] = None
        try:
            exit_dt = datetime.fromisoformat(r['exit_ts_raw'].replace('Z', '+00:00'))
            minute = exit_dt.minute
            hour = exit_dt.hour
            total_min = hour * 60 + minute
            nearest_boundary_min = round(total_min / tf_min) * tf_min
            boundary_dt = exit_dt.replace(hour=0, minute=0, second=0, microsecond=0) + \
                __import__('datetime').timedelta(minutes=nearest_boundary_min)
            exit_delay_sec = (exit_dt - boundary_dt).total_seconds()
            r['exit_delay_sec'] = round(exit_delay_sec, 1)
        except Exception:
            r['exit_delay_sec'] = None
        r['big_loss_flag'] = r.get('pnl_usd', 0) < -BIG_LOSS_USD
    return lv_rows


MISMATCH_CSV = os.path.join(PROJECT_ROOT, "logs", "bt_live_mismatch.csv")
MISMATCH_CSV_MAX_BYTES = 20 * 1024 * 1024

def _rotate_mismatch_csv_if_needed():
    if os.path.exists(MISMATCH_CSV) and os.path.getsize(MISMATCH_CSV) > MISMATCH_CSV_MAX_BYTES:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        os.rename(MISMATCH_CSV, f"{MISMATCH_CSV}.{ts}.bak")

def _ensure_mismatch_csv_header():
    if not os.path.exists(MISMATCH_CSV):
        with open(MISMATCH_CSV, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "logged_at","bot","date","direction_bt","direction_live","direction_mismatch",
                "entry_ts_bt","entry_ts_live","entry_price_bt","entry_price_live","entry_slippage_usd",
                "exit_ts_bt","exit_ts_live","exit_price_bt","exit_price_live","exit_slippage_usd",
                "bt_pnl_usd","live_pnl_usd","net_pnl_gap_usd","missed_trade","extra_live_trade"
            ])

def match_and_log(bt_rows, lv_rows, bot, date_str):
    tf_min = 120 if bot == 's4' else 30
    if bot == 's4v3':
        tf_min = 240
    match_window_sec = (tf_min + 15) * 60
    _rotate_mismatch_csv_if_needed()
    _ensure_mismatch_csv_header()
    now_iso = datetime.now(timezone.utc).isoformat()
    matched_live_idx = set()
    rows_to_write = []
    unmatched_bt = []

    # Pass 1: same-direction matching within time window (original behavior)
    for bt in bt_rows:
        best_j = None
        best_dt = None
        for j, lv in enumerate(lv_rows):
            if j in matched_live_idx:
                continue
            if lv['dir'] != bt['dir']:
                continue
            try:
                bt_dt = pd.to_datetime(bt['entry_ts'])
                if bt_dt.tzinfo is None:
                    bt_dt = bt_dt.tz_localize('UTC')
                lv_dt = pd.to_datetime(lv['entry_ts_raw'])
                if lv_dt.tzinfo is None:
                    lv_dt = lv_dt.tz_localize('UTC')
                diff = abs((bt_dt - lv_dt).total_seconds())
            except Exception:
                continue
            if diff <= match_window_sec and (best_dt is None or diff < best_dt):
                best_dt = diff
                best_j = j
        if best_j is not None:
            lv = lv_rows[best_j]
            matched_live_idx.add(best_j)
            entry_slip = round(lv['entry_p'] - bt['entry_p'], 2)
            exit_slip = round(lv['exit_p'] - bt['exit_p'], 2)
            pnl_gap = round(lv['pnl_usd'] - bt['net_pnl_usd'], 2)
            rows_to_write.append([
                now_iso, bot, date_str, bt['dir'], lv['dir'], bt['dir'] != lv['dir'],
                bt['entry_ts'], lv['entry_ts_raw'], bt['entry_p'], lv['entry_p'], entry_slip,
                bt['exit_ts'], lv['exit_ts_raw'], bt['exit_p'], lv['exit_p'], exit_slip,
                bt['net_pnl_usd'], lv['pnl_usd'], pnl_gap, False, False
            ])
        else:
            unmatched_bt.append(bt)

    # Pass 2: retry BT rows still unmatched against remaining live rows,
    # regardless of direction - lets direction_mismatch=True actually get
    # logged instead of every wrong-direction case silently becoming
    # "missed_trade".
    still_unmatched_bt = []
    for bt in unmatched_bt:
        best_j = None
        best_dt = None
        for j, lv in enumerate(lv_rows):
            if j in matched_live_idx:
                continue
            try:
                bt_dt = pd.to_datetime(bt['entry_ts'])
                if bt_dt.tzinfo is None:
                    bt_dt = bt_dt.tz_localize('UTC')
                lv_dt = pd.to_datetime(lv['entry_ts_raw'])
                if lv_dt.tzinfo is None:
                    lv_dt = lv_dt.tz_localize('UTC')
                diff = abs((bt_dt - lv_dt).total_seconds())
            except Exception:
                continue
            if diff <= match_window_sec and (best_dt is None or diff < best_dt):
                best_dt = diff
                best_j = j
        if best_j is not None:
            lv = lv_rows[best_j]
            matched_live_idx.add(best_j)
            entry_slip = round(lv['entry_p'] - bt['entry_p'], 2)
            exit_slip = round(lv['exit_p'] - bt['exit_p'], 2)
            pnl_gap = round(lv['pnl_usd'] - bt['net_pnl_usd'], 2)
            rows_to_write.append([
                now_iso, bot, date_str, bt['dir'], lv['dir'], bt['dir'] != lv['dir'],
                bt['entry_ts'], lv['entry_ts_raw'], bt['entry_p'], lv['entry_p'], entry_slip,
                bt['exit_ts'], lv['exit_ts_raw'], bt['exit_p'], lv['exit_p'], exit_slip,
                bt['net_pnl_usd'], lv['pnl_usd'], pnl_gap, False, False
            ])
        else:
            still_unmatched_bt.append(bt)

    # Truly missed BT trades - no live counterpart in either pass
    for bt in still_unmatched_bt:
        rows_to_write.append([
            now_iso, bot, date_str, bt['dir'], "", False,
            bt['entry_ts'], "", bt['entry_p'], "", "",
            bt['exit_ts'], "", bt['exit_p'], "", "",
            bt['net_pnl_usd'], "", "", True, False
        ])

    # Extra live trades - executed with no BT counterpart at all
    for j, lv in enumerate(lv_rows):
        if j not in matched_live_idx:
            rows_to_write.append([
                now_iso, bot, date_str, "", lv['dir'], False,
                "", lv['entry_ts_raw'], "", lv['entry_p'], "",
                "", lv['exit_ts_raw'], "", lv['exit_p'], "",
                "", lv['pnl_usd'], "", False, True
            ])

    with open(MISMATCH_CSV, "a", newline="") as f:
        w = csv.writer(f)
        w.writerows(rows_to_write)
        f.flush()
        os.fsync(f.fileno())

    print(f"\nLogged {len(rows_to_write)} row(s) to {MISMATCH_CSV}")
    return rows_to_write

ISSUE_TRACKER_CSV = os.path.join(PROJECT_ROOT, "logs", "issue_tracker_trades.csv")

def cross_reference_issue_tracker(bot, date_str, rows_to_write):
    """
    Fix E: cross-references today's bt_live_mismatch rows (in-memory, just
    written) against logs/issue_tracker_trades.csv on (bot, entry_ts_live)
    to pull existing verdict/repeat_count if a human/prior run already
    tagged that trade. Read-only against issue_tracker_trades.csv - never
    writes or modifies it. Print-only report, no new file.
    """
    if not os.path.exists(ISSUE_TRACKER_CSV):
        print(f"\n(No {ISSUE_TRACKER_CSV} found - skipping cross-reference)")
        return
    try:
        it_df = pd.read_csv(ISSUE_TRACKER_CSV)
    except Exception as e:
        print(f"\n(Could not read issue_tracker_trades.csv: {e})")
        return
    if 'bot' not in it_df.columns or 'entry_ts' not in it_df.columns:
        print("\n(issue_tracker_trades.csv missing 'bot' or 'entry_ts' column - skipping)")
        return

    it_df['bot_norm'] = it_df['bot'].astype(str).str.lower()
    it_df['entry_ts_parsed'] = pd.to_datetime(it_df['entry_ts'], errors='coerce')

    # Fix E correction (28-Sep-2026): use same per-bot window as Fix A instead
    # of a flat 15-min tolerance - flat window missed real matches for
    # S4 (needs 135min) and S4V3 (needs 255min) due to confirmation-lag delay
    # after candle close, not cron-timing congestion.
    _tf_min = 120 if bot == 's4' else 30
    if bot == 's4v3':
        _tf_min = 240
    _match_window_sec = (_tf_min + 15) * 60

    print(f"\n========== CROSS-REFERENCE WITH issue_tracker_trades.csv - {bot.upper()} - {date_str} ==========")
    match_count = 0
    matched_it_idx = set()  # exclusivity guard - each issue_tracker row claimed once
    for row in rows_to_write:
        row_bot = row[1]
        entry_ts_live = row[7]
        if not entry_ts_live:
            continue
        try:
            lv_dt = pd.to_datetime(entry_ts_live, errors='coerce')
            if lv_dt is not None and not pd.isna(lv_dt) and lv_dt.tzinfo is not None:
                lv_dt = lv_dt.tz_localize(None)
        except Exception:
            continue
        if pd.isna(lv_dt):
            continue

        candidates = it_df[(it_df['bot_norm'] == row_bot.lower()) & (~it_df.index.isin(matched_it_idx))]
        if candidates.empty:
            continue

        diffs = (candidates['entry_ts_parsed'] - lv_dt).abs()
        best_idx = diffs.idxmin() if not diffs.empty else None
        if best_idx is None or pd.isna(diffs.loc[best_idx]):
            continue
        if diffs.loc[best_idx].total_seconds() > _match_window_sec:
            continue

        matched_it_idx.add(best_idx)
        match = candidates.loc[best_idx]
        match_count += 1
        print(f"LIVE entry={entry_ts_live} -> issue_tracker verdict={match.get('verdict','')} "
              f"repeat_count={match.get('repeat_count','')} "
              f"bt_lv_pnl_gap_$={match.get('bt_lv_pnl_gap_$','')}")

    if match_count == 0:
        print("No matching rows found in issue_tracker_trades.csv for this date/bot.")
    print(f"Cross-reference matches found: {match_count}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bot', required=True, choices=list(KEY_MAP.keys()))
    parser.add_argument('--date', required=True, help='YYYY-MM-DD (UTC)')
    args = parser.parse_args()

    print(f"\n========== BT (BACKTEST) TRADES - {args.bot.upper()} - {args.date} ==========")
    bt_rows = get_bt_rows(args.bot, args.date)
    if not bt_rows:
        print("No BT rows found for this date.")
    for i, r in enumerate(bt_rows, 1):
        print(f"{i}. {r['dir']} | entry={r['entry_ts']} @ {r['entry_p']} | exit={r['exit_ts']} @ {r['exit_p']} | net_pnl=${r['net_pnl_usd']:.2f}")
    print(f"BT TOTAL TRADES: {len(bt_rows)}")

    print(f"\n========== DELTA LIVE FILLS (via Audit pairing) - {args.bot.upper()} - {args.date} ==========")
    fills = get_delta_fills(args.bot, args.date)
    lv_rows = _pair_fills_local(fills)
    lv_rows = _filter_by_ist_date_local(lv_rows, args.date)
    lv_rows = analyze_live_trades(lv_rows, args.bot)
    if not lv_rows:
        print("No live trades found for this date.")
    for i, r in enumerate(lv_rows, 1):
        _edelay = r.get('entry_delay_sec')
        _edelay_str = f"{_edelay}s" if _edelay is not None else "N/A"
        _xdelay = r.get('exit_delay_sec')
        _xdelay_str = f"{_xdelay}s" if _xdelay is not None else "N/A"
        _loss_flag = "  !! BIG LOSS !!" if r.get('big_loss_flag') else ""
        print(f"{i}. {r['dir']} | entry={r['entry_ts_raw']} @ {r['entry_p']} (entry_delay={_edelay_str}) | exit={r['exit_ts_raw']} @ {r['exit_p']} (exit_delay={_xdelay_str}) | pnl=${r['pnl_usd']:.2f}{_loss_flag}")
    print(f"LIVE TOTAL TRADES: {len(lv_rows)}")

    print(f"\n========== SUMMARY (manual compare - no auto-pairing) ==========")
    print(f"BT trade count:   {len(bt_rows)}")
    print(f"LIVE trade count: {len(lv_rows)}")
    if len(bt_rows) != len(lv_rows):
        print("!! COUNT MISMATCH - review both lists above manually !!")
    else:
        print("Counts match - review prices/times/pnl above manually for slippage/delay.")

    _rows_written = match_and_log(bt_rows, lv_rows, args.bot, args.date)
    cross_reference_issue_tracker(args.bot, args.date, _rows_written)

if __name__ == '__main__':
    main()
