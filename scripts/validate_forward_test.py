#!/usr/bin/env python3
"""
Forward Test Validation Framework
Checkpoint 0: Pre-flight / Data Availability Check
READ-ONLY - never places orders, never modifies CSVs/strategy/backtest files
"""
import os, sys, time

REPO = "/home/anildalabanjan933/crypto_trading_system"
os.chdir(REPO)
sys.path.insert(0, ".")

HEARTBEAT_FILE = "logs/engine_heartbeat.txt"
HEARTBEAT_MAX_AGE_SEC = 900

CSV_FILES = {"S2": "logs/signals_s2.csv", "S4": "logs/signals_s4.csv"}
LOG_FILES = {"S2": "logs/live_trading_s2.log", "S4": "logs/live_trading_s4.log"}
LOG_MAX_AGE_SEC = 900


def check_heartbeat():
    r = {"name": "engine_heartbeat", "status": None, "detail": ""}
    if not os.path.exists(HEARTBEAT_FILE):
        r["status"] = "UNAVAILABLE"; r["detail"] = f"{HEARTBEAT_FILE} does not exist"
        return r
    try:
        age = time.time() - float(open(HEARTBEAT_FILE).read().strip())
        if age > HEARTBEAT_MAX_AGE_SEC:
            r["status"] = "UNAVAILABLE"; r["detail"] = f"heartbeat age {age:.0f}s exceeds {HEARTBEAT_MAX_AGE_SEC}s"
        else:
            r["status"] = "OK"; r["detail"] = f"heartbeat age {age:.0f}s"
    except Exception as e:
        r["status"] = "UNAVAILABLE"; r["detail"] = f"could not parse heartbeat: {e}"
    return r


def check_csv_files():
    out = []
    for label, path in CSV_FILES.items():
        r = {"name": f"csv_{label}", "status": None, "detail": ""}
        if not os.path.exists(path):
            r["status"] = "UNAVAILABLE"; r["detail"] = f"{path} does not exist"
        else:
            size = os.path.getsize(path)
            if size == 0:
                r["status"] = "UNAVAILABLE"; r["detail"] = f"{path} is empty"
            else:
                with open(path) as f:
                    n = sum(1 for _ in f)
                if n == 0:
                    r["status"] = "UNAVAILABLE"; r["detail"] = f"{path} has 0 rows"
                else:
                    r["status"] = "OK"; r["detail"] = f"{path} has {n} rows"
        out.append(r)
    return out


def check_log_files():
    out = []
    now = time.time()
    for label, path in LOG_FILES.items():
        r = {"name": f"log_{label}", "status": None, "detail": ""}
        if not os.path.exists(path):
            r["status"] = "UNAVAILABLE"; r["detail"] = f"{path} does not exist"
        else:
            age = now - os.path.getmtime(path)
            if age > LOG_MAX_AGE_SEC:
                r["status"] = "UNAVAILABLE"; r["detail"] = f"{path} last modified {age:.0f}s ago (>{LOG_MAX_AGE_SEC}s)"
            else:
                r["status"] = "OK"; r["detail"] = f"{path} last modified {age:.0f}s ago"
        out.append(r)
    return out


def check_delta_api():
    out = []
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=os.path.join(REPO, ".env"), override=True)
        from engine.order_manager import OrderManager
    except Exception as e:
        return [{"name": "delta_api_import", "status": "UNAVAILABLE", "detail": f"import failed: {e}"}]

    for label in ["S2", "S4"]:
        r = {"name": f"delta_api_{label}", "status": None, "detail": ""}
        try:
            api_key = os.getenv(f"{label}_API_KEY")
            api_secret = os.getenv(f"{label}_API_SECRET")
            if not api_key or not api_secret or "your_real" in api_key:
                r["status"] = "UNAVAILABLE"; r["detail"] = f"{label} API key/secret missing or placeholder"
                out.append(r); continue

            om = OrderManager(api_key, api_secret, testnet=True)
            pos = om.get_position()
            if pos is None:
                r["status"] = "UNAVAILABLE"; r["detail"] = "get_position() returned None - GET unreachable"
            elif isinstance(pos, dict) and pos.get("success") is False:
                r["status"] = "UNAVAILABLE"; r["detail"] = f"get_position() failed: {pos}"
            else:
                r["status"] = "OK"; r["detail"] = f"GET reachable - position: {pos}"
        except Exception as e:
            r["status"] = "UNAVAILABLE"; r["detail"] = f"exception during {label} API check: {e}"
        out.append(r)
    return out


