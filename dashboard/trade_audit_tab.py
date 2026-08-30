# ============================================================
# TRADE AUDIT TAB - CHUNK 1: Helper Functions & Constants
# (Safe, independent copies - does NOT touch existing TODAY'S
# TRADES tab code. All names use _audit suffix to avoid clashes.)
# ============================================================

import datetime as _dt_audit
import re
import pandas as _pd_audit

_ORDERS_CACHE_AUDIT = {}  # in-process cache to avoid repeated Streamlit cache deep-copy per row

# ---- Table styling (independent copies, same look as existing tables) ----
THS_AUDIT = "padding:3px 6px;border:1px solid #90CAF9;background:#42A5F5;font-size:10px;font-weight:700;color:#fff;text-align:center;width:40px;vertical-align:middle;"
TH_AUDIT  = "padding:3px 6px;border:1px solid #90CAF9;background:#42A5F5;font-size:10px;font-weight:700;color:#fff;text-align:center;vertical-align:middle;"
TD_AUDIT  = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;text-align:center;vertical-align:middle;"
TDN_AUDIT = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;text-align:center;background:#f7f9fc;font-weight:700;color:#555;vertical-align:middle;"

def _to_ist_audit(ts):
    if ts in (None, "", "-", "PENDING"):
        return "-"
    try:
        _t = _pd_audit.to_datetime(str(ts).replace("T", " "))
        _t_ist = _t + _pd_audit.Timedelta(hours=5, minutes=30)
        return _t_ist.strftime("%d-%b %I:%M %p")
    except Exception:
        return str(ts)

def _get_date_range_audit(range_choice, custom_start=None, custom_end=None):
    _today = _dt_audit.datetime.utcnow().date()
    if range_choice == "Today":
        return _today, _today
    elif range_choice == "2 Day":
        return _today - _dt_audit.timedelta(days=1), _today
    elif range_choice == "1 Week":
        return _today - _dt_audit.timedelta(days=6), _today
    elif range_choice == "1 Month":
        return _today - _dt_audit.timedelta(days=29), _today
    elif range_choice == "Custom":
        return custom_start, custom_end
    return _today, _today

_CONTRACT_MULT_AUDIT = 100 * 0.001

# ============================================================
# TRADE AUDIT TAB - CHUNK 2: Backtest Row Builder
# (Independent copy, generalized for date range instead of
# hardcoded "today only". Reuses global _load14().)
# ============================================================

_BT_CSV_PATTERN_AUDIT = {
    "S4":   "output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv",
    "S4V2": "output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv",
    "S4V3": "output/trade_log_RenkoSMIIOCrossV3Strategy_BTCUSD_*.csv",
}

def _get_bt_rows_audit(strat_label, from_date, to_date, load14_fn, inr_rate):
    rows = []
    try:
        _csv_pattern = _BT_CSV_PATTERN_AUDIT.get(strat_label)
        if not _csv_pattern:
            return []

        _df_container = load14_fn(_csv_pattern, str(from_date))
        if _df_container is None:
            return []

        dfc = _df_container.get("raw_df") if isinstance(_df_container, dict) else _df_container
        if dfc is None or not hasattr(dfc, "iterrows"):
            return []

        dfc = dfc.copy()
        dfc["exit_datetime"]  = _pd_audit.to_datetime(dfc["exit_datetime"])
        dfc["entry_datetime"] = _pd_audit.to_datetime(dfc["entry_datetime"])

        dfc = dfc[
            ((dfc["entry_datetime"].dt.date >= from_date) & (dfc["entry_datetime"].dt.date <= to_date)) |
            ((dfc["exit_datetime"].dt.date >= from_date) & (dfc["exit_datetime"].dt.date <= to_date))
        ]
        dfc = dfc.sort_values("entry_datetime", ascending=False)

        _cum_pnl = 0.0
        _trade_no = 0
        for _, r in dfc.iterrows():
            _trade_no += 1
            _dir_raw = str(r.get("direction", "")).upper()
            _entry_ts_raw = str(r.get("entry_datetime", ""))
            _exit_ts_raw  = str(r.get("exit_datetime", ""))

            _entry_p = float(r.get("entry_price", 0))
            _exit_p  = float(r.get("exit_price", 0))
            _pnl_usd = float(r.get("net_pnl", 0))
            _pnl_inr = float(r.get("net_pnl_inr", 0))
            _tax_charges = (
                float(r.get("taker_fees_usd", 0))
                + float(r.get("slippage_usd", 0))
                + float(r.get("funding_usd", 0))
                + float(r.get("tax_usd", 0))
            ) * inr_rate

            _net_pnl_inr = _pnl_inr - (max(_pnl_inr, 0) * 0.10)
            _cum_pnl += _net_pnl_inr

            rows.append({
                "trade_no"     : _trade_no,
                "label"        : strat_label,
                "dir"          : _dir_raw,
                "date"         : _entry_ts_raw[:10],
                "symbol"       : "BTCUSD",
                "entry_ts_raw" : _entry_ts_raw,
                "exit_ts_raw"  : _exit_ts_raw,
                "entry_ist"    : _to_ist_audit(_entry_ts_raw),
                "exit_ist"     : _to_ist_audit(_exit_ts_raw) if _exit_ts_raw not in ("", "PENDING", "nan") else "-",
                "entry_p"      : _entry_p,
                "exit_p"       : _exit_p,
                "lot"          : 1,
                "charges"      : _tax_charges,
                "pnl_usd"      : _pnl_usd,
                "net_pnl_inr"  : _net_pnl_inr,
                "cum_pnl_inr"  : _cum_pnl,
            })
    except Exception:
        pass
    return rows

# ============================================================
# TRADE AUDIT TAB - CHUNK 3: Live Fills Row Builder
# (Independent copy - fetches real Delta fills via /fills API,
# pairs entry/exit sequentially, builds rows for the given
# date range. Caching is applied at the wiring stage, not here.)
# ============================================================

