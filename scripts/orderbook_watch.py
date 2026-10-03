#!/usr/bin/env python3
import requests, time, csv, os
from datetime import datetime, timedelta, timezone

TESTNET = "https://cdn-ind.testnet.deltaex.org"
PROD = "https://api.india.delta.exchange"
SYMBOL = "BTCUSD"
CONTRACT_VALUE = 0.001
LOTS = 100
NOTIONAL_BTC = CONTRACT_VALUE * LOTS

DELAYS = [5,10,15,20,25,30,35,40,45,50]
CYCLE_SLEEP = 30
RETENTION_DAYS = 90

HIGH_SLIP_BUCKETS = [200,300,400,500,600,700,800,900,1000]
LATEST_EVENTS_LIMIT = 30

BASE_DIR = os.path.expanduser("~/crypto_tradingsystem")
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
CSV_PATH = os.path.join(DATA_DIR, "orderbook_history.csv")
HTML_PATH = os.path.join(REPORT_DIR, "orderbook_report.html")
REPORT_CSV_PATH = os.path.join(REPORT_DIR, "orderbook_report.csv")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

CSV_HEADER = ["timestamp","symbol","delay","env","side","slip_price","slip_100lot"]
START_TIME = datetime.now(timezone.utc)

def get_best_bid_ask(base_url):
    r = requests.get(f"{base_url}/v2/l2orderbook/{SYMBOL}", timeout=(3,10))
    r.raise_for_status()
    res = r.json()["result"]
    best_bid = float(res["buy"][0]["price"])
    best_ask = float(res["sell"][0]["price"])
    return best_bid, best_ask

def append_rows(rows):
    file_exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(CSV_HEADER)
        w.writerows(rows)

def rollover():
    if not os.path.exists(CSV_PATH):
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    keep = []
    with open(CSV_PATH, "r") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            try:
                ts = datetime.fromisoformat(row[0])
                if ts >= cutoff:
                    keep.append(row)
            except Exception:
                continue
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        w.writerows(keep)

