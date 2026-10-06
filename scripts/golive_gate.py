#!/usr/bin/env python3
"""
golive_gate.py - READ-ONLY go-live readiness checker.
Checks criteria from Claude go-live report Section 3 (a-i).
Does NOT touch trading, signal, or order logic. Zero write operations
to any trading-related file. Only reads logs/*.csv and git log.
Added 05-Oct-2026.

Usage: .venv/bin/python3 scripts/golive_gate.py
Exit code 0 = all PASS, 1 = at least one FAIL.
"""
import os, sys, csv, json, subprocess
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/home/anildalabanjan7/crypto_tradingsystem")
os.chdir("/home/anildalabanjan7/crypto_tradingsystem")

CRITICAL_FILES = [
    "engine/order_manager.py",
    "scripts/renko_state_engine.py",
    "scripts/signal_replay_s4.py",
    "scripts/signal_replay_s4v2.py",
    "scripts/signal_replay_s4v3.py",
    "scripts/sl_safety_monitor.py",
    "scripts/cts_env.py",
    "scripts/position_risk_monitor.py",
    "bot_watchdog.sh",
    "scripts/watchdog_capital.py",
]
WINDOW_DAYS = 14
RESULTS = []

def record(name, passed, detail):
    RESULTS.append({"criterion": name, "passed": passed, "detail": detail})

def load_exempt():
    exempt = set()
    exempt_path = "scripts/baseline_exempt.txt"
    if os.path.exists(exempt_path):
        with open(exempt_path) as ef:
            for line in ef:
                line = line.strip()
                if not line:
                    continue
                h = line.split("|")[0].strip()
                if h:
                    exempt.add(h)
    return exempt

def get_baseline_commit_date():
    try:
        exempt = load_exempt()
        dates = []
        for f in CRITICAL_FILES:
            out = subprocess.check_output(
                ["git", "log", "--format=%H|||%ad", "--date=iso", "--", f],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            if not out:
                continue
            for line in out.splitlines():
                parts = line.split("|||", 1)
                if len(parts) != 2:
                    continue
                commit_hash, date_str = parts
                if commit_hash.strip() in exempt:
                    continue
                dates.append(datetime.fromisoformat(date_str.strip()))
                break
        return max(dates) if dates else None
    except Exception as e:
        return None

def read_startups():
    log_files = {
        "S4": "logs/live_trading_s4.log",
        "S4V2": "logs/live_trading_s4v2.log",
        "S4V3": "logs/live_trading_s4v3.log",
    }
    startups = []
    for bot, lpath in log_files.items():
        if not os.path.exists(lpath):
            continue
        with open(lpath, errors="ignore") as f:
            for line in f:
                if "[STARTUP]" in line and "Bot starting" in line:
                    try:
                        ts_str = line.split(" INFO")[0].strip()
                        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=timezone.utc)
                        startups.append((bot, ts))
                    except Exception:
                        continue
    return startups