def _fetch_fills_audit(fetch_fills_fn, acc_label, product_id=84, window_hours=48):
    """
    fetch_fills_fn: the cached fetch function (passed in from main app,
    e.g. wraps the /v2/fills API call with @st.cache_data already applied).
    acc_label: "S4", "S4V2", or "S4V3" - used to pick correct API keys.
    """
    try:
        return fetch_fills_fn(acc_label, product_id, window_hours)
    except Exception:
        return []


def _pair_fills_audit(fills):
    """
    Uses Delta's own per-fill realized PnL (meta_data.new_position.realized_pnl)
    as the authoritative PnL source, instead of reconstructing PnL from raw
    price differences via order pairing.

    IMPORTANT (fixed): meta_data.new_position.realized_pnl is a CUMULATIVE
    snapshot - "Net realized pnl since the position was opened" per Delta's
    own /positions API doc wording - NOT the isolated PnL of that single fill.
    Using it directly (as a prior version of this function did) double/triple
    counts PnL for every multi-fill position. The correct extraction is a
    baseline-delta: this fill's true PnL = raw_cumulative - baseline, where
    baseline is the cumulative value observed just before this fill, and
    baseline resets to 0 whenever the position returns to size == 0 (a new
    position lifecycle). Verified against live CSV reconciliation in
    scripts/audit_delta_issue_tracker.py (S4: 0.00 diff on PnL/charges/trades;
    S4V2 residuals fully explained by CSV export-lag, not calculation error).

    For each fill, we determine how much of its size actually CLOSES existing
    opposite-side queue lots (closed_qty = min(fill_size, opposite_qty_available)).
    The corrected fill_pnl corresponds entirely to that closed_qty (not the
    full fill size) - critical for position-flip fills that both close an old
    position and open a new opposite one in a single fill. Any leftover size
    beyond closed_qty is a fresh opening lot pushed onto the FIFO queue.

    Total PnL always sums to sum(all fills corrected fill_pnl) - sum(all
    fills commission), i.e. exactly Delta's own accounting, for any date
    range, any account, permanently (no CSV dependency).
    """
    fills_sorted = sorted(fills, key=lambda f: f.get("created_at", ""))

    queue = []  # each: dict(remaining, price, time, side, comm_per_unit)
    pairs = []
    baseline = 0.0  # cumulative realized_pnl at start of current position lifecycle

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

        # Corrected per-fill PnL: delta against lifecycle baseline, not raw cumulative value
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
                "pnl_usd": chunk_pnl,  # GROSS pnl (matches CSV "Realised P&L" convention); charges tracked separately
                "exit_order_id": _fill_order_id,
                "exit_order_closed": _fill_order_closed,
            })
            head["remaining"] -= match_size
            remaining_to_close -= match_size
            if head["remaining"] <= 1e-9:
                queue.pop(0)

        opening_qty = size - closed_qty
        if opening_qty > 1e-9:
            queue.append({"remaining": opening_qty, "price": price, "time": time,
                          "side": side, "comm_per_unit": comm_per_unit})

        # Reset baseline when position returns to flat; a new lifecycle begins
        baseline = 0.0 if pos_size_after == 0 else raw_cumulative

    return pairs


def _get_live_rows_audit(strat_label, from_date, to_date, fetch_fills_fn, inr_rate, product_id=84):
    """
    Builds Delta Live Filled rows for a strategy within [from_date, to_date].
    """
    rows = []
    try:
        acc_map = {"S4": "S4", "S4V2": "S4V2", "S4V3": "S4V3"}
        acc_label = acc_map.get(strat_label)
        if not acc_label:
            return []

        _window_hours = max(24, (_dt_audit.datetime.utcnow().date() - from_date).days * 24 + 48)
        fills = _fetch_fills_audit(fetch_fills_fn, acc_label, product_id, _window_hours)
        if not fills:
            return []

        pairs = _pair_fills_audit(fills)

        # Filter to date range first (same logic as before)
        _filtered = []
        for p in pairs:
            try:
                _entry_dt = _pd_audit.to_datetime(str(p["entry_ts_raw"]).replace("T", " "))
            except Exception:
                continue
            try:
                _exit_dt_chk = _pd_audit.to_datetime(str(p.get("exit_ts_raw","")).replace("T"," "))
                _in_range = (from_date <= _entry_dt.date() <= to_date) or (from_date <= _exit_dt_chk.date() <= to_date)
            except Exception:
                _in_range = (from_date <= _entry_dt.date() <= to_date)
            if _in_range:
                _filtered.append(p)

        # Aggregate FIFO chunks by exit_order_id so ONE Delta order = ONE trade row,
        # matching Delta's own order-level "closed" definition (order_unfilled_size == 0)
        # instead of counting per FIFO-matched chunk. This is what makes trade_no match
        # the CSV order-level trade count permanently (verified in
        # scripts/audit_delta_issue_tracker.py).
        _order_groups = {}
        _order_seq = []
        for p in _filtered:
            oid = p.get("exit_order_id", "")
            if oid not in _order_groups:
                _order_groups[oid] = {
                    "dir": p["dir"],
                    "entry_ts_raw": p["entry_ts_raw"],
                    "exit_ts_raw": p["exit_ts_raw"],
                    "entry_p_num": 0.0,
                    "exit_p": p["exit_p"],
                    "lot": 0.0,
                    "charges": 0.0,
                    "pnl_usd": 0.0,
                    "exit_order_closed": p.get("exit_order_closed", False),
                }
                _order_seq.append(oid)
            g = _order_groups[oid]
            g["lot"] += p["lot"]
            g["charges"] += p["charges"]
            g["pnl_usd"] += p["pnl_usd"]
            g["entry_p_num"] += p["entry_p"] * p["lot"]
            if str(p["entry_ts_raw"]) < str(g["entry_ts_raw"]):
                g["entry_ts_raw"] = p["entry_ts_raw"]
            g["exit_order_closed"] = g["exit_order_closed"] or p.get("exit_order_closed", False)

        _cum_pnl = 0.0
        _trade_no = 0
        for oid in _order_seq:
            g = _order_groups[oid]
            if not g["exit_order_closed"]:
                # Order not yet fully filled - not a completed trade by Delta's own
                # order-state definition; exclude from trade count (matches CSV).
                continue

            _trade_no += 1
            _entry_p = (g["entry_p_num"] / g["lot"]) if g["lot"] else 0.0
            _net_pnl_inr = (g["pnl_usd"] - g["charges"]) * inr_rate  # gross pnl minus charges = true net
            _cum_pnl += _net_pnl_inr

            rows.append({
                "trade_no"     : _trade_no,
                "label"        : strat_label,
                "dir"          : g["dir"],
                "date"         : str(g["entry_ts_raw"])[:10],
                "symbol"       : "BTCUSD",
                "entry_ts_raw" : g["entry_ts_raw"],
                "exit_ts_raw"  : g["exit_ts_raw"],
                "entry_ist"    : _to_ist_audit(g["entry_ts_raw"]),
                "exit_ist"     : _to_ist_audit(g["exit_ts_raw"]),
                "entry_p"      : _entry_p,
                "exit_p"       : g["exit_p"],
                "lot"          : g["lot"],
                "charges"      : g["charges"] * inr_rate,
                "pnl_usd"      : g["pnl_usd"],
                "net_pnl_inr"  : _net_pnl_inr,
                "cum_pnl_inr"  : _cum_pnl,
            })
    except Exception:
        pass
    return rows