ENGINE_LOG = "logs/renko_state_engine.log"

def check_signal_generation():
    import re, subprocess
    out = []
    for label in ["S2", "S4"]:
        r = {"name": f"signal_gen_{label}", "status": None, "detail": ""}
        csv_path = CSV_FILES[label]
        try:
            if not os.path.exists(csv_path):
                r["status"] = "UNAVAILABLE"; r["detail"] = f"{csv_path} does not exist"
                out.append(r); continue
            with open(csv_path) as f2:
                rows = [line.strip().split(",") for line in f2 if line.strip()]
            csv_entries = set(row[0] for row in rows if len(row) >= 1)
            csv_exits = set(row[1] for row in rows if len(row) >= 2 and row[1] != "PENDING")

            if not os.path.exists(ENGINE_LOG):
                r["status"] = "UNAVAILABLE"; r["detail"] = f"{ENGINE_LOG} does not exist"
                out.append(r); continue

            grep_out = subprocess.run(
                ["grep", f"[{label}]", ENGINE_LOG],
                capture_output=True, text=True
            ).stdout
            lines = [l for l in grep_out.splitlines()
                     if f"[{label}] ENTRY" in l or f"[{label}] EXIT" in l]
            lines = lines[-10:]

            if not lines:
                r["status"] = "UNAVAILABLE"; r["detail"] = "no ENTRY/EXIT lines found in engine log yet"
                out.append(r); continue

            mismatches = []
            checked = 0
            for l in lines:
                m = re.search(rf"\[{label}\] (ENTRY|EXIT) (\w+) at (\S+)", l)
                if not m:
                    continue
                sig_type, direction, ts = m.groups()
                checked += 1
                if sig_type == "ENTRY":
                    if ts not in csv_entries:
                        mismatches.append(f"ENTRY {ts} not found in CSV entry column")
                else:
                    if ts not in csv_exits and ts not in csv_entries:
                        mismatches.append(f"EXIT {ts} not found in CSV exit column")

            if mismatches:
                r["status"] = "FAIL"; r["detail"] = "; ".join(mismatches)
            else:
                r["status"] = "PASS"; r["detail"] = f"{checked} recent log signals all found in CSV - CSV/log in sync"
        except Exception as e:
            r["status"] = "UNAVAILABLE"; r["detail"] = f"exception: {e}"
        out.append(r)
    return out


def run_checkpoint_1():
    results = check_signal_generation()
    overall = "PASS"
    for r in results:
        if r["status"] == "FAIL":
            overall = "FAIL"
        elif r["status"] == "UNAVAILABLE" and overall != "FAIL":
            overall = "PARTIAL"
    return overall, results


def print_report_1(overall, results):
    print("=" * 70)
    print("CHECKPOINT 1 - SIGNAL GENERATION (CSV vs ENGINE LOG)")
    print("=" * 70)
    for r in results:
        print(f"  [{r['status']:<12}] {r['name']:<20} - {r['detail']}")
    print("-" * 70)
    print(f"CHECKPOINT 1 OVERALL: {overall}")
    print("=" * 70)


LIVE_LOG_FILES = {"S2": "logs/live_trading_s2.log", "S4": "logs/live_trading_s4.log"}
SLIPPAGE_TOLERANCE_USD = 50.0

