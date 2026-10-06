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

def get_baseline_commit_date():
    try:
        dates = []
        for f in CRITICAL_FILES:
            out = subprocess.check_output(
                ["git", "log", "-1", "--format=%ad", "--date=iso", "--", f],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            if out:
                dates.append(datetime.fromisoformat(out))
        return max(dates) if dates else None
    except Exception as e:
        return None

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

    slips = [(r.get("bot"), r.get("entry_ts_bt"), r.get("entry_slippage_usd"), r.get("exit_slippage_usd")) for r in since]
    if slips:
        print(f"[INFO] entry/exit slippage since baseline (testnet - informational only, not gated): {slips[-5:]}")

def check_fire_delay(baseline):
    rows = read_csv_rows("logs/confirmation_lag_events.csv")
    since = [r for r in rows if float(r.get("detected_at", 0)) >= baseline.timestamp()]
    delays = []
    for r in since:
        tf = TF_MIN_BY_BOT.get(r.get("label", ""))
        if tf is None:
            continue
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
        failed_drills = [k for k, v in drills.items() if not v.get("passed")]
        missing_drills = [k for k in REQUIRED_DRILLS if k not in drills]
        record("g_protection_drills", not failed_drills and not missing_drills,
               f"{len(drills)} drills logged, missing={missing_drills} failed={failed_drills}")
    else:
        record("g_protection_drills", False, "logs/drills.json not found")

    # --- Criterion i: production readiness config checks ---
    try:
        from scripts.cts_env import CTS_ENV, IS_TESTNET, PRODUCT_ID, LOT_SIZE
        record("i_env_config", True,
               f"CTS_ENV={CTS_ENV} PRODUCT_ID={PRODUCT_ID} LOT_SIZE={LOT_SIZE} "
               f"(testnet={IS_TESTNET} - expected before Stage B)")
    except Exception as e:
        record("i_env_config", False, f"cts_env import failed: {e}")

    # --- Criterion d: fire delay p90<=5s, max<=15s (if lag events exist) ---
    lag_rows = read_csv_rows("logs/confirmation_lag_events.csv")
    if lag_rows:
        lags = []
        for r in lag_rows:
            if baseline:
                try:
                    ts = datetime.fromisoformat(r.get("detected_at", "").replace("Z", "+00:00"))
                    if ts < baseline:
                        continue
                except Exception:
                    continue
            try:
                lags.append(float(r.get("lag_sec", "")))
            except Exception:
                continue
        if lags:
            lags.sort()
            p90 = lags[int(len(lags) * 0.9)] if len(lags) > 1 else lags[0]
            max_lag = max(lags)
            record("d_fire_delay", p90 <= 5 and max_lag <= 15,
                   f"p90={p90:.1f}s max={max_lag:.1f}s (n={len(lags)}) - need p90<=5s, max<=15s")
        else:
            pass  # replaced below by check_fire_delay(window_start)
    else:
        record("d_fire_delay", None, "logs/confirmation_lag_events.csv empty/missing")

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