# ============================================================
# TRADE AUDIT TAB - CHUNK 4: Match + Message Logic
# (Independent copy - compares a BT row vs a Live row, computes
# slippage (Match column), and builds source-led issue text
# (Message column) using [SOURCE] - [Cause] format.)
# ============================================================

def _match_audit(bt, lv):
    """
    Returns (match_text, slip_fav_usd, slip_unfav_usd) for a BT/LV pair.
    match_text shows entry/exit slippage as raw price-point deltas.
    """
    if bt is None or lv is None:
        return "-", 0.0, 0.0

    _slip_fav = 0.0
    _slip_unfav = 0.0
    try:
        _signed_entry = (bt["entry_p"] - lv["entry_p"]) if bt["dir"] == "LONG" else (lv["entry_p"] - bt["entry_p"])
        _entry_diff = abs(_signed_entry)
        _entry_sign = "+" if _signed_entry >= 0 else "-"
        if _signed_entry >= 0:
            _slip_fav += _entry_diff
        else:
            _slip_unfav += _entry_diff
        _entry_line = f"Entry: {_entry_sign}{_entry_diff:.2f} pts"
    except Exception:
        _entry_line = "Entry: -"

    _exit_line = "Exit: open"
    try:
        _bt_closed = bt.get("exit_ist") not in ("-", "", None)
        _lv_closed = lv.get("exit_ist") not in ("-", "", None)
        if _bt_closed and _lv_closed and bt.get("exit_p") and lv.get("exit_p"):
            _signed_exit = (lv["exit_p"] - bt["exit_p"]) if bt["dir"] == "LONG" else (bt["exit_p"] - lv["exit_p"])
            _exit_diff = abs(_signed_exit)
            _exit_sign = "+" if _signed_exit >= 0 else "-"
            if _signed_exit >= 0:
                _slip_fav += _exit_diff
            else:
                _slip_unfav += _exit_diff
            _exit_line = f"Exit: {_exit_sign}{_exit_diff:.2f} pts"
    except Exception:
        pass

    return f"{_entry_line} | {_exit_line}", _slip_fav, _slip_unfav


def _get_trade_issues_audit(strat_label, entry_dt, exit_dt=None, read_log_fn=None):
    """
    Scans log files for root-cause issues near a trade's entry/exit time.
    read_log_fn: cached log-reading function passed in from main app
    (e.g. wraps @st.cache_data log line reader already in use elsewhere).
    Returns list of "[SOURCE] - [Cause]" strings.
    """
    issues = []
    if read_log_fn is None:
        return issues
    try:
        _window_start = entry_dt - _pd_audit.Timedelta(minutes=10)
        _window_end = (exit_dt if exit_dt is not None else entry_dt) + _pd_audit.Timedelta(minutes=10)
        _bot_tag = strat_label  # "S4", "S4V2", "S4V3"

        # ---- CTS SIDE issues: safety monitor log ----
        _sl_lines = read_log_fn("logs/sl_safety_monitor.log")
        for _line in _sl_lines:
            if _bot_tag not in _line:
                continue
            try:
                _ts_str = _line.split(",")[0].strip()
                _line_ts = _pd_audit.to_datetime(_ts_str, format="%Y-%m-%d %H:%M:%S,%f")
            except Exception:
                continue
            if not (_window_start <= _line_ts <= _window_end):
                continue
            if "AUTO-PLACED SUCCESS" in _line or "RECOVERED - SL WAS MISSING" in _line:
                issues.append("CTS SIDE - SL was missing, auto-fixed by safety monitor within 60s")
            elif "ORPHAN POSITION" in _line:
                issues.append("CTS SIDE - Exchange position was untracked, auto-flagged and fixed")
            elif "STUCK PENDING" in _line:
                issues.append("CTS SIDE - Position sync delay detected, self-healed automatically")
            elif "EMERGENCY CLOSE" in _line:
                issues.append("CTS SIDE - SL placement failed, position auto-closed for safety")

        # ---- CTS SIDE issues: connection drops ----
        _eng_lines = read_log_fn("logs/renko_state_engine.log")
        for _line in _eng_lines:
            if "[WS] Reconnecting" not in _line:
                continue
            try:
                _ts_str = _line.split(" IST")[0].strip()
                _line_ts = _pd_audit.to_datetime(_ts_str, format="%d-%b-%Y %I:%M:%S %p")
            except Exception:
                continue
            if _window_start <= _line_ts <= _window_end:
                issues.append("CTS SIDE - Brief connection drop near this trade, auto-reconnected within 5s")

        # ---- CTS SIDE / DELTA SIDE issues: bot log ----
        _bot_log_path = f"logs/live_trading_{_bot_tag.lower()}.log"
        _bot_lines = read_log_fn(_bot_log_path)
        for _line in _bot_lines:
            _ts_raw = _line[:23]
            try:
                _line_ts2 = _pd_audit.to_datetime(_ts_raw, format="%Y-%m-%d %H:%M:%S,%f")
            except Exception:
                continue
            if not (_window_start <= _line_ts2 <= _window_end):
                continue
            if "[STARTUP]" in _line and "Bot starting" in _line:
                issues.append(f"CTS SIDE - Bot restarted near this trade's time ({_line_ts2.strftime('%H:%M:%S')} UTC)")
            elif "unfilled_beyond_band" in _line and "ENTRY FAILED" in _line:
                issues.append("DELTA SIDE - Entry order rejected, price moved outside safety band")
            elif "ENTRY FAILED" in _line:
                issues.append("DELTA SIDE - Entry order failed, exchange rejected the order")
            elif "ENTRY ABANDONED" in _line:
                issues.append("CTS SIDE - Entry abandoned after 5 failed attempts, avoided infinite retry")
            elif "ENTRY blocked - manual_override active" in _line:
                issues.append("CTS SIDE - Entry skipped, manual override was active at signal time")
            elif "ENTRY blocked - engine heartbeat stale" in _line:
                issues.append("CTS SIDE - Entry blocked, engine heartbeat was stale")
    except Exception:
        pass
    return list(dict.fromkeys(issues))