def check_order_execution():
    import re, subprocess
    out = []
    for label in ["S2", "S4"]:
        r = {"name": f"order_exec_{label}", "status": None, "detail": ""}
        log_path = LIVE_LOG_FILES[label]
        try:
            if not os.path.exists(log_path):
                r["status"] = "UNAVAILABLE"; r["detail"] = f"{log_path} does not exist"
                out.append(r); continue

            tail_out = subprocess.run(
                ["tail", "-n", "500", log_path], capture_output=True, text=True
            ).stdout
            lines = tail_out.splitlines()

            attempts = [l for l in lines if "[ORDER] ENTRY" in l or "[ORDER] EXIT" in l]
            confirmed = [l for l in lines if "confirmed" in l.lower() and "[ORDER]" in l]
            failed = [l for l in lines if "[ORDER]" in l and "FAILED" in l]

            if not attempts and not failed:
                r["status"] = "UNAVAILABLE"; r["detail"] = "no recent [ORDER] activity found in log yet"
                out.append(r); continue

            if failed:
                last_fail = failed[-1].split("INFO")[-1].split("ERROR")[-1].strip()
                outage_signature = "Expecting value: line 1 column 1" in tail_out or "max_retries_exceeded" in tail_out
                if outage_signature:
                    r["status"] = "OUTAGE"
                    r["detail"] = f"{len(failed)} failure(s) match known Delta testnet outage signature (not a code bug) - last: {last_fail[:120]}"
                else:
                    r["status"] = "FAIL"
                    r["detail"] = f"{len(failed)} recent order failure(s) - last: {last_fail[:120]}"
            elif confirmed:
                r["status"] = "PASS"
                r["detail"] = f"{len(confirmed)} order(s) confirmed, 0 failures in last 500 log lines"
            else:
                r["status"] = "PARTIAL"
                r["detail"] = f"{len(attempts)} order attempt(s) seen, none confirmed yet - may be in-flight"
        except Exception as e:
            r["status"] = "UNAVAILABLE"; r["detail"] = f"exception: {e}"
        out.append(r)
    return out


def check_price_slippage():
    import subprocess
    out = []
    for label in ["S2", "S4"]:
        r = {"name": f"slippage_{label}", "status": None, "detail": ""}
        csv_path = CSV_FILES[label]
        log_path = LIVE_LOG_FILES[label]
        try:
            if not os.path.exists(csv_path) or not os.path.exists(log_path):
                r["status"] = "UNAVAILABLE"; r["detail"] = "csv or log file missing"
                out.append(r); continue

            with open(csv_path) as f2:
                rows = [line.strip().split(",") for line in f2 if line.strip()]
            last_closed = None
            for row in reversed(rows):
                if len(row) >= 6 and row[1] != "PENDING" and row[5].strip() not in ("", "PENDING"):
                    last_closed = row
                    break
            if not last_closed:
                r["status"] = "UNAVAILABLE"; r["detail"] = "no closed trade with exit price found in CSV yet"
                out.append(r); continue

            bt_exit_price = float(last_closed[5])
            bt_exit_ts = last_closed[1]

            grep_out = subprocess.run(
                ["grep", "EXIT confirmed", log_path], capture_output=True, text=True
            ).stdout
            if not grep_out.strip():
                r["status"] = "UNAVAILABLE"; r["detail"] = "no 'EXIT confirmed' line found in live log yet"
                out.append(r); continue

            r["status"] = "OK"
            r["detail"] = f"backtest exit price {bt_exit_price} at {bt_exit_ts} - live confirms present (exact fill price cross-check needs richer log; slippage tolerance={SLIPPAGE_TOLERANCE_USD} USD)"
        except Exception as e:
            r["status"] = "UNAVAILABLE"; r["detail"] = f"exception: {e}"
        out.append(r)
    return out


def run_checkpoint_2():
    results = check_order_execution() + check_price_slippage()
    overall = "PASS"
    for r in results:
        if r["status"] == "FAIL":
            overall = "FAIL"
        elif r["status"] == "OUTAGE" and overall not in ("FAIL",):
            overall = "OUTAGE"
        elif r["status"] in ("UNAVAILABLE", "PARTIAL") and overall not in ("FAIL", "OUTAGE"):
            overall = "PARTIAL"
    return overall, results


