import csv, re, glob, argparse
from datetime import datetime, timedelta

BT_GLOB = {
    "s4": "output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv",
    "s4v2": "output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv",
}
LV_FILE = {"s4": "logs/signals_s4.csv", "s4v2": "logs/signals_s4v2.csv"}
LOG_FILE = {"s4": "logs/live_trading_s4.log", "s4v2": "logs/live_trading_s4v2.log"}
ISSUE_KEYWORDS = ["LIQUIDATION RISK CRITICAL", "ORPHAN", "STUCK PENDING",
                  "SL HIT DETECTED", "ENTRY MISMATCH", "speed", "emergency",
                  "ENTRY FAILED", "ENTRY ABANDONED", "unfilled_beyond_band"]

def dt(s):
    return datetime.fromisoformat(s.replace("Z", ""))

def resolve_start_date(args):
    today = datetime.now().date()
    if args.date:
        return args.date
    if args.days:
        return (today - timedelta(days=args.days)).isoformat()
    return (today - timedelta(days=1)).isoformat()

def load_bt(bot, start_date):
    f = sorted(glob.glob(BT_GLOB[bot]))[-1]
    rows = []
    with open(f) as fh:
        for r in csv.DictReader(fh):
            if r["entry_datetime"] >= start_date:
                rows.append(r)
    return rows

def load_lv(bot, start_date):
    rows = []
    with open(LV_FILE[bot]) as fh:
        for r in csv.reader(fh):
            if r[0] >= start_date:
                rows.append({"entry_ts": r[0], "exit_ts": r[1], "direction": r[2],
                             "entry_price": r[4], "exit_price": r[5]})
    return rows

def preload_log(path):
    """Read log file ONCE, return list of (datetime, line) tuples."""
    events = []
    try:
        with open(path, errors="ignore") as fh:
            for line in fh:
                ts_str = line[:19]
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                events.append((ts, line))
    except FileNotFoundError:
        pass
    return events

def load_log_events(bot):
    entry_fill, close_fill, sl_hit = {}, [], {}
    pending_entry_ts = None
    pending_close = False
    with open(LOG_FILE[bot], errors="ignore") as fh:
        for line in fh:
            m = re.match(r'^(\S+ \S+),\d+ INFO \[ORDER\] ENTRY attempt \w+ \d+ lots \| dir=\w+ \| ts=(\S+) \| attempt=1/5', line)
            if m:
                pending_entry_ts = (m.group(1), m.group(2))
                continue
            m = re.match(r'^(\S+ \S+),\d+ INFO \[OrderManager\] Close order placed', line)
            if m:
                pending_close = m.group(1)
                continue
            m = re.match(r'^(\S+ \S+),\d+ INFO \[OrderManager\] Order filled', line)
            if m:
                if pending_entry_ts:
                    entry_fill[pending_entry_ts[1]] = m.group(1)
                    pending_entry_ts = None
                elif pending_close:
                    close_fill.append(m.group(1))
                    pending_close = False
                continue
            m = re.match(r'^(\S+ \S+),\d+ INFO \[SYNC\] CSV PENDING row exit filled: entry=(\S+) exit=(\S+) price=', line)
            if m:
                sl_hit[m.group(2)] = m.group(3)
    return entry_fill, close_fill, sl_hit

def scan_issues_fast(preloaded_events_list, start_ts, end_ts):
    issues = []
    try:
        s, e = dt(start_ts), dt(end_ts)
    except Exception:
        return ""
    for events in preloaded_events_list:
        for ts, line in events:
            if s <= ts <= e:
                for kw in ISSUE_KEYWORDS:
                    if kw.lower() in line.lower():
                        issues.append(kw)
            elif ts > e:
                break
    return ", ".join(sorted(set(issues))) if issues else "OK - no issues found"