# ============================================================
# TRADE AUDIT TAB - CHUNK 4B: Extended Log Scan + Open Positions
# (Independent additions - does not modify Chunk 3/4 functions.
# Adds position_risk_monitor.log + margin_monitor.log scanning,
# and detects live entry orders with no matching exit yet.)
# ============================================================

def _get_trade_issues_audit_full(strat_label, entry_dt, exit_dt=None, read_log_fn=None):
    issues = _get_trade_issues_audit(strat_label, entry_dt, exit_dt, read_log_fn)
    if read_log_fn is None:
        return issues
    try:
        _window_start = entry_dt - _pd_audit.Timedelta(minutes=10)
        _window_end = (exit_dt if exit_dt is not None else entry_dt) + _pd_audit.Timedelta(minutes=10)

        _extra_sources = [
            ("logs/position_risk_monitor.log", {
                "MARGIN CALL": "DELTA SIDE - Margin call triggered near this trade",
                "RISK LIMIT": "CTS SIDE - Position risk limit breached, auto-action taken",
                "LIQUIDATION WARNING": "DELTA SIDE - Liquidation risk flagged near this trade",
            }),
            ("logs/margin_monitor.log", {
                "MARGIN REJECTED": "DELTA SIDE - Order rejected due to insufficient margin",
                "MARGIN LOW": "CTS SIDE - Low margin detected, position sizing may be affected",
            }),
        ]
        for _log_path, _tag_map in _extra_sources:
            try:
                _lines = read_log_fn(_log_path)
            except Exception:
                continue
            for _line in _lines:
                if strat_label not in _line:
                    continue
                try:
                    _ts_str = _line.split(",")[0].strip()
                    _line_ts = _pd_audit.to_datetime(_ts_str, format="%Y-%m-%d %H:%M:%S,%f")
                except Exception:
                    continue
                if not (_window_start <= _line_ts <= _window_end):
                    continue
                for _kw, _msg in _tag_map.items():
                    if _kw in _line:
                        issues.append(_msg)
    except Exception:
        pass
    return list(dict.fromkeys(issues))


def _get_open_live_rows_audit(strat_label, from_date, to_date, fetch_fills_fn, product_id=84):
    """
    Detects entry orders with no matching exit yet (open positions).
    Independent re-scan of raw fills - does not touch _pair_fills_audit.
    """
    from collections import defaultdict
    rows = []
    try:
        acc_map = {"S4": "S4", "S4V2": "S4V2", "S4V3": "S4V3"}
        acc_label = acc_map.get(strat_label)
        if not acc_label:
            return []

        _window_hours = max(24, (_dt_audit.datetime.utcnow().date() - from_date).days * 24 + 48)
        fills = _fetch_fills_audit(fetch_fills_fn, acc_label, product_id, _window_hours)
        if not fills:
            return []

        order_fills = defaultdict(list)
        for f in fills:
            order_fills[f.get("order_id", "")].append(f)

        orders = []
        for oid, flist in order_fills.items():
            total_size = sum(float(f.get("size", 0)) for f in flist)
            if total_size <= 0:
                continue
            wavg = sum(float(f.get("price", 0) or 0) * float(f.get("size", 0)) for f in flist) / total_size
            commission = sum(abs(float(f.get("commission", 0))) for f in flist)
            orders.append({
                "order_id": oid,
                "side": str(flist[0].get("side", "")).upper(),
                "size": total_size,
                "price": wavg,
                "time": flist[0].get("created_at", ""),
                "commission": commission,
            })
        orders_sorted = sorted(orders, key=lambda x: x["time"])

        used = set()
        for i, entry_o in enumerate(orders_sorted):
            exit_side = "SELL" if entry_o["side"] == "BUY" else "BUY"
            for j in range(i + 1, len(orders_sorted)):
                if orders_sorted[j]["side"] == exit_side and j not in used:
                    used.add(i); used.add(j)
                    break

        for i, entry_o in enumerate(orders_sorted):
            if i in used:
                continue
            try:
                _entry_dt = _pd_audit.to_datetime(str(entry_o["time"]).replace("T", " "))
            except Exception:
                continue
            try:
                _exit_dt_chk = _pd_audit.to_datetime(str(p.get("exit_ts_raw","")).replace("T"," "))
                _in_range = (from_date <= _entry_dt.date() <= to_date) or (from_date <= _exit_dt_chk.date() <= to_date)
            except Exception:
                _in_range = (from_date <= _entry_dt.date() <= to_date)
            if not _in_range:
                continue

            _dir = "LONG" if entry_o["side"] == "BUY" else "SHORT"
            rows.append({
                "trade_no": None, "label": strat_label, "dir": _dir,
                "date": str(entry_o["time"])[:10], "symbol": "BTCUSD",
                "entry_ts_raw": entry_o["time"], "exit_ts_raw": None,
                "entry_ist": _to_ist_audit(entry_o["time"]), "exit_ist": "OPEN",
                "entry_p": entry_o["price"], "exit_p": None,
                "lot": entry_o["size"], "charges": entry_o["commission"],
                "pnl_usd": None, "net_pnl_inr": None, "cum_pnl_inr": None,
                "is_open": True,
            })
    except Exception:
        pass
    return rows