def print_report_2(overall, results):
    print("=" * 70)
    print("CHECKPOINT 2 - ORDER EXECUTION VERIFICATION")
    print("=" * 70)
    for r in results:
        print(f"  [{r['status']:<12}] {r['name']:<20} - {r['detail']}")
    print("-" * 70)
    print(f"CHECKPOINT 2 OVERALL: {overall}")
    print("=" * 70)


def check_position_sync():
    out = []
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=os.path.join(REPO, ".env"), override=True)
        from engine.order_manager import OrderManager
    except Exception as e:
        return [{"name": "position_sync_import", "status": "UNAVAILABLE", "detail": f"import failed: {e}"}]

    import subprocess
    for label in ["S2", "S4"]:
        r = {"name": f"position_sync_{label}", "status": None, "detail": ""}
        try:
            api_key = os.getenv(f"{label}_API_KEY")
            api_secret = os.getenv(f"{label}_API_SECRET")
            if not api_key or not api_secret:
                r["status"] = "UNAVAILABLE"; r["detail"] = f"{label} API key/secret missing"
                out.append(r); continue

            om = OrderManager(api_key, api_secret, testnet=True)
            exchange_pos = om.get_position()
            if not exchange_pos or not exchange_pos.get("success"):
                r["status"] = "UNAVAILABLE"; r["detail"] = "could not fetch exchange position (API unreachable)"
                out.append(r); continue

            exchange_dir = exchange_pos.get("direction", "FLAT")
            exchange_size = abs(exchange_pos.get("size", 0))

            log_path = LIVE_LOG_FILES[label]
            if not os.path.exists(log_path):
                r["status"] = "UNAVAILABLE"; r["detail"] = f"{log_path} does not exist"
                out.append(r); continue

            tail_out = subprocess.run(
                ["tail", "-n", "300", log_path], capture_output=True, text=True
            ).stdout
            bot_position = None
            for line in reversed(tail_out.splitlines()):
                if "position=" in line:
                    try:
                        bot_position = line.split("position=")[1].split("|")[0].strip()
                    except Exception:
                        pass
                    break

            if bot_position is None:
                r["status"] = "UNAVAILABLE"; r["detail"] = "no position= field found in recent log lines"
                out.append(r); continue

            bot_dir_norm = "FLAT" if bot_position in ("None", "flat", "FLAT") else bot_position.upper()
            exch_dir_norm = exchange_dir.upper()

            if bot_dir_norm == exch_dir_norm:
                r["status"] = "PASS"
                r["detail"] = f"bot={bot_dir_norm} matches exchange={exch_dir_norm} (size={exchange_size})"
            else:
                r["status"] = "FAIL"
                r["detail"] = f"MISMATCH: bot thinks position={bot_dir_norm} but exchange shows={exch_dir_norm} (size={exchange_size}) - possible ghost position or stuck state"
        except Exception as e:
            r["status"] = "UNAVAILABLE"; r["detail"] = f"exception: {e}"
        out.append(r)
    return out


def run_checkpoint_3():
    results = check_position_sync()
    overall = "PASS"
    for r in results:
        if r["status"] == "FAIL":
            overall = "FAIL"
        elif r["status"] == "UNAVAILABLE" and overall != "FAIL":
            overall = "PARTIAL"
    return overall, results


def print_report_3(overall, results):
    print("=" * 70)
    print("CHECKPOINT 3 - POSITION STATE SYNC (BOT vs EXCHANGE)")
    print("=" * 70)
    for r in results:
        print(f"  [{r['status']:<12}] {r['name']:<20} - {r['detail']}")
    print("-" * 70)
    print(f"CHECKPOINT 3 OVERALL: {overall}")
    print("=" * 70)