def build_trades(bot, start_date, preloaded_events_list):
    bt_rows = load_bt(bot, start_date)
    lv_rows = load_lv(bot, start_date)
    entry_fill, close_fill, sl_hit = load_log_events(bot)
    lv_by_ts = {r["entry_ts"]: r for r in lv_rows}
    close_q = list(close_fill)
    trades = []
    for bt in bt_rows:
        ets = bt["entry_datetime"]
        xts = bt["exit_datetime"]
        lv = lv_by_ts.get(ets)
        bt_count_flag = 1
        lv_count_flag = 1 if lv else 0

        entry_delay = "N/A"
        if ets in entry_fill:
            try:
                fill_t = datetime.strptime(entry_fill[ets], "%Y-%m-%d %H:%M:%S")
                nom_t = dt(ets)
                entry_delay = int((fill_t - nom_t).total_seconds())
            except Exception:
                pass

        exit_delay = "N/A"
        exit_msg = ""
        if ets in sl_hit:
            exit_msg = "SL HIT - protective exit, delay N/A by design"
        elif close_q:
            try:
                fill_t = datetime.strptime(close_q.pop(0), "%Y-%m-%d %H:%M:%S")
                nom_t = dt(xts)
                exit_delay = int((fill_t - nom_t).total_seconds())
            except Exception:
                pass

        lv_entry_p = float(lv["entry_price"]) if lv else None
        lv_exit_p = float(lv["exit_price"]) if lv and lv["exit_ts"] else None
        bt_entry_p = float(bt["entry_price"])
        bt_exit_p = float(bt["exit_price"])
        direction = bt["direction"]
        sign = 1 if direction == "long" else -1

        net_slip = "N/A"
        if lv_entry_p is not None and lv_exit_p is not None:
            entry_slip = (lv_entry_p - bt_entry_p) * 100 * 0.001 * (-sign)
            exit_slip = (lv_exit_p - bt_exit_p) * 100 * 0.001 * sign
            net_slip = round(entry_slip + exit_slip, 2)

        issues = scan_issues_fast(preloaded_events_list, ets, xts)
        if exit_msg:
            issues = (exit_msg + "; " + issues) if issues != "OK - no issues found" else exit_msg

        trades.append({
            "bot": bot.upper(), "date": ets[:10], "direction": direction,
            "bt_entry": f"{ets[11:16]}/{bt_entry_p}", "lv_entry": f"{ets[11:16]}/{lv_entry_p}" if lv else "MISSED",
            "bt_exit": f"{xts[11:16]}/{bt_exit_p}", "lv_exit": f"{lv['exit_ts'][11:16]}/{lv_exit_p}" if lv else "MISSED",
            "entry_delay": entry_delay, "exit_delay": exit_delay,
            "net_slip": net_slip, "issue": issues,
            "bt_count": bt_count_flag, "lv_count": lv_count_flag,
        })
    return trades

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Custom start date YYYY-MM-DD")
    ap.add_argument("--days", type=int, help="Previous N days")
    args = ap.parse_args()
    start_date = resolve_start_date(args)

    all_trades = []
    for bot in ["s4", "s4v2"]:
        print(f"Loading {bot} log (one-time read)...", flush=True)
        events = preload_log(LOG_FILE[bot])
        pr_events = preload_log("logs/position_risk_monitor.log")
        print(f"Building trades for {bot}...", flush=True)
        all_trades.extend(build_trades(bot, start_date, [events, pr_events]))

    by_date = {}
    for t in all_trades:
        by_date.setdefault(t["date"], []).append(t)

    out_lines = [f"Report range: {start_date} to today (UTC)\n"]
    for date in sorted(by_date):
        rows = by_date[date]
        bt_count = sum(r["bt_count"] for r in rows)
        lv_count = sum(r["lv_count"] for r in rows)
        out_lines.append(f"\n=== DATE: {date} | BT trade count: {bt_count} | FWD-TEST trade count: {lv_count} ===")
        out_lines.append(f"{'BOT':6}| {'DIR':6}| {'ENTRY TIME/PRICE (BT vs LV)':32}| {'EXIT TIME/PRICE (BT vs LV)':32}| {'ENTRY DELAY(s)':14}| {'EXIT DELAY(s)':14}| {'NET SLIP($)':12}| MESSAGE/ISSUE")
        out_lines.append("-" * 160)
        for r in rows:
            out_lines.append(
                f"{r['bot']:6}| {r['direction']:6}| {r['bt_entry']} vs {r['lv_entry']:18}| "
                f"{r['bt_exit']} vs {r['lv_exit']:18}| {str(r['entry_delay']):14}| {str(r['exit_delay']):14}| "
                f"{str(r['net_slip']):12}| {r['issue']}"
            )

    report = "\n".join(out_lines)
    print(report)
    with open("output/daily_bt_vs_live_report.txt", "w") as f:
        f.write(report)

if __name__ == "__main__":
    main()