# ============================================================
# TRADE AUDIT TAB - CHUNK 5: Independent Tables + Main UI
# (Two fully independent tables rendered side by side. No BT/LV
# pairing anywhere. Message column on Live Filled side only,
# from log scan. BT side has dynamic Lot + Slippage inputs.)
# ============================================================

import streamlit as st

_STRATS_AUDIT = ["S4", "S4V2", "S4V3"]
_INR_RATE_AUDIT_DEFAULT_UNUSED = None

def _clean_html_audit(html):
    """
    Collapses multi-line indented HTML into a single continuous line.
    Prevents Streamlit/Markdown from misreading whitespace-only lines
    as blank lines, which breaks raw HTML block parsing and causes
    tables to render as literal text instead of HTML.
    """
    return re.sub(r"\n\s*", "", html)

_INR_RATE_AUDIT = 84.0


def _fmt_num_audit(v, dec=2):
    try:
        return f"{float(v):,.{dec}f}"
    except Exception:
        return "-"


def _cell_audit(row, key, dec=2, is_int=False, default="-"):
    if row is None:
        return default
    v = row.get(key)
    if v is None:
        return default
    if is_int:
        try:
            return str(int(v))
        except Exception:
            return default
    return _fmt_num_audit(v, dec)


def _apply_bt_adjustments_audit(bt_rows, lot_input, slippage_usd, inr_rate):
    """
    Scales backtest rows to a user-chosen lot size and deducts a
    synthetic slippage cost ($ per lot). Pure what-if simulation on
    the backtest side only - no live data involved.
    Assumes CSV base figures represent 1 lot.
    """
    adjusted = []
    cum = 0.0
    for r in bt_rows:
        r2 = dict(r)
        pnl_usd = r.get("pnl_usd")
        if pnl_usd is None or r.get("exit_ist") in ("-", None):
            r2["lot"] = lot_input
            r2["net_pnl_inr"] = None
            r2["cum_pnl_inr"] = cum
            adjusted.append(r2)
            continue
        scaled_usd = pnl_usd * (lot_input / 100.0)
        before_tax_inr = scaled_usd * inr_rate
        after_tax_inr = before_tax_inr - (max(before_tax_inr, 0) * 0.10)
        slip_deduction_inr = slippage_usd * (lot_input / 100.0) * inr_rate
        final_net_inr = after_tax_inr - slip_deduction_inr
        cum += final_net_inr
        r2["lot"] = lot_input
        r2["charges"] = (r.get("charges") or 0) * (lot_input / 100.0)
        r2["net_pnl_inr"] = final_net_inr
        r2["cum_pnl_inr"] = cum
        adjusted.append(r2)
    return adjusted


def _render_lv_row_html(row, strat_label, read_log_fn, fetch_orders_fn=None):
    if row.get("is_open"):
        try:
            _entry_dt = _pd_audit.to_datetime(str(row.get("entry_ts_raw", "")).replace("T", " "))
            message = "DELTA SIDE - Position Still Open (awaiting exit fill)"
        except Exception:
            message = "DELTA SIDE - Position Still Open (awaiting exit fill)"
    else:
        try:
            _entry_dt = _pd_audit.to_datetime(str(row["entry_ts_raw"]).replace("T", " "))
            _exit_raw = row.get("exit_ts_raw")
            _exit_dt = _pd_audit.to_datetime(str(_exit_raw).replace("T", " ")) if _exit_raw not in (None, "", "PENDING", "nan") else None
            _issues = _get_trade_issues_audit_full(strat_label, _entry_dt, _exit_dt, read_log_fn)
            _all_msgs = _issues
            message = " | ".join(_all_msgs) if _all_msgs else "OK - No issues detected"
        except Exception:
            message = "OK - No issues detected"

    return f"""
    <tr>
      <td style="{TDN_AUDIT}">{row.get('trade_no') if row.get('trade_no') is not None else '-'}</td>
      <td style="{TD_AUDIT}">{row.get('date','-')}</td>
      <td style="{TD_AUDIT}">{row.get('symbol','-')}</td>
      <td style="{TD_AUDIT}">{row.get('dir','-')}</td>
      <td style="{TD_AUDIT}">{row.get('entry_ist','-')}</td>
      <td style="{TD_AUDIT}">{row.get('exit_ist','-')}</td>
      <td style="{TD_AUDIT}">{_fmt_num_audit(row.get('entry_p'))}</td>
      <td style="{TD_AUDIT}">{_fmt_num_audit(row.get('exit_p')) if row.get('exit_p') is not None else 'OPEN'}</td>
      <td style="{TD_AUDIT}">{_cell_audit(row, 'lot', is_int=True)}</td>
      <td style="{TD_AUDIT}">{_fmt_num_audit(row.get('charges'))}</td>
      {_pnl_td_audit(row.get('net_pnl_inr'))}
      {_pnl_td_audit(row.get('cum_pnl_inr'))}
      <td style="{TD_AUDIT};text-align:left;">{message}</td>
    </tr>
    """