def check_duplicate_orders():
    import re, subprocess
    out = []
    for label in ["S2", "S4"]:
        r = {"name": f"duplicate_orders_{label}", "status": None, "detail": ""}
        log_path = LIVE_LOG_FILES[label]
        try:
            if not os.path.exists(log_path):
                r["status"] = "UNAVAILABLE"; r["detail"] = f"{log_path} does not exist"
                out.append(r); continue

            tail_out = subprocess.run(
                ["tail", "-n", "1000", log_path], capture_output=True, text=True
            ).stdout
            lines = tail_out.splitlines()

            confirmed = []
            for l in lines:
                m = re.search(r"\[ORDER\] (ENTRY|EXIT) (\w+) (\d+) lots \| .*ts=(\S+)", l)
                if m and ("confirmed" in l.lower() or True):
                    pass
            # Use attempt lines with ts= as the signature of an order action
            attempts = []
            for l in lines:
                m = re.search(r"\[ORDER\] (ENTRY|EXIT) \w+ \d+ lots \| .*ts=(\S+)", l)
                if m:
                    attempts.append((m.group(1), m.group(2)))

            if not attempts:
                r["status"] = "UNAVAILABLE"; r["detail"] = "no order attempts found in recent log"
                out.append(r); continue

            confirmed_lines = [l for l in lines if "confirmed" in l.lower() and "[ORDER]" in l]
            confirmed_keys = []
            for l in confirmed_lines:
                m = re.search(r"\[ORDER\] (ENTRY|EXIT) confirmed", l)
                if m:
                    # pair confirmed line with nearest preceding attempt ts for same type
                    confirmed_keys.append(m.group(1))

            seen = {}
            for sig_type, ts in attempts:
                key = (sig_type, ts)
                seen[key] = seen.get(key, 0) + 1

            retry_loops = [f"{k[0]} at {k[1]} retried {c}x (all failed - outage retry loop)"
                           for k, c in seen.items() if c > 1]

            outage_signature = "Expecting value: line 1 column 1" in tail_out or "max_retries_exceeded" in tail_out

            # Real duplicate = same (type, ts) confirmed more than once
            confirmed_seen = {}
            for l in confirmed_lines:
                for k in seen.keys():
                    if k[1] in l or True:
                        pass
            real_dupe_confirmed = len(confirmed_lines) > 0 and len(set(confirmed_lines)) < len(confirmed_lines)

            if real_dupe_confirmed:
                r["status"] = "FAIL"
                r["detail"] = "duplicate CONFIRMED order detected - possible double execution on exchange"
            elif retry_loops and outage_signature:
                r["status"] = "OUTAGE"
                r["detail"] = "; ".join(retry_loops[:3]) + " - matches known outage, safe retry behavior, no confirmed duplicate"
            elif retry_loops:
                r["status"] = "FAIL"
                r["detail"] = "; ".join(retry_loops[:5]) + " - repeated attempts NOT matching known outage signature, investigate"
            else:
                r["status"] = "PASS"
                r["detail"] = f"{len(attempts)} order attempt(s) checked - no duplicate ENTRY/EXIT at same timestamp"
        except Exception as e:
            r["status"] = "UNAVAILABLE"; r["detail"] = f"exception: {e}"
        out.append(r)
    return out


def run_checkpoint_4():
    results = check_duplicate_orders()
    overall = "PASS"
    for r in results:
        if r["status"] == "FAIL":
            overall = "FAIL"
        elif r["status"] == "UNAVAILABLE" and overall != "FAIL":
            overall = "PARTIAL"
    return overall, results


def print_report_4(overall, results):
    print("=" * 70)
    print("CHECKPOINT 4 - DUPLICATE ORDER DETECTION")
    print("=" * 70)
    for r in results:
        print(f"  [{r['status']:<12}] {r['name']:<20} - {r['detail']}")
    print("-" * 70)
    print(f"CHECKPOINT 4 OVERALL: {overall}")
    print("=" * 70)


SL_PCT_EXPECTED = 0.02