def read_history():
    rows = []
    if not os.path.exists(CSV_PATH):
        return rows
    with open(CSV_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row["timestamp"] = datetime.fromisoformat(row["timestamp"])
                row["delay"] = int(row["delay"])
                row["slip_price"] = float(row["slip_price"])
                row["slip_100lot"] = float(row["slip_100lot"])
                rows.append(row)
            except Exception:
                continue
    return rows

def classify_bucket(abs_price):
    if abs_price < HIGH_SLIP_BUCKETS[0]:
        return None
    for i in range(len(HIGH_SLIP_BUCKETS)-1):
        lo = HIGH_SLIP_BUCKETS[i]; hi = HIGH_SLIP_BUCKETS[i+1]
        if lo <= abs_price < hi:
            return f"{lo}-{hi}"
    return f"{HIGH_SLIP_BUCKETS[-1]}+"

def classify_category(abs_price):
    if abs_price < 300:
        return "Normal/Sideways"
    elif abs_price < 500:
        return "Normal Volatility"
    elif abs_price < 1000:
        return "Strong/High Vol"
    else:
        return "Extreme Volatility"

def compute_high_slippage_summary():
    hist = read_history()
    hist = [r for r in hist if r["side"] in ("entry","exit")]

    events = []
    for r in hist:
        abs_price = abs(r["slip_price"])
        bucket = classify_bucket(abs_price)
        if bucket is None:
            continue
        category = classify_category(abs_price)
        events.append({
            "timestamp": r["timestamp"],
            "env": r["env"],
            "side": r["side"],
            "delay": r["delay"],
            "slip_price": r["slip_price"],
            "slip_100lot": r["slip_100lot"],
            "bucket": bucket,
            "category": category
        })

    monthly = {}
    for e in events:
        ym = e["timestamp"].strftime("%Y-%m")
        key = (ym, e["bucket"], e["category"])
        if key not in monthly:
            monthly[key] = {"testnet":0, "prod":0}
        monthly[key][e["env"]] += 1

    monthly_rows = []
    for (ym, bucket, category), counts in sorted(monthly.items()):
        monthly_rows.append((ym, bucket, category, counts["testnet"], counts["prod"]))

    latest_events = sorted(events, key=lambda e: e["timestamp"], reverse=True)[:LATEST_EVENTS_LIMIT]

    return monthly_rows, latest_events

def run_cycle():
    now = datetime.now(timezone.utc)
    t_bid0, t_ask0 = get_best_bid_ask(TESTNET)
    p_bid0, p_ask0 = get_best_bid_ask(PROD)

    rows = []
    entry_table = []
    exit_table = []
    rt_table = []

    for d in DELAYS:
        time.sleep(5)
        t_bid, t_ask = get_best_bid_ask(TESTNET)
        p_bid, p_ask = get_best_bid_ask(PROD)

        t_entry = t_ask - t_ask0
        p_entry = p_ask - p_ask0
        t_exit = t_bid0 - t_bid
        p_exit = p_bid0 - p_bid

        t_rt = t_bid - t_ask0
        p_rt = p_bid - p_ask0

        ts_str = now.isoformat()
        rows.append([ts_str, SYMBOL, d, "testnet", "entry", round(t_entry,4), round(t_entry*NOTIONAL_BTC,4)])
        rows.append([ts_str, SYMBOL, d, "prod", "entry", round(p_entry,4), round(p_entry*NOTIONAL_BTC,4)])
        rows.append([ts_str, SYMBOL, d, "testnet", "exit", round(t_exit,4), round(t_exit*NOTIONAL_BTC,4)])
        rows.append([ts_str, SYMBOL, d, "prod", "exit", round(p_exit,4), round(p_exit*NOTIONAL_BTC,4)])
        rows.append([ts_str, SYMBOL, d, "testnet", "roundtrip", round(t_rt,4), round(t_rt*NOTIONAL_BTC,4)])
        rows.append([ts_str, SYMBOL, d, "prod", "roundtrip", round(p_rt,4), round(p_rt*NOTIONAL_BTC,4)])

        entry_table.append((d, t_entry, t_entry*NOTIONAL_BTC, p_entry, p_entry*NOTIONAL_BTC))
        exit_table.append((d, t_exit, t_exit*NOTIONAL_BTC, p_exit, p_exit*NOTIONAL_BTC))
        rt_table.append((d, t_rt, t_rt*NOTIONAL_BTC, p_rt, p_rt*NOTIONAL_BTC))

    append_rows(rows)
    rollover()
    return now, entry_table, exit_table, rt_table

def print_top_table(title, table):
    print(f"\n--- {title} ---")
    print(f"{'Delay':<6}{'T_SlipPrice':<14}{'T_Slip$100lot':<16}{'P_SlipPrice':<14}{'P_Slip$100lot':<14}")
    for d, tp, t100, pp, p100 in table:
        print(f"{d:<6}{tp:<14.2f}{t100:<16.2f}{pp:<14.2f}{p100:<14.2f}")

def compute_rolling(side):
    hist = read_history()
    hist = [r for r in hist if r["side"] == side]
    now = datetime.now(timezone.utc)
    periods = {
        "1Day": timedelta(days=1),
        "2Day": timedelta(days=2),
        "3Day": timedelta(days=3),
        "Weekly": timedelta(days=7),
        "2Weekly": timedelta(days=14),
    }
    result = {}
    for pname, delta in periods.items():
        cutoff = now - delta
        subset = [r for r in hist if r["timestamp"] >= cutoff]
        n = len(subset)
        per_delay = {}
        for d in DELAYS:
            t_vals = [r["slip_price"] for r in subset if r["delay"] == d and r["env"] == "testnet"]
            p_vals = [r["slip_price"] for r in subset if r["delay"] == d and r["env"] == "prod"]
            t_avg = sum(t_vals)/len(t_vals) if t_vals else 0.0
            p_avg = sum(p_vals)/len(p_vals) if p_vals else 0.0
            per_delay[d] = (t_avg, p_avg)
        result[pname] = (n, per_delay)
    return result

def print_rolling_table(title, rolling):
    print(f"\n=== ROLLING AVERAGES - {title} ===")
    header = f"{'Period':<8}{'N':<6}" + "".join([f"D{d:<9}" for d in DELAYS])
    print(header)
    for pname, (n, per_delay) in rolling.items():
        line_t = f"{pname:<8}{n:<6}" + "".join([f"T:{per_delay[d][0]:<7.1f}" for d in DELAYS])
        line_p = f"{'':<8}{'':<6}" + "".join([f"P:{per_delay[d][1]:<7.1f}" for d in DELAYS])
        print(line_t)
        print(line_p)

def build_html(now, entry_table, exit_table, rt_table, roll_entry, roll_exit, roll_rt, monthly_rows, latest_events):
    def table_rows_top(table):
        rows = ""
        for d, tp, t100, pp, p100 in table:
            rows += f"<tr><td>{d}</td><td class='t'>{tp:.2f}</td><td class='t'>{t100:.2f}</td><td class='p'>{pp:.2f}</td><td class='p'>{p100:.2f}</td></tr>"
        return rows

    def table_rows_roll(rolling):
        rows = ""
        for pname, (n, per_delay) in rolling.items():
            rows += f"<tr><td>{pname}</td><td>{n}</td>"
            for d in DELAYS:
                t_avg, p_avg = per_delay[d]
                rows += f"<td class='t'>T:{t_avg:.1f}</td>"
            rows += "</tr><tr><td></td><td></td>"
            for d in DELAYS:
                t_avg, p_avg = per_delay[d]
                rows += f"<td class='p'>P:{p_avg:.1f}</td>"
            rows += "</tr>"
        return rows

    def table_rows_monthly(rows_data):
        rows = ""
        for ym, bucket, category, t_count, p_count in rows_data:
            rows += f"<tr><td>{ym}</td><td>{bucket}</td><td>{category}</td><td class='t'>{t_count}</td><td class='p'>{p_count}</td></tr>"
        return rows

    def table_rows_latest(events):
        rows = ""
        for e in events:
            cls = "t" if e["env"] == "testnet" else "p"
            rows += f"<tr><td>{e['timestamp'].isoformat()}</td><td class='{cls}'>{e['env']}</td><td>{e['side']}</td><td>{e['delay']}</td><td class='{cls}'>{e['slip_price']:.2f}</td><td class='{cls}'>{e['slip_100lot']:.2f}</td><td>{e['bucket']}</td><td>{e['category']}</td></tr>"
        return rows

    html = f"""
    <html><head><style>
    body {{ background:white; font-family:Arial; color:#111; }}
    table {{ border-collapse: collapse; margin-bottom:30px; width:100%; }}
    th, td {{ border:1px solid #ccc; padding:6px 10px; text-align:center; }}
    th {{ background:#2c3e50; color:white; }}
    td.t {{ background:#fdf3d1; }}
    td.p {{ background:#d4f0d4; }}
    h2 {{ background:#2c3e50; color:white; padding:8px; }}
    h3.hs {{ background:#8b0000; color:white; padding:8px; }}
    </style></head><body>
    <h2>Orderbook Report - {SYMBOL} &nbsp;|&nbsp; Started: {START_TIME.strftime('%d-%b-%Y %H:%M UTC')} &nbsp;|&nbsp; Latest Update: {now.strftime('%d-%b-%Y %H:%M:%S UTC')}</h2>

    <h3>Entry Side</h3>
    <table><tr><th>Delay</th><th>T_SlipPrice</th><th>T_Slip$100lot</th><th>P_SlipPrice</th><th>P_Slip$100lot</th></tr>
    {table_rows_top(entry_table)}</table>

    <h3>Exit Side</h3>
    <table><tr><th>Delay</th><th>T_SlipPrice</th><th>T_Slip$100lot</th><th>P_SlipPrice</th><th>P_Slip$100lot</th></tr>
    {table_rows_top(exit_table)}</table>

    <h3>Roundtrip (True Sequential Trade)</h3>
    <table><tr><th>Delay</th><th>T_SlipPrice</th><th>T_Slip$100lot</th><th>P_SlipPrice</th><th>P_Slip$100lot</th></tr>
    {table_rows_top(rt_table)}</table>

    <h3>Rolling Averages - Entry</h3>
    <table><tr><th>Period</th><th>N</th>{"".join(f"<th>D{d}</th>" for d in DELAYS)}</tr>
    {table_rows_roll(roll_entry)}</table>

    <h3>Rolling Averages - Exit</h3>
    <table><tr><th>Period</th><th>N</th>{"".join(f"<th>D{d}</th>" for d in DELAYS)}</tr>
    {table_rows_roll(roll_exit)}</table>

    <h3>Rolling Averages - Roundtrip</h3>
    <table><tr><th>Period</th><th>N</th>{"".join(f"<th>D{d}</th>" for d in DELAYS)}</tr>
    {table_rows_roll(roll_rt)}</table>

    <h3 class="hs">HIGH SLIPPAGE EVENTS - Monthly Count (Testnet vs Production)</h3>
    <table><tr><th>Month</th><th>Bucket</th><th>Category</th><th>Testnet Count</th><th>Production Count</th></tr>
    {table_rows_monthly(monthly_rows)}</table>

    <h3 class="hs">HIGH SLIPPAGE EVENTS - Latest {LATEST_EVENTS_LIMIT} (Any Time)</h3>
    <table><tr><th>Timestamp</th><th>Env</th><th>Side</th><th>Delay</th><th>SlipPrice</th><th>Slip$100lot</th><th>Bucket</th><th>Category</th></tr>
    {table_rows_latest(latest_events)}</table>

    </body></html>
    """
    with open(HTML_PATH, "w") as f:
        f.write(html)

def build_csv_report(now, entry_table, exit_table, rt_table, roll_entry, roll_exit, roll_rt, monthly_rows, latest_events):
    with open(REPORT_CSV_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Report Time", now.isoformat()])
        w.writerow(["Script Start Time", START_TIME.isoformat()])
        w.writerow([])

        for title, table in [("ENTRY SIDE", entry_table), ("EXIT SIDE", exit_table), ("ROUNDTRIP", rt_table)]:
            w.writerow([title])
            w.writerow(["Delay","T_SlipPrice","T_Slip100lot","P_SlipPrice","P_Slip100lot"])
            for d, tp, t100, pp, p100 in table:
                w.writerow([d, round(tp,2), round(t100,2), round(pp,2), round(p100,2)])
            w.writerow([])

        for title, rolling in [("ROLLING ENTRY", roll_entry), ("ROLLING EXIT", roll_exit), ("ROLLING ROUNDTRIP", roll_rt)]:
            w.writerow([title])
            w.writerow(["Period","N"] + [f"D{d}" for d in DELAYS])
            for pname, (n, per_delay) in rolling.items():
                t_row = [pname, n] + [round(per_delay[d][0],1) for d in DELAYS]
                p_row = ["", ""] + [round(per_delay[d][1],1) for d in DELAYS]
                w.writerow(t_row)
                w.writerow(p_row)
            w.writerow([])

        w.writerow(["HIGH SLIPPAGE EVENTS - MONTHLY COUNT"])
        w.writerow(["Month","Bucket","Category","Testnet Count","Production Count"])
        for ym, bucket, category, t_count, p_count in monthly_rows:
            w.writerow([ym, bucket, category, t_count, p_count])
        w.writerow([])

        w.writerow([f"HIGH SLIPPAGE EVENTS - LATEST {LATEST_EVENTS_LIMIT}"])
        w.writerow(["Timestamp","Env","Side","Delay","SlipPrice","Slip100lot","Bucket","Category"])
        for e in latest_events:
            w.writerow([e["timestamp"].isoformat(), e["env"], e["side"], e["delay"], round(e["slip_price"],2), round(e["slip_100lot"],2), e["bucket"], e["category"]])

def main():
    while True:
        try:
            now, entry_table, exit_table, rt_table = run_cycle()

            print(f"\n=== Cycle @ {now.isoformat()} | {SYMBOL} | {LOTS} lots ===")
            print_top_table("ENTRY SIDE (Buy)", entry_table)
            print_top_table("EXIT SIDE (Sell)", exit_table)
            print_top_table("ROUNDTRIP (True Sequential Trade)", rt_table)

            roll_entry = compute_rolling("entry")
            roll_exit = compute_rolling("exit")
            roll_rt = compute_rolling("roundtrip")

            print_rolling_table("ENTRY SIDE", roll_entry)
            print_rolling_table("EXIT SIDE", roll_exit)
            print_rolling_table("ROUNDTRIP", roll_rt)

            monthly_rows, latest_events = compute_high_slippage_summary()

            build_html(now, entry_table, exit_table, rt_table, roll_entry, roll_exit, roll_rt, monthly_rows, latest_events)
            build_csv_report(now, entry_table, exit_table, rt_table, roll_entry, roll_exit, roll_rt, monthly_rows, latest_events)
            print(f"\nHTML report saved: {HTML_PATH}")
            print(f"CSV report saved: {REPORT_CSV_PATH}")
            print(f"High slippage events found: {len(latest_events)} (showing latest {LATEST_EVENTS_LIMIT})")

        except Exception as e:
            print(f"ERROR in cycle: {e}")

        time.sleep(CYCLE_SLEEP)

if __name__ == "__main__":
    main()
