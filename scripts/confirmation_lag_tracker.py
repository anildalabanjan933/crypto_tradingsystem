import csv, os
from datetime import timezone

LAG_LOG = "logs/confirmation_lag_events.csv"

def log_lag_event(label, sig_ts, detected_at_ts, tf_minutes, direction, price_then, price_now):
    """Passive, log-only. Called from _fire() in renko_state_engine.py right after
    a signal fires. No new API calls, no thread, no blocking - csv.writer append
    using data _fire() already has in scope."""
    sig_ts_utc = sig_ts.replace(tzinfo=timezone.utc)
    lag_sec = detected_at_ts - sig_ts_utc.timestamp()
    expected_floor = tf_minutes * 60
    file_exists = os.path.exists(LAG_LOG)
    with open(LAG_LOG, "a", newline="") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["label","sig_ts","detected_at","lag_sec","exceeds_floor",
                        "direction","price_then","price_now","est_damage_usd"])
        exceeds_floor = lag_sec > expected_floor * 1.1
        est_damage = abs(price_now - price_then) * 100 * 0.001
        w.writerow([label, sig_ts_utc.isoformat(), detected_at_ts, round(lag_sec,1),
                    exceeds_floor, direction, price_then, price_now, round(est_damage,2)])