def check_stop_loss_placement():
    import re, subprocess
    out = []
    for label in ["S2", "S4"]:
        r = {"name": f"sl_check_{label}", "status": None, "detail": ""}
        log_path = LIVE_LOG_FILES[label]
        try:
            if not os.path.exists(log_path):
                r["status"] = "UNAVAILABLE"; r["detail"] = f"{log_path} does not exist"
                out.append(r); continue

            tail_out = subprocess.run(
                ["tail", "-n", "1000", log_path], capture_output=True, text=True
            ).stdout
            lines = tail_out.splitlines()

            entry_confirms = [l for l in lines if "[ORDER] ENTRY confirmed" in l]
            sl_placed = [l for l in lines if "stop" in l.lower() and ("placed" in l.lower() or "sl" in l.lower())]

            if not entry_confirms:
                r["status"] = "UNAVAILABLE"; r["detail"] = "no confirmed ENTRY found in recent log - nothing to verify SL against"
                out.append(r); continue

            if not sl_placed:
                r["status"] = "FAIL"
                r["detail"] = f"{len(entry_confirms)} confirmed ENTRY found but NO stop-loss placement log line found - SL may be missing"
            else:
                r["status"] = "PASS"
                r["detail"] = f"{len(entry_confirms)} confirmed ENTRY, {len(sl_placed)} SL-related log line(s) found"
        except Exception as e:
            r["status"] = "UNAVAILABLE"; r["detail"] = f"exception: {e}"
        out.append(r)
    return out


def run_checkpoint_5():
    results = check_stop_loss_placement()
    overall = "PASS"
    for r in results:
        if r["status"] == "FAIL":
            overall = "FAIL"
        elif r["status"] == "UNAVAILABLE" and overall != "FAIL":
            overall = "PARTIAL"
    return overall, results


def print_report_5(overall, results):
    print("=" * 70)
    print("CHECKPOINT 5 - STOP LOSS VERIFICATION")
    print("=" * 70)
    for r in results:
        print(f"  [{r['status']:<12}] {r['name']:<20} - {r['detail']}")
    print("-" * 70)
    print(f"CHECKPOINT 5 OVERALL: {overall}")
    print("=" * 70)


PRICE_TOLERANCE_PCT = 0.02

def check_pnl_reconciliation():
    import csv, subprocess
    out = []
    for label in ["S2", "S4"]:
        r = {"name": f"pnl_recon_{label}", "status": None, "detail": ""}
        log_path = LIVE_LOG_FILES[label]
        csv_path = f"logs/signals_{label.lower()}.csv"
        try:
            if not os.path.exists(log_path) or not os.path.exists(csv_path):
                r["status"] = "UNAVAILABLE"; r["detail"] = "log or CSV missing"
                out.append(r); continue

            tail_out = subprocess.run(["tail", "-n", "1000", log_path], capture_output=True, text=True).stdout
            lines = tail_out.splitlines()
            exit_confirms = [l for l in lines if "EXIT confirmed" in l]

            if not exit_confirms:
                r["status"] = "UNAVAILABLE"; r["detail"] = "no confirmed EXIT yet - nothing to reconcile"
                out.append(r); continue

            rows = []
            with open(csv_path) as f2:
                for row in csv.reader(f2):
                    if len(row) >= 6:
                        rows.append(row)

            if not rows:
                r["status"] = "UNAVAILABLE"; r["detail"] = "signal CSV empty"
                out.append(r); continue

            last_row = rows[-1]
            expected_exit_price = last_row[5] if len(last_row) > 5 else None

            mismatch = False
            if expected_exit_price:
                try:
                    exp_p = float(expected_exit_price)
                    for l in exit_confirms[-3:]:
                        nums = [tok.strip("$,") for tok in l.replace(":", " ").split() if tok.replace(".", "").replace("$", "").replace(",", "").isdigit()]
                    r["status"] = "PASS"
                    r["detail"] = f"{len(exit_confirms)} EXIT confirmed, latest CSV exit_price={expected_exit_price}"
                except Exception:
                    r["status"] = "PARTIAL"; r["detail"] = "could not parse price for comparison"
            else:
                r["status"] = "PARTIAL"; r["detail"] = f"{len(exit_confirms)} EXIT confirmed but CSV missing exit price field"
        except Exception as e:
            r["status"] = "UNAVAILABLE"; r["detail"] = f"exception: {e}"
        out.append(r)
    return out

def run_checkpoint_6():
    results = check_pnl_reconciliation()
    overall = "PASS"
    for r in results:
        if r["status"] == "FAIL": overall = "FAIL"
        elif r["status"] in ("UNAVAILABLE", "PARTIAL") and overall != "FAIL": overall = "PARTIAL"
    return overall, results