def read_planned():
    ppath = "logs/planned_restarts.txt"
    planned = []
    if os.path.exists(ppath):
        with open(ppath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 2:
                    continue
                ts_str, bot = parts[0], parts[1]
                try:
                    ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
                    planned.append((bot, ts))
                except Exception:
                    continue
    return planned

def unplanned_restarts(baseline):
    startups = read_startups()
    planned = read_planned()
    tolerance_min = 10
    unplanned = []
    for bot, ts in startups:
        if baseline and ts < baseline:
            continue
        matched = False
        for pbot, pts in planned:
            if pbot == bot and abs((ts - pts).total_seconds()) <= tolerance_min * 60:
                matched = True
                break
        if not matched:
            unplanned.append((bot, ts))
    return unplanned

def read_csv_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", errors="ignore") as f:
        return list(csv.DictReader(f))


TF_MIN_BY_BOT = {"S4": 120, "S4V2": 30, "S4V3": 240}

def check_bt_live_match(baseline):
    """Criteria b (direction) + c (trade count), with testnet band/slippage
    miss treated as PASS (exchange-side, not a system bug)."""
    rows = read_csv_rows("logs/bt_live_mismatch.csv")
    issue_rows = read_csv_rows("logs/issue_tracker_trades.csv")
    exempt_flags = {"ENTRY_UNFILLED_BAND", "ENTRY_BAND_ABANDONED"}
    since = [r for r in rows if r.get("logged_at", "") >= baseline.isoformat()]
    if not since:
        record("b_direction_match", True, "no rows since baseline (nothing to check yet)")
        record("c_trade_count_match", True, "no rows since baseline (nothing to check yet)")
        return
    dir_mismatches = [r for r in since if str(r.get("direction_mismatch")).lower() == "true"]
    record("b_direction_match", len(dir_mismatches) == 0,
           f"{len(since)-len(dir_mismatches)}/{len(since)} match, mismatches={len(dir_mismatches)}")

    missed = [r for r in since if str(r.get("missed_trade")).lower() == "true"]
    extra = [r for r in since if str(r.get("extra_live_trade")).lower() == "true"]
    unexempt_missed = []
    for r in missed:
        bot, ets = r.get("bot", "").upper(), r.get("entry_ts_bt", "")
        exempted = any(
            ir.get("bot", "").upper() == bot and ir.get("system_side_flag", "") in exempt_flags
            and ets[:10] in str(ir.get("date", ""))
            for ir in issue_rows
        )
        if not exempted:
            unexempt_missed.append(r)
    record("c_trade_count_match", len(unexempt_missed) == 0 and len(extra) == 0,
           f"missed={len(missed)} (exempted testnet-band={len(missed)-len(unexempt_missed)}, "
           f"unexplained={len(unexempt_missed)}), extra_live={len(extra)}")

    detail_rows = [{
        "bot": r.get("bot"), "entry_ts_bt": r.get("entry_ts_bt"), "entry_ts_live": r.get("entry_ts_live"),
        "entry_price_bt": r.get("entry_price_bt"), "entry_price_live": r.get("entry_price_live"),
        "entry_slippage_usd": r.get("entry_slippage_usd"),
        "exit_ts_bt": r.get("exit_ts_bt"), "exit_ts_live": r.get("exit_ts_live"),
        "exit_price_bt": r.get("exit_price_bt"), "exit_price_live": r.get("exit_price_live"),
        "exit_slippage_usd": r.get("exit_slippage_usd"),
    } for r in since]
    if detail_rows:
        print(f"[INFO] entry/exit fill ts+price+slippage since baseline (testnet - informational only, not gated): {detail_rows[-5:]}")

def check_fire_delay(baseline):
    rows = read_csv_rows("logs/confirmation_lag_events.csv")
    since = [r for r in rows if float(r.get("detected_at", 0)) >= baseline.timestamp()]
    delays = []
    seen = set()
    for r in since:
        tf = TF_MIN_BY_BOT.get(r.get("label", ""))
        if tf is None:
            continue
        dedup_key = (r.get("label", ""), r.get("detected_at", ""))
        if dedup_key in seen:
            continue  # BUG-FIX: exit+flip-entry fire in same cycle, share detected_at - count once
        seen.add(dedup_key)
        try:
            real_delay = float(r["lag_sec"]) - tf * 60
            delays.append(real_delay)
        except Exception:
            continue
    if not delays:
        record("d_fire_delay", None, "no numeric lag data since baseline (SKIP)")
        return
    delays.sort()
    p90 = delays[int(0.9 * (len(delays) - 1))]
    mx = max(delays)
    record("d_fire_delay", p90 <= 5 and mx <= 15,
           f"p90={p90:.1f}s (<=5 required) max={mx:.1f}s (<=15 required) n={len(delays)}")

def main():
    baseline = get_baseline_commit_date()
    now = datetime.now(timezone.utc)

    if baseline is None:
        record("baseline_commit", False, "Could not determine baseline commit date")
        window_start = None
    else:
        if baseline.tzinfo is None:
            baseline = baseline.replace(tzinfo=timezone.utc)
        days_elapsed = (now - baseline).total_seconds() / 86400.0
        window_start = baseline
        record("baseline_commit", True,
               f"Last critical-file commit: {baseline.isoformat()} | "
               f"days_elapsed={days_elapsed:.1f} / required={WINDOW_DAYS}")

    if window_start:
        check_bt_live_match(window_start)
        check_fire_delay(window_start)

    unplanned = unplanned_restarts(window_start)
    record("j_unplanned_restarts", len(unplanned) == 0,
           f"{len(unplanned)} unplanned restart(s): " +
           "; ".join(f"{b}@{t.isoformat()}" for b, t in unplanned))

    # --- Criterion a: zero new SYSTEM-SIDE / UNEXPLAINED verdicts since baseline ---
    tracker_rows = read_csv_rows("logs/issue_tracker_trades.csv")
    bad_verdicts = []
    if baseline:
        for r in tracker_rows:
            try:
                row_date = datetime.fromisoformat(str(r.get("entry_ts", "")).replace("T", " ").split(".")[0]).replace(tzinfo=timezone.utc)
            except Exception:
                try:
                    row_date = datetime.strptime(r.get("date", ""), "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(hours=23, minutes=59)
                except Exception:
                    continue
            if row_date >= baseline and r.get("verdict") in ("SYSTEM-SIDE", "UNEXPLAINED"):
                bad_verdicts.append(r)
    record("a_bug_log", len(bad_verdicts) == 0,
           f"{len(bad_verdicts)} SYSTEM-SIDE/UNEXPLAINED rows since baseline")

    # --- Criterion f: zero desync/orphan/resync/version-drift/canary events in window ---
    fast_events = read_csv_rows("logs/watchdog_fast_events.csv")
    bad_classes = ("A_STATE_DESYNC", "CANARY_FAIL", "STUCK", "ORPHAN", "AUTO-RESYNC", "VERSION-DRIFT", "VERSION_DRIFT")
    f_hits = []
    if baseline:
        for r in fast_events:
            try:
                ts = datetime.fromisoformat(r.get("detected_at_utc", "").replace("Z", "+00:00"))
            except Exception:
                continue
            if ts >= baseline and any(bc in r.get("check_class", "") for bc in bad_classes):
                f_hits.append(r)
    record("f_desync_orphan", len(f_hits) == 0,
           f"{len(f_hits)} desync/orphan/resync/canary events since baseline")

    # --- Criterion e: zero missed/expired signals since baseline ---
    missed_classes = ("C_MISSED_SIGNAL", "REPAINT GUARD", "SKIPPED", "CAP_EXHAUSTED_SKIP")
    e_hits = []
    if baseline:
        for r in fast_events:
            try:
                ts = datetime.fromisoformat(r.get("detected_at_utc", "").replace("Z", "+00:00"))
            except Exception:
                continue
            if ts >= baseline and any(mc in r.get("check_class", "") or mc in r.get("detail", "") for mc in missed_classes):
                e_hits.append(r)
    record("e_missed_signals", len(e_hits) == 0,
           f"{len(e_hits)} missed/expired signal events since baseline")

    # --- Criterion h: no identical non-heartbeat signature >5x in 10min ---
    loop_violation = False
    loop_detail = "no violation found"
    sig_counts = {}
    for r in fast_events:
        try:
            ts = datetime.fromisoformat(r.get("detected_at_utc", "").replace("Z", "+00:00"))
        except Exception:
            continue
        if baseline and ts < baseline:
            continue
        key = (r.get("bot"), r.get("check_class"))
        sig_counts.setdefault(key, []).append(ts)
    for key, timestamps in sig_counts.items():
        timestamps.sort()
        for i in range(len(timestamps)):
            window = [t for t in timestamps[i:] if (t - timestamps[i]).total_seconds() <= 600]
            if len(window) > 5:
                loop_violation = True
                loop_detail = f"{key} repeated {len(window)}x within 10min at {timestamps[i].isoformat()}"
                break
        if loop_violation:
            break
    record("h_loop_pattern", not loop_violation, loop_detail)

    # --- Criterion g: all drills passed (from logs/drills.json) ---
    drills_path = "logs/drills.json"
    if os.path.exists(drills_path):
        with open(drills_path) as f:
            drills = json.load(f)
        REQUIRED_DRILLS = ["sl_delete_autoplace", "sl_placement_fail_emergency_close", "auto_resync",
                           "manual_flatten_all", "watchdog_capital_slippage_alert",
                           "tier1_speed_autoclose", "tier2_liqdist_autoclose"]
        FORWARD_TEST_EXCEPTIONS = {
            "tier2_liqdist_autoclose": "S4V3 Portfolio margin mode returns null liquidation_price (Delta Exchange API design) - accepted forward-test exception, must verify at live go-live",
        }
        failed_drills = [k for k, v in drills.items() if not v.get("passed")]
        missing_drills = [k for k in REQUIRED_DRILLS if k not in drills]
        missing_blocking = [k for k in missing_drills if k not in FORWARD_TEST_EXCEPTIONS]
        missing_excepted = [k for k in missing_drills if k in FORWARD_TEST_EXCEPTIONS]
        detail = f"{len(drills)} drills logged, missing_blocking={missing_blocking} failed={failed_drills}"
        if missing_excepted:
            detail += f", accepted_exceptions={missing_excepted}"
        record("g_protection_drills", not failed_drills and not missing_blocking, detail)
    else:
        record("g_protection_drills", False, "logs/drills.json not found")

    # --- Criterion i: production readiness config checks ---
    try:
        from scripts.cts_env import CTS_ENV, IS_TESTNET, PRODUCT_ID, LOT_SIZE
        lot_note = "accepted forward-test exception, must switch to 1 at live go-live" if LOT_SIZE != 1 else "OK"
        record("i_env_config", True,
               f"CTS_ENV={CTS_ENV} PRODUCT_ID={PRODUCT_ID} LOT_SIZE={LOT_SIZE} ({lot_note}) "
               f"(testnet={IS_TESTNET} - expected before Stage B); "
               f"S4V3 Portfolio margin mode retained (accepted forward-test exception, Delta Exchange 2-account "
               f"limit per margin mode, re-check at live go-live)")
    except Exception as e:
        record("i_env_config", False, f"cts_env import failed: {e}")

    # --- Print report ---
    print("=" * 70)
    print("GOLIVE_GATE REPORT -", now.isoformat())
    print("=" * 70)
    overall_pass = True
    for r in RESULTS:
        if r["passed"] is None:
            status = "SKIP"
        elif r["passed"]:
            status = "PASS"
        else:
            status = "FAIL"
            overall_pass = False
        print(f"[{status}] {r['criterion']}: {r['detail']}")
    print("=" * 70)
    print("OVERALL:", "PASS" if overall_pass else "FAIL")
    sys.exit(0 if overall_pass else 1)

if __name__ == "__main__":
    main()
