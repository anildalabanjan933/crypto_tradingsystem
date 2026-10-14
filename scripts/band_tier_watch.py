import re, time, csv, os
from datetime import datetime, timezone

LOGS = {
    "S4": "logs/live_trading_s4.log",
    "S4V2": "logs/live_trading_s4v2.log",
    "S4V3": "logs/live_trading_s4v3.log",
    "TM1_S4": "logs/live_trading_testmember1_s4.log",
    "ENGINE": "logs/renko_state_engine.log",
}
OUT = "logs/band_tier_events.csv"
PATTERNS = {
    "BAND_RETRY": re.compile(r"cid=\w+_a([1-9])"),
    "BAND_ABANDONED": re.compile(r"ENTRY ABANDONED|unfilled_beyond_band"),
    "TIER0_SL": re.compile(r"[Ee]mergency SL|sl_pct=10"),
    "TIER1_SPEED": re.compile(r"speed.*%/min|Tier ?1"),
    "TIER2_LIQ": re.compile(r"dist_to_liq|Tier ?2|CRITICAL close"),
    "CLOSE_ESCALATION": re.compile(r"band=\$(500|750|1000)"),
    "CAP_EXHAUSTED_SKIP": re.compile(r"reconcile incomplete, signal SKIPPED"),
}

if not os.path.exists(OUT):
    with open(OUT, "w", newline="") as f:
        csv.writer(f).writerow(["logged_at_utc","bot","event_type","line"])

positions = {b: 0 for b in LOGS}

while True:
    for bot, path in LOGS.items():
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", errors="ignore") as f:
                f.seek(positions[bot])
                new_lines = f.readlines()
                positions[bot] = f.tell()
        except Exception:
            continue
        for line in new_lines:
            for etype, pat in PATTERNS.items():
                if pat.search(line):
                    with open(OUT, "a", newline="") as out:
                        csv.writer(out).writerow([
                            datetime.now(timezone.utc).isoformat(), bot, etype, line.strip()
                        ])
    time.sleep(30)