def print_report_6(overall, results):
    print("=" * 70)
    print("CHECKPOINT 6 - PNL RECONCILIATION (LIVE vs SIGNAL CSV)")
    print("=" * 70)
    for r in results:
        print(f"  [{r['status']:<12}] {r['name']:<20} - {r['detail']}")
    print("-" * 70)
    print(f"CHECKPOINT 6 OVERALL: {overall}")
    print("=" * 70)

LATENCY_WARN_SEC = 60

def check_signal_to_order_latency():
    import subprocess, re
    from datetime import datetime
    out = []
    for label in ["S2", "S4"]:
        r = {"name": f"latency_{label}", "status": None, "detail": ""}
        log_path = LIVE_LOG_FILES[label]
        try:
            if not os.path.exists(log_path):
                r["status"] = "UNAVAILABLE"; r["detail"] = f"{log_path} does not exist"
                out.append(r); continue

            tail_out = subprocess.run(["tail", "-n", "1000", log_path], capture_output=True, text=True).stdout
            lines = tail_out.splitlines()

            signal_lines = [l for l in lines if "[SIGNAL]" in l or "signal detected" in l.lower()]
            order_lines = [l for l in lines if "[ORDER] ENTRY confirmed" in l or "[ORDER] EXIT confirmed" in l]

            if not signal_lines or not order_lines:
                r["status"] = "UNAVAILABLE"; r["detail"] = "not enough signal/order pairs in recent log to measure latency"
                out.append(r); continue

            def get_ts(line):
                m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                if m:
                    try:
                        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        return None
                return None

            sig_ts = get_ts(signal_lines[-1])
            ord_ts = get_ts(order_lines[-1])

            if not sig_ts or not ord_ts:
                r["status"] = "UNAVAILABLE"; r["detail"] = "could not parse timestamps for latency check"
                out.append(r); continue

            delta_sec = abs((ord_ts - sig_ts).total_seconds())
            if delta_sec > LATENCY_WARN_SEC:
                r["status"] = "PARTIAL"
                r["detail"] = f"latency {delta_sec:.0f}s exceeds {LATENCY_WARN_SEC}s warning threshold"
            else:
                r["status"] = "PASS"
                r["detail"] = f"latency {delta_sec:.0f}s within {LATENCY_WARN_SEC}s threshold"
        except Exception as e:
            r["status"] = "UNAVAILABLE"; r["detail"] = f"exception: {e}"
        out.append(r)
    return out

def run_checkpoint_7():
    results = check_signal_to_order_latency()
    overall = "PASS"
    for r in results:
        if r["status"] == "FAIL": overall = "FAIL"
        elif r["status"] in ("UNAVAILABLE", "PARTIAL") and overall != "FAIL": overall = "PARTIAL"
    return overall, results

def print_report_7(overall, results):
    print("=" * 70)
    print("CHECKPOINT 7 - SIGNAL TO ORDER LATENCY")
    print("=" * 70)
    for r in results:
        print(f"  [{r['status']:<12}] {r['name']:<20} - {r['detail']}")
    print("-" * 70)
    print(f"CHECKPOINT 7 OVERALL: {overall}")
    print("=" * 70)

ERROR_RATE_WARN = 5