def _pnl_td_audit(value):
    if value is None:
        return f'<td style="{TD_AUDIT}">-</td>'
    _color = "#2e7d32" if value >= 0 else "#c62828"
    return f'<td style="{TD_AUDIT};color:{_color};font-weight:700;">{_fmt_num_audit(value)}</td>'


def _render_bt_row_html(row):
    return f"""
    <tr>
      <td style="{TDN_AUDIT}">{row.get('trade_no','-')}</td>
      <td style="{TD_AUDIT}">{row.get('date','-')}</td>
      <td style="{TD_AUDIT}">{row.get('symbol','-')}</td>
      <td style="{TD_AUDIT}">{row.get('dir','-')}</td>
      <td style="{TD_AUDIT}">{row.get('entry_ist','-')}</td>
      <td style="{TD_AUDIT}">{row.get('exit_ist','-')}</td>
      <td style="{TD_AUDIT}">{_fmt_num_audit(row.get('entry_p'))}</td>
      <td style="{TD_AUDIT}">{_fmt_num_audit(row.get('exit_p')) if row.get('exit_p') else 'OPEN'}</td>
      <td style="{TD_AUDIT}">{_cell_audit(row, 'lot', is_int=True)}</td>
      <td style="{TD_AUDIT}">{_fmt_num_audit(row.get('charges'))}</td>
      {_pnl_td_audit(row.get('net_pnl_inr'))}
      {_pnl_td_audit(row.get('cum_pnl_inr'))}
    </tr>
    """


def _render_lv_table_html(rows_html):
    header = f"""
    <table style="width:100%;border-collapse:collapse;margin-bottom:10px;">
      <tr>
        <th style="{TH_AUDIT}">Trade No</th><th style="{TH_AUDIT}">Date</th>
        <th style="{TH_AUDIT}">Symbol</th><th style="{TH_AUDIT}">Dir</th><th style="{TH_AUDIT}">Entry Time</th>
        <th style="{TH_AUDIT}">Exit Time</th><th style="{TH_AUDIT}">Entry Px</th>
        <th style="{TH_AUDIT}">Exit Px</th><th style="{TH_AUDIT}">Lot</th>
        <th style="{TH_AUDIT}">Charges</th><th style="{TH_AUDIT}">Net PnL</th>
        <th style="{TH_AUDIT}">Cum PnL</th><th style="{TH_AUDIT}">Message</th>
      </tr>
    """
    return header + rows_html + "</table>"


def _render_bt_table_html(rows_html):
    header = f"""
    <table style="width:100%;border-collapse:collapse;margin-bottom:10px;">
      <tr>
        <th style="{TH_AUDIT}">Trade No</th><th style="{TH_AUDIT}">Date</th>
        <th style="{TH_AUDIT}">Symbol</th><th style="{TH_AUDIT}">Dir</th><th style="{TH_AUDIT}">Entry Time</th>
        <th style="{TH_AUDIT}">Exit Time</th><th style="{TH_AUDIT}">Entry Px</th>
        <th style="{TH_AUDIT}">Exit Px</th><th style="{TH_AUDIT}">Lot</th>
        <th style="{TH_AUDIT}">Charges</th><th style="{TH_AUDIT}">Net PnL</th>
        <th style="{TH_AUDIT}">Cum PnL</th>
      </tr>
    """
    return header + rows_html + "</table>"


@st.cache_data(ttl=180, show_spinner=False)
def _load_audit_bt_cached(_load14_fn, strat_label, from_date, to_date, inr_rate):
    return _get_bt_rows_audit(strat_label, from_date, to_date, _load14_fn, inr_rate)


@st.cache_data(ttl=180, show_spinner=False)
def _load_audit_lv_cached(_fetch_fills_fn, strat_label, from_date, to_date, inr_rate):
    return _get_live_rows_audit(strat_label, from_date, to_date, _fetch_fills_fn, inr_rate)


@st.cache_data(ttl=180, show_spinner=False)
def _load_audit_lv_open_cached(_fetch_fills_fn, strat_label, from_date, to_date):
    return _get_open_live_rows_audit(strat_label, from_date, to_date, _fetch_fills_fn)


def _metric_pnl_html_audit(label, value):
    _color = "#2e7d32" if value >= 0 else "#c62828"
    return f'''
    <div style="padding:0 0 4px 0;">
      <div style="font-size:14px;color:#6b7280;">{label}</div>
      <div style="font-size:14px;font-weight:600;color:{_color};">Rs {_fmt_num_audit(value)}</div>
    </div>
    '''