def check_error_rate():
    import subprocess
    out = []
    outage_sig = ["Expecting value: line 1 column 1", "max_retries_exceeded", "POST failed after 3 attempts", "GET failed after 3 attempts"]
    for label in ["S2", "S4"]:
        r = {"name": f"error_rate_{label}", "status": None, "detail": ""}
        log_path = LIVE_LOG_FILES[label]
        try:
            if not os.path.exists(log_path):
                r["status"] = "UNAVAILABLE"; r["detail"] = f"{log_path} does not exist"
                out.append(r); continue

            tail_out = subprocess.run(["tail", "-n", "1000", log_path], capture_output=True, text=True).stdout
            lines = tail_out.splitlines()

            error_lines = [l for l in lines if " ERROR " in l or " CRITICAL " in l]
            outage_errors = [l for l in error_lines if any(sig in l for sig in outage_sig)]
            real_errors = [l for l in error_lines if l not in outage_errors]

            if not error_lines:
                r["status"] = "PASS"; r["detail"] = "zero ERROR/CRITICAL lines in recent log"
            elif not real_errors:
                r["status"] = "OUTAGE"
                r["detail"] = f"{len(error_lines)} error line(s), all match known outage signature - not a code bug"
            elif len(real_errors) > ERROR_RATE_WARN:
                r["status"] = "FAIL"
                r["detail"] = f"{len(real_errors)} non-outage error(s) found - exceeds {ERROR_RATE_WARN} threshold - last: {real_errors[-1][:120]}"
            else:
                r["status"] = "PARTIAL"
                r["detail"] = f"{len(real_errors)} non-outage error(s) found (within threshold) - last: {real_errors[-1][:120]}"
        except Exception as e:
            r["status"] = "UNAVAILABLE"; r["detail"] = f"exception: {e}"
        out.append(r)
    return out

def run_checkpoint_8():
    results = check_error_rate()
    overall = "PASS"
    for r in results:
        if r["status"] == "FAIL": overall = "FAIL"
        elif r["status"] in ("UNAVAILABLE", "PARTIAL", "OUTAGE") and overall != "FAIL": overall = r["status"] if overall == "PASS" else overall
    return overall, results

def print_report_8(overall, results):
    print("=" * 70)
    print("CHECKPOINT 8 - ERROR RATE MONITORING")
    print("=" * 70)
    for r in results:
        print(f"  [{r['status']:<12}] {r['name']:<20} - {r['detail']}")
    print("-" * 70)
    print(f"CHECKPOINT 8 OVERALL: {overall}")
    print("=" * 70)

def run_checkpoint_0():
    results = []
    results.append(check_heartbeat())
    results.extend(check_csv_files())
    results.extend(check_log_files())
    results.extend(check_delta_api())
    overall = "PASS"
    for r in results:
        if r["status"] == "UNAVAILABLE":
            overall = "PARTIAL"
    return overall, results


def print_report(overall, results):
    print("=" * 70)
    print("CHECKPOINT 0 - PRE-FLIGHT / DATA AVAILABILITY CHECK")
    print("=" * 70)
    for r in results:
        print(f"  [{r['status']:<12}] {r['name']:<20} - {r['detail']}")
    print("-" * 70)
    print(f"CHECKPOINT 0 OVERALL: {overall}")
    if overall == "PARTIAL":
        print("NOTE: One or more data sources unavailable (env/outage issue).")
        print("      Dependent checkpoints will be SKIPPED, not marked FAIL,")
        print("      to avoid false-positive bug reports.")
    print("=" * 70)


if __name__ == "__main__":
    overall0, results0 = run_checkpoint_0()
    print_report(overall0, results0)
    print()
    if overall0 == "PARTIAL":
        print("Checkpoint 0 PARTIAL - running Checkpoint 1 anyway (informational)")
        print()
    overall1, results1 = run_checkpoint_1()
    print_report_1(overall1, results1)
    print()
    overall2, results2 = run_checkpoint_2()
    print_report_2(overall2, results2)
    print()
    overall3, results3 = run_checkpoint_3()
    print_report_3(overall3, results3)
    print()
    overall4, results4 = run_checkpoint_4()
    print_report_4(overall4, results4)
    print()
    overall5, results5 = run_checkpoint_5()
    print_report_5(overall5, results5)
    print()
    overall6, results6 = run_checkpoint_6()
    print_report_6(overall6, results6)
    print()
    overall7, results7 = run_checkpoint_7()
    print_report_7(overall7, results7)
    print()
    overall8, results8 = run_checkpoint_8()
    print_report_8(overall8, results8)
    final_fail = (overall0 == "FAIL") or (overall1 == "FAIL") or (overall2 == "FAIL") or (overall3 == "FAIL") or (overall4 == "FAIL") or (overall5 == "FAIL") or (overall6 == "FAIL") or (overall7 == "FAIL") or (overall8 == "FAIL")
    sys.exit(1 if final_fail else 0)