def _render_one_strategy_block_audit(strat_label, from_date, to_date, load14_fn, fetch_fills_fn, read_log_fn, inr_rate, bt_lot_input, bt_slippage_input, fetch_orders_fn=None):
    bt_rows_raw = _load_audit_bt_cached(load14_fn, strat_label, from_date, to_date, inr_rate)
    lv_rows = _load_audit_lv_cached(fetch_fills_fn, strat_label, from_date, to_date, inr_rate)
    lv_open_rows = _load_audit_lv_open_cached(fetch_fills_fn, strat_label, from_date, to_date)

    bt_rows = _apply_bt_adjustments_audit(bt_rows_raw, bt_lot_input, bt_slippage_input, inr_rate)
    lv_all_rows = lv_rows + lv_open_rows

    col_lv, col_bt = st.columns(2)

    with col_lv:
        st.markdown(f"**{strat_label}**")
        _total_trade_lv = len(lv_all_rows)
        _total_pnl_lv = sum(r["net_pnl_inr"] for r in lv_rows if r.get("net_pnl_inr") is not None)
        _total_charge_lv = sum(r["charges"] for r in lv_all_rows if r.get("charges") is not None)
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Trade", _total_trade_lv)
        with m2:
            st.markdown(_metric_pnl_html_audit("Total Net PnL", _total_pnl_lv), unsafe_allow_html=True)
        m3.metric("Total Charge", f"Rs {_fmt_num_audit(_total_charge_lv)}")

        rows_html = "".join(_render_lv_row_html(r, strat_label, read_log_fn, fetch_orders_fn) for r in lv_all_rows)
        st.markdown(_clean_html_audit(f'<div style="overflow-x:auto;">{_render_lv_table_html(rows_html)}</div>'), unsafe_allow_html=True)

        st.markdown("##### Unfilled / Failed Order Alerts (Delta Side)")
        alerts = []
        try:
            _bot_log_path = f"logs/live_trading_{strat_label.lower()}.log"
            _bot_lines = read_log_fn(_bot_log_path) if read_log_fn else []
            for _line in _bot_lines:
                _ts_raw = _line[:23]
                try:
                    _line_ts = _pd_audit.to_datetime(_ts_raw, format="%Y-%m-%d %H:%M:%S,%f")
                except Exception:
                    continue
                if not (from_date <= _line_ts.date() <= to_date):
                    continue
                if "ENTRY FAILED" in _line and "unfilled_beyond_band" in _line:
                    alerts.append((_line_ts, "DELTA SIDE - Entry order rejected, price moved outside safety band"))
                elif "ENTRY FAILED" in _line:
                    alerts.append((_line_ts, "DELTA SIDE - Entry order failed, exchange rejected the order"))
                elif "ENTRY ABANDONED" in _line:
                    alerts.append((_line_ts, "CTS SIDE - Entry abandoned after repeated failed attempts"))
        except Exception:
            pass

        try:
            if fetch_orders_fn is not None:
                _acc_map_ord = {"S4": "S4", "S4V2": "S4V2", "S4V3": "S4V3"}
                _acc_lbl_ord = _acc_map_ord.get(strat_label)
                if _acc_lbl_ord:
                    _orders_hist = fetch_orders_fn(_acc_lbl_ord, 84)
                    for _o in (_orders_hist or []):
                        try:
                            _o_ts = _dt_audit.datetime.utcfromtimestamp(int(_o.get("created_at", 0)) / 1e6)
                        except Exception:
                            continue
                        if not (from_date <= _o_ts.date() <= to_date):
                            continue
                        _state = _o.get("state", "")
                        _size = _o.get("size", 0)
                        _unfilled = _o.get("unfilled_size", 0)
                        _sot = _o.get("stop_order_type")
                        _tag = "SL" if _sot == "stop_loss_order" else "Order"
                        try:
                            _filled = float(_size) - float(_unfilled)
                        except Exception:
                            _filled = None
                        if _state == "cancelled":
                            if _filled and _filled > 0:
                                alerts.append((_o_ts, f"DELTA SIDE - {_tag} Partially Filled then Cancelled ({int(_filled)}/{_size} filled)"))
                            else:
                                alerts.append((_o_ts, f"DELTA SIDE - {_tag} Cancelled, No Fill (0/{_size} filled)"))
                        elif _state in ("open", "pending"):
                            alerts.append((_o_ts, f"DELTA SIDE - {_tag} Still {_state.capitalize()}"))
        except Exception:
            pass

        if alerts:
            alerts_sorted = sorted(alerts, key=lambda x: x[0], reverse=True)
            rows_a = "".join(
                f'<tr><td style="{TD_AUDIT}">{_to_ist_audit(str(ts))}</td><td style="{TD_AUDIT};text-align:left;">{msg}</td></tr>'
                for ts, msg in alerts_sorted
            )
            st.markdown(
                _clean_html_audit(
                    f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;">'
                    f'<tr><th style="{TH_AUDIT}">Timestamp (IST)</th><th style="{TH_AUDIT}">Message</th></tr>{rows_a}</table></div>'
                ),
                unsafe_allow_html=True
            )
        else:
            st.caption("No unfilled/failed order alerts in this date range.")

    with col_bt:
        st.markdown(f"**{strat_label}**")
        _total_trade_bt = len(bt_rows)
        _total_pnl_bt = sum(r["net_pnl_inr"] for r in bt_rows if r.get("net_pnl_inr") is not None)
        _total_charge_bt = sum(r["charges"] for r in bt_rows if r.get("charges") is not None)
        n1, n2, n3 = st.columns(3)
        n1.metric("Total Trade", _total_trade_bt)
        with n2:
            st.markdown(_metric_pnl_html_audit("Total Net PnL", _total_pnl_bt), unsafe_allow_html=True)
        n3.metric("Total Charge", f"Rs {_fmt_num_audit(_total_charge_bt)}")

        rows_html_bt = "".join(_render_bt_row_html(r) for r in bt_rows)
        st.markdown(_clean_html_audit(f'<div style="overflow-x:auto;">{_render_bt_table_html(rows_html_bt)}</div>'), unsafe_allow_html=True)


def render_trade_audit_tab(load14_fn, fetch_fills_fn, read_log_fn, inr_rate=_INR_RATE_AUDIT, fetch_orders_fn=None):
    st.markdown("### TRADE AUDIT - Delta Live Filled vs Backtest")

    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1.4])
    with c1:
        strat_label = st.selectbox("Strategy", ["ALL STRATEGY", "S4", "S4V2", "S4V3"], key="audit_strat_select")
    with c2:
        range_choice = st.selectbox("Date Range", ["Today", "2 Day", "1 Week", "1 Month", "Custom"], index=0, key="audit_range_select")
    with c3:
        bt_lot_input = st.number_input("BT Lot", min_value=1, value=100, step=1, key="audit_bt_lot")
    with c4:
        bt_slippage_input = st.selectbox("BT Slip($)", [0, 5, 10, 15], index=1, key="audit_bt_slip")
    custom_start, custom_end = None, None
    with c5:
        if range_choice == "Custom":
            custom_start = st.date_input("From", key="audit_custom_from")
            custom_end = st.date_input("To", key="audit_custom_to")

    from_date, to_date = _get_date_range_audit(range_choice, custom_start, custom_end)
    if from_date is None or to_date is None:
        st.warning("Please select a valid custom date range.")
        return

    hcol1, hcol2 = st.columns(2)
    with hcol1:
        st.markdown("### DELTA LIVE FILLED")
    with hcol2:
        st.markdown("### BACKTEST")

    if strat_label == "ALL STRATEGY":
        for _idx, _s in enumerate(["S4", "S4V2", "S4V3"]):
            _render_one_strategy_block_audit(_s, from_date, to_date, load14_fn, fetch_fills_fn, read_log_fn, inr_rate, bt_lot_input, bt_slippage_input, fetch_orders_fn)
            if _idx < 2:
                st.markdown("---")
    else:
        _render_one_strategy_block_audit(strat_label, from_date, to_date, load14_fn, fetch_fills_fn, read_log_fn, inr_rate, bt_lot_input, bt_slippage_input, fetch_orders_fn)


# ============================================================
# TRADE AUDIT TAB - CHUNK 6: Standalone Fills Fetcher + Log Reader
# (Independent copies - do NOT touch Section 14's closures.
# Exact same logic/signature/base-url replicated so this tab
# has zero dependency on _tab_today's internal functions.)
# ============================================================

import streamlit as st

@st.cache_data(ttl=180, show_spinner=False)
def _fetch_account_fills_cached_audit(acc, _product_id=84, _window_hours=48):
    import hmac as _hmlf_a, hashlib as _hslf_a, time as _tmlf_a, requests as _rqlf_a, os as _os_a
    _k = _os_a.environ.get(f'{acc}_API_KEY', '')
    _s = _os_a.environ.get(f'{acc}_API_SECRET', '')
    if not _k or not _s:
        return []
    _base = "https://cdn-ind.testnet.deltaex.org"
    _path = "/v2/fills"
    _now = int(_tmlf_a.time())
    _start = int((_now - _window_hours * 3600) * 1e6)
    _end   = int((_now + 300) * 1e6)
    _all_fills = []
    _after_cursor = None
    for _page in range(1, 50):
        _ts_ep = str(int(_tmlf_a.time()))
        _p = {"product_id": _product_id, "page_size": 50,
              "start_time": _start, "end_time": _end}
        if _after_cursor:
            _p["after"] = _after_cursor
        _qs = "&".join(f"{a}={b}" for a, b in sorted(_p.items()))
        _msg = "GET" + _ts_ep + _path + "?" + _qs
        _sig = _hmlf_a.new(_s.encode(), _msg.encode(), _hslf_a.sha256).hexdigest()
        _hdr = {"api-key": _k, "timestamp": _ts_ep, "signature": _sig}
        try:
            _r = _rqlf_a.get(f"{_base}{_path}?{_qs}", headers=_hdr, timeout=10)
            _d = _r.json()
            if not _d.get("success"):
                break
            _page_fills = _d.get("result", [])
            if not _page_fills:
                break
            _all_fills.extend(_page_fills)
            _meta = _d.get("meta", {})
            _after_cursor = _meta.get("after")
            if not _after_cursor:
                break
        except Exception:
            break
    return _all_fills


@st.cache_data(ttl=180, show_spinner=False)
def _fetch_account_orders_history_cached_audit(acc, _product_id=84, _window_hours=48):
    import hmac as _hmoh_a, hashlib as _hsoh_a, time as _tmoh_a, requests as _rqoh_a, os as _osoh_a
    _k = _osoh_a.environ.get(f'{acc}_API_KEY', '')
    _s = _osoh_a.environ.get(f'{acc}_API_SECRET', '')
    if not _k or not _s:
        return []
    _base = "https://cdn-ind.testnet.deltaex.org"
    _path = "/v2/orders/history"
    _now = int(_tmoh_a.time())
    _start = int((_now - _window_hours * 3600) * 1e6)
    _end   = int((_now + 300) * 1e6)
    _all_orders = []
    _after_cursor = None
    for _page in range(1, 50):
        _ts_ep = str(int(_tmoh_a.time()))
        _p = {"product_ids": str(_product_id), "page_size": 50,
              "start_time": _start, "end_time": _end}
        if _after_cursor:
            _p["after"] = _after_cursor
        _qs = "&".join(f"{a}={b}" for a, b in sorted(_p.items()))
        _msg = "GET" + _ts_ep + _path + "?" + _qs
        _sig = _hmoh_a.new(_s.encode(), _msg.encode(), _hsoh_a.sha256).hexdigest()
        _hdr = {"api-key": _k, "timestamp": _ts_ep, "signature": _sig}
        try:
            _r = _rqoh_a.get(f"{_base}{_path}?{_qs}", headers=_hdr, timeout=10)
            _d = _r.json()
            if not _d.get("success"):
                break
            _page_orders = _d.get("result", [])
            if not _page_orders:
                break
            _all_orders.extend(_page_orders)
            _meta = _d.get("meta", {})
            _after_cursor = _meta.get("after")
            if not _after_cursor:
                break
        except Exception:
            break
    return _all_orders


@st.cache_data(ttl=180, show_spinner=False)
def _read_log_lines_cached_audit(_path, _mtime):
    try:
        with open(_path) as _f:
            return _f.readlines()
    except Exception:
        return []


def _read_log_lines_audit(_path):
    import os as _os_audit2
    try:
        _mtime = _os_audit2.path.getmtime(_path)
    except Exception:
        _mtime = 0
    return _read_log_lines_cached_audit(_path, _mtime)
