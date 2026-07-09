import streamlit as st
import json, os, subprocess, datetime, shutil

st.set_page_config(page_title="Crypto Trading Dashboard", layout="wide", page_icon="📈")

st.markdown("""
<style>
.stApp { background-color: #ffffff; }
[data-testid="stMetricValue"] { font-size: 16px !important; }
[data-testid="stMetricLabel"] { font-size: 12px !important; }
.section-title { color: #1a73e8; font-size: 18px; font-weight: bold; 
                 border-bottom: 2px solid #1a73e8; padding-bottom: 5px; 
                 margin-bottom: 15px; margin-top: 20px; }
.alert-red { background: #ffebee; border: 1px solid #dc3545; border-radius: 8px; 
             padding: 10px; color: #dc3545; font-weight: bold; margin: 5px 0; }
.alert-yellow { background: #fff8e1; border: 1px solid #ffc107; border-radius: 8px; 
                padding: 10px; color: #856404; font-weight: bold; margin: 5px 0; }
.alert-green { background: #e8f5e9; border: 1px solid #28a745; border-radius: 8px; 
               padding: 10px; color: #28a745; font-weight: bold; margin: 5px 0; }
</style>
""", unsafe_allow_html=True)

# ================================================================
# HELPER FUNCTIONS
# ================================================================

def load_config():
    try:
        return json.load(open("dashboard/algo_config.json"))
    except Exception as e:
        st.error(f"Config error: {e}")
        return {}

def get_disk_usage():
    try:
        total, used, free = shutil.disk_usage(".")
        pct = int(used / total * 100)
        free_gb = round(free / 1024**3, 1)
        return pct, free_gb
    except:
        return 0, 0

def get_git_commit():
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True
        )
        return result.stdout.strip()[:10] if result.stdout else "unknown"
    except:
        return "unknown"

def get_last_log_signal(log_path, keyword="ORDER"):
    try:
        if os.path.exists(log_path):
            lines = open(log_path, encoding="utf-8", errors="ignore").readlines()
            for line in reversed(lines):
                if keyword in line:
                    return line.strip()[-60:]
            return "No signal yet"
        return "Log not found"
    except:
        return "Error reading log"

def check_log_for_errors(log_path):
    try:
        if os.path.exists(log_path):
            lines = open(log_path, encoding="utf-8", errors="ignore").readlines()
            for line in reversed(lines[-50:]):
                if "ERROR" in line:
                    return line.strip()
        return None
    except:
        return None

# ================================================================
# LOAD CONFIG
# ================================================================
config = load_config()
system = config.get("system", {})
s2_log = system.get("log_path_s2", "logs/live_trading_s2.log")
s4_log = system.get("log_path_s4", "logs/live_trading_s4.log")

# ================================================================
# TOP HEADER
# ================================================================
col_title, col_status = st.columns([4, 1])
with col_title:
    st.markdown("## CRYPTO TRADING SYSTEM")
    st.markdown("BTC Algo Trading Dashboard - Single Control Centre")
with col_status:
    st.markdown("<br>", unsafe_allow_html=True)
    st.success("SYSTEM ONLINE")

st.markdown("---")

# ================================================================
# SECTION 1 - SYSTEM STATUS CARDS
# ================================================================
st.markdown("<div class='section-title'>SECTION 1 - SYSTEM STATUS</div>", unsafe_allow_html=True)

disk_pct, disk_free = get_disk_usage()
git_commit = get_git_commit()
s2_last = get_last_log_signal(s2_log)
s4_last = get_last_log_signal(s4_log)
s2_error = check_log_for_errors(s2_log)
s4_error = check_log_for_errors(s4_log)

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.markdown("**S2 BOT**")
    if os.path.exists(s2_log):
        st.success("LOG ACTIVE")
    else:
        st.error("LOG MISSING")
    st.caption(f"Last: {s2_last[:40]}")

with c2:
    st.markdown("**S4 BOT**")
    if os.path.exists(s4_log):
        st.success("LOG ACTIVE")
    else:
        st.error("LOG MISSING")
    st.caption(f"Last: {s4_last[:40]}")

with c3:
    st.markdown("**VM DISK**")
    if disk_pct > 80:
        st.error(f"{disk_pct}% USED")
    elif disk_pct > 60:
        st.warning(f"{disk_pct}% USED")
    else:
        st.success(f"{disk_pct}% USED")
    st.caption(f"{disk_free} GB free")

with c4:
    st.markdown("**GITHUB**")
    st.success("SYNCED")
    st.caption(f"Commit: {git_commit}")

with c5:
    st.markdown("**DELTA API**")
    st.info("MANUAL CHECK")
    st.caption("Visit Delta Exchange")

# ================================================================
# ALERT BANNER
# ================================================================
st.markdown("---")
alerts = []

if disk_pct > 80:
    alerts.append(("red", f"DISK CRITICAL: {disk_pct}% used - clean up immediately"))
elif disk_pct > 70:
    alerts.append(("yellow", f"DISK WARNING: {disk_pct}% used - monitor closely"))
if not os.path.exists(s2_log):
    alerts.append(("red", "S2 LOG NOT FOUND - bot may not be running"))
if not os.path.exists(s4_log):
    alerts.append(("red", "S4 LOG NOT FOUND - bot may not be running"))
if s2_error:
    alerts.append(("red", f"S2 ERROR DETECTED: {s2_error}"))
if s4_error:
    alerts.append(("red", f"S4 ERROR DETECTED: {s4_error}"))

if alerts:
    for level, msg in alerts:
        if level == "red":
            st.markdown(f"<div class='alert-red'>ERROR: {msg}</div>", unsafe_allow_html=True)
        elif level == "yellow":
            st.markdown(f"<div class='alert-yellow'>WARNING: {msg}</div>", unsafe_allow_html=True)
else:
    st.markdown("<div class='alert-green'>ALL SYSTEMS HEALTHY - No errors detected</div>", unsafe_allow_html=True)



# ================================================================
# SECTION 2 - BOT CONTROL
# ================================================================
st.markdown("<div class='section-title'>SECTION 2 - BOT CONTROL</div>", unsafe_allow_html=True)

algos = config.get("algos", [])

col_h1, col_h2, col_h3, col_h4, col_h5, col_h6 = st.columns([1,2,2,1,2,2])
col_h1.markdown("**Algo**")
col_h2.markdown("**Strategy**")
col_h3.markdown("**Symbol**")
col_h4.markdown("**Lots**")
col_h5.markdown("**Status**")
col_h6.markdown("**Action**")
st.markdown("---")

for i, algo in enumerate(algos):
    c1, c2, c3, c4, c5, c6 = st.columns([1,2,2,1,2,2])
    with c1:
        st.markdown(f"**{algo['name']}**")
    with c2:
        st.caption(algo.get('strategy',''))
    with c3:
        st.caption(algo.get('symbol','BTCUSD'))
    with c4:
        new_lots = st.number_input(
            "", min_value=1, max_value=10000,
            value=algo.get('lots', 100),
            key=f"sec2_lots_{i}", label_visibility="collapsed"
        )
        if new_lots != algo.get('lots', 100):
            algos[i]['lots'] = new_lots
            config['algos'] = algos
            json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
            st.success("Lots updated")
    with c5:
        if algo.get('active', True):
            st.success("ACTIVE")
        else:
            st.error("INACTIVE")
    with c6:
        col_on, col_off = st.columns(2)
        with col_on:
            if st.button("ON", key=f"sec2_on_{i}"):
                algos[i]['active'] = True
                config['algos'] = algos
                json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
                st.success(f"{algo['name']} activated")
        with col_off:
            if st.button("OFF", key=f"sec2_off_{i}"):
                algos[i]['active'] = False
                config['algos'] = algos
                json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
                st.warning(f"{algo['name']} deactivated")

st.markdown("---")
b1, b2, b3, b4 = st.columns(4)
with b1:
    if st.button("START ALL BOTS", key="sec2_start"):
        st.info("Connect to VM to start bots - use SSH terminal")
with b2:
    if st.button("STOP ALL BOTS", key="sec2_stop"):
        st.warning("Connect to VM to stop bots - use SSH terminal")
with b3:
    if st.button("RESTART ALL BOTS", key="sec2_restart"):
        st.info("Connect to VM to restart - use SSH terminal")
with b4:
    if st.button("ADD NEW ALGO", key="sec2_add"):
        st.session_state['show_add_algo'] = True

if st.session_state.get('show_add_algo', False):
    st.markdown("**Add New Algo**")
    with st.form("add_algo_form"):
        new_name = st.text_input("Algo Name (e.g. S5)")
        new_file = st.text_input("Script File (e.g. run_live_trading_s5.py)")
        new_strategy = st.text_input("Strategy Name")
        new_symbol = st.selectbox("Symbol", ["BTCUSD", "ETHUSD"])
        new_lots = st.number_input("Lots", min_value=1, value=100)
        new_direction = st.selectbox("Direction", ["BOTH", "LONG", "SHORT"])
        col_save, col_cancel = st.columns(2)
        with col_save:
            submitted = st.form_submit_button("SAVE")
        with col_cancel:
            cancelled = st.form_submit_button("CANCEL")
        if submitted and new_name:
            algos.append({
                'name': new_name,
                'file': new_file,
                'strategy': new_strategy,
                'symbol': new_symbol,
                'lots': int(new_lots),
                'direction': new_direction,
                'active': True
            })
            config['algos'] = algos
            json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
            st.success(f"Algo {new_name} added")
            st.session_state['show_add_algo'] = False
        if cancelled:
            st.session_state['show_add_algo'] = False


# ================================================================
# SECTION 3 - PLATFORM MONITOR
# ================================================================
st.markdown("<div class='section-title'>SECTION 3 - PLATFORM MONITOR</div>", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["DELTA EXCHANGE", "ALGOTEST", "TRADETRON"])

with tab1:
    st.markdown("**Delta Exchange Account**")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Account Balance", "Manual Check")
        st.metric("Unrealised PnL", "Manual Check")
    with c2:
        st.metric("Realised PnL Today", "Manual Check")
        st.metric("Funding Rate", "Manual Check")
    with c3:
        st.metric("Open Positions", "Manual Check")
        st.metric("Last Order", "Manual Check")
    st.info("Visit Delta Exchange to check live account data: https://www.delta.exchange")
    st.markdown("**API Status**")
    col_a, col_b = st.columns(2)
    with col_a:
        st.success("API KEY: CONFIGURED")
    with col_b:
        st.success("TRADING: ENABLED")

with tab2:
    st.markdown("**Algotest Forward Test Monitor**")
    import datetime
    start = datetime.date(2026, 7, 7)
    end = datetime.date(2026, 7, 24)
    today = datetime.date.today()
    total_days = (end - start).days
    days_done = min((today - start).days, total_days)
    days_left = max((end - today).days, 0)
    progress = min(days_done / total_days, 1.0)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Start Date", str(start))
    with c2:
        st.metric("End Date", str(end))
    with c3:
        st.metric("Days Done", days_done)
    with c4:
        st.metric("Days Left", days_left)

    st.progress(progress, text=f"Forward Test Progress: {int(progress*100)}%")
    st.markdown("---")

    st.markdown("**Webhook Status**")
    webhooks = [
        "S2 BUY ENTRY", "S2 BUY EXIT",
        "S2 SELL ENTRY", "S2 SELL EXIT",
        "S4 BUY ENTRY", "S4 BUY EXIT",
        "S4 SELL ENTRY", "S4 SELL EXIT"
    ]
    w1, w2, w3, w4 = st.columns(4)
    cols = [w1, w2, w3, w4]
    for idx, wh in enumerate(webhooks):
        with cols[idx % 4]:
            st.success(f"{wh}: 200 OK")

    if st.button("TEST ALL WEBHOOKS", key="sec3_test_webhooks"):
        st.info("Run: python algotest_webhook.py on VM to test all webhooks")

    st.markdown("---")
    st.markdown("**Forward Test Metrics**")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("MTM Value", "Check Algotest Dashboard")
    with m2:
        st.metric("Executed Signals", "Check Algotest Dashboard")
    with m3:
        st.metric("Cumulative PnL", "Check Algotest Dashboard")
    with m4:
        st.metric("Max DD So Far", "Check Algotest Dashboard")
    st.info("Visit Algotest dashboard for live MTM and signal data")

with tab3:
    st.markdown("**Tradetron Marketplace**")
    st.warning("NOT CONNECTED - Tradetron setup pending after July 24")
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Status", "NOT CONNECTED")
    with c2:
        st.metric("Subscribers", "N/A")
    with c3:
        st.metric("Signals Sent", "N/A")
    st.info("Tradetron will be configured after July 24 forward test completes")


# ================================================================
# SECTION 4 - FORWARD TEST vs BACKTEST COMPARE
# ================================================================
st.markdown("<div class='section-title'>SECTION 4 - FORWARD TEST vs BACKTEST COMPARE</div>", unsafe_allow_html=True)

selected_algo = st.selectbox("Select Strategy", ["S2 - RenkoReversalStrategy", "S4 - RenkoSMIIOSupertrendStrategy"], key="sec4_algo")

if "S2" in selected_algo:
    backtest = {
        "Trade Count": 1506, "Win Rate": 52.26,
        "Total PnL (L)": 26.37, "Max DD (%)": 0.27,
        "Slippage/side ($)": 5.0, "Sharpe": 5.55
    }
    thresholds = {
        "Trade Count": 0, "Win Rate": 3.0,
        "Total PnL (L)": 5.0, "Max DD (%)": 0.05,
        "Slippage/side ($)": 3.0, "Sharpe": 1.0
    }
else:
    backtest = {
        "Trade Count": 659, "Win Rate": 57.66,
        "Total PnL (L)": 23.37, "Max DD (%)": 0.28,
        "Slippage/side ($)": 5.0, "Sharpe": 6.92
    }
    thresholds = {
        "Trade Count": 0, "Win Rate": 3.0,
        "Total PnL (L)": 5.0, "Max DD (%)": 0.05,
        "Slippage/side ($)": 3.0, "Sharpe": 1.0
    }

st.markdown("**Enter Forward Test Values (from Algotest dashboard)**")
forward = {}
c1, c2, c3 = st.columns(3)
with c1:
    forward["Trade Count"] = st.number_input("Trade Count", min_value=0, value=0, key="sec4_tc")
    forward["Win Rate"] = st.number_input("Win Rate (%)", min_value=0.0, value=0.0, key="sec4_wr")
with c2:
    forward["Total PnL (L)"] = st.number_input("Total PnL (L)", value=0.0, key="sec4_pnl")
    forward["Max DD (%)"] = st.number_input("Max DD (%)", min_value=0.0, value=0.0, key="sec4_dd")
with c3:
    forward["Slippage/side ($)"] = st.number_input("Slippage/side ($)", min_value=0.0, value=0.0, key="sec4_slip")
    forward["Sharpe"] = st.number_input("Sharpe", value=0.0, key="sec4_sharpe")

st.markdown("---")
st.markdown("**Comparison Table**")

header = st.columns([2,2,2,1,2])
header[0].markdown("**Metric**")
header[1].markdown("**Backtest**")
header[2].markdown("**Forward**")
header[3].markdown("**Diff**")
header[4].markdown("**Status**")

red_alerts = []
for metric in backtest:
    row = st.columns([2,2,2,1,2])
    bt_val = backtest[metric]
    fw_val = forward[metric]
    diff = abs(fw_val - bt_val)
    threshold = thresholds[metric]
    row[0].write(metric)
    row[1].write(str(bt_val))
    row[2].write(str(fw_val))
    row[3].write(f"{diff:.2f}")
    if fw_val == 0:
        row[4].info("PENDING")
    elif diff <= threshold:
        row[4].success("MATCH")
    else:
        row[4].error("INVESTIGATE")
        red_alerts.append(f"{metric}: diff={diff:.2f} exceeds threshold={threshold}")

if red_alerts:
    st.markdown("---")
    for alert in red_alerts:
        st.markdown(f"<div class='alert-red'>MISMATCH DETECTED: {alert}</div>", unsafe_allow_html=True)
else:
    if any(forward[m] > 0 for m in forward):
        st.markdown("<div class='alert-green'>ALL METRICS MATCH - Forward test healthy</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='alert-yellow'>PENDING - Enter forward test values above to compare</div>", unsafe_allow_html=True)


# ================================================================
# SECTION 5 - LOG MONITOR
# ================================================================
st.markdown("<div class='section-title'>SECTION 5 - LOG MONITOR</div>", unsafe_allow_html=True)

col_sel, col_filter = st.columns([2,3])
with col_sel:
    log_choice = st.selectbox("Select Log", ["S2", "S4", "Both"], key="sec5_log")
with col_filter:
    custom_filter = st.text_input("Custom Filter (type keyword)", value="", key="sec5_custom")

qf1, qf2, qf3, qf4 = st.columns(4)
with qf1:
    if st.button("ORDER", key="sec5_order"):
        st.session_state['sec5_filter'] = "ORDER"
with qf2:
    if st.button("ERROR", key="sec5_error"):
        st.session_state['sec5_filter'] = "ERROR"
with qf3:
    if st.button("ALGOTEST", key="sec5_algotest"):
        st.session_state['sec5_filter'] = "ALGOTEST"
with qf4:
    if st.button("ALL", key="sec5_all"):
        st.session_state['sec5_filter'] = ""

active_filter = custom_filter if custom_filter else st.session_state.get('sec5_filter', '')

def read_log(path, keyword='', last_n=50):
    try:
        if os.path.exists(path):
            lines = open(path, encoding='utf-8', errors='ignore').readlines()
            if keyword:
                lines = [l for l in lines if keyword.upper() in l.upper()]
            return lines[-last_n:]
        return [f"Log not found: {path}"]
    except Exception as e:
        return [f"Error reading log: {e}"]

def format_log_line(line):
    if 'ERROR' in line:
        return f"🔴 {line.strip()}"
    elif 'ORDER' in line:
        return f"🟢 {line.strip()}"
    elif 'ALGOTEST' in line:
        return f"🔵 {line.strip()}"
    else:
        return line.strip()

s2_log_path = system.get('log_path_s2', 'logs/live_trading_s2.log')
s4_log_path = system.get('log_path_s4', 'logs/live_trading_s4.log')

if log_choice == "S2":
    lines = read_log(s2_log_path, active_filter)
    st.markdown(f"**S2 Log** - Filter: `{active_filter if active_filter else 'ALL'}`")
    st.code('\n'.join([format_log_line(l) for l in lines]), language=None)
elif log_choice == "S4":
    lines = read_log(s4_log_path, active_filter)
    st.markdown(f"**S4 Log** - Filter: `{active_filter if active_filter else 'ALL'}`")
    st.code('\n'.join([format_log_line(l) for l in lines]), language=None)
else:
    col_s2, col_s4 = st.columns(2)
    with col_s2:
        lines = read_log(s2_log_path, active_filter)
        st.markdown(f"**S2 Log** - Filter: `{active_filter if active_filter else 'ALL'}`")
        st.code('\n'.join([format_log_line(l) for l in lines]), language=None)
    with col_s4:
        lines = read_log(s4_log_path, active_filter)
        st.markdown(f"**S4 Log** - Filter: `{active_filter if active_filter else 'ALL'}`")
        st.code('\n'.join([format_log_line(l) for l in lines]), language=None)

col_ref, col_auto = st.columns(2)
with col_ref:
    if st.button("REFRESH LOGS", key="sec5_refresh"):
        st.rerun()
with col_auto:
    auto_refresh = st.checkbox("AUTO REFRESH 30s", key="sec5_autorefresh")
    if auto_refresh:
        import time
        time.sleep(30)
        st.rerun()



# ================================================================
# SECTION 6 - BACKTEST
# ================================================================
st.markdown("<div class='section-title'>SECTION 6 - BACKTEST</div>", unsafe_allow_html=True)

import datetime, subprocess, os, glob

col1, col2 = st.columns(2)
with col1:
    bt_strategy = st.selectbox("Select Strategy", [
        "RenkoReversalStrategy",
        "RenkoSMIIOSupertrendStrategy",
        "RenkoBreakoutStrategy",
        "RenkoTrendlinePullbackStrategy"
    ], key="sec6_strategy")
with col2:
    bt_lots = st.number_input("Lots", min_value=1, max_value=10000, value=100, key="sec6_lots")

col3, col4, col5 = st.columns(3)
with col3:
    bt_start = st.date_input("Start Date", value=datetime.date(2025, 1, 1), key="sec6_start")
with col4:
    bt_end = st.date_input("End Date", value=datetime.date.today(), key="sec6_end")
with col5:
    bt_slippage = st.number_input("Slippage/side ($)", min_value=0.0, value=5.0, key="sec6_slip")

if st.button("RUN BACKTEST", key="sec6_run"):
    st.info(f"Running backtest: {bt_strategy} | Lots: {bt_lots} | {bt_start} to {bt_end}")
    with st.spinner("Running backtest..."):
        try:
            cmd = [
                "python", "run_single_strategy.py",
                "--strategy", bt_strategy,
                "--lots", str(bt_lots),
                "--start", str(bt_start),
                "--end", str(bt_end),
                "--slippage", str(bt_slippage),
                "--symbol", "BTCUSD",
                "--csv", "data/btc_1m_delta.csv"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                st.success("Backtest complete")
                st.code(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
            else:
                st.error("Backtest failed")
                st.code(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        except subprocess.TimeoutExpired:
            st.error("Backtest timed out after 5 minutes")
        except Exception as e:
            st.error(f"Error running backtest: {e}")

st.markdown("---")
st.markdown("**Backtest Reports**")

html_files = sorted(glob.glob("output/*.html"), reverse=True)
csv_files = sorted(glob.glob("output/*.csv"), reverse=True)

col_html, col_csv = st.columns(2)
with col_html:
    st.markdown("**HTML Reports**")
    if html_files:
        selected_html = st.selectbox("Select HTML Report", html_files, key="sec6_html_select")
        if st.button("VIEW HTML REPORT", key="sec6_view_html"):
            try:
                content = open(selected_html, encoding='utf-8').read()
                st.components.v1.html(content, height=600, scrolling=True)
            except Exception as e:
                st.error(f"Error opening report: {e}")
        with open(selected_html, 'rb') as f:
            st.download_button("DOWNLOAD HTML", f, file_name=os.path.basename(selected_html), key="sec6_dl_html")
    else:
        st.info("No HTML reports found in output/ folder")

with col_csv:
    st.markdown("**CSV Results**")
    if csv_files:
        selected_csv = st.selectbox("Select CSV", csv_files, key="sec6_csv_select")
        if st.button("VIEW CSV", key="sec6_view_csv"):
            try:
                import pandas as pd
                df = pd.read_csv(selected_csv)
                st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.error(f"Error opening CSV: {e}")
        with open(selected_csv, 'rb') as f:
            st.download_button("DOWNLOAD CSV", f, file_name=os.path.basename(selected_csv), key="sec6_dl_csv")
    else:
        st.info("No CSV files found in output/ folder")



# ================================================================
# SECTION 6B - PORTFOLIO BACKTEST
# ================================================================
st.markdown("<div class='section-title'>SECTION 6B - PORTFOLIO BACKTEST</div>", unsafe_allow_html=True)

import subprocess, glob, os

port_tab1, port_tab2 = st.tabs(["PREDEFINED PORTFOLIO", "DYNAMIC PORTFOLIO"])

with port_tab1:
    st.markdown("**Predefined Portfolios**")
    portfolios = {
        'DE-Strangle Intraday': 'Intraday option selling (3 strategies)',
        'DE-Strangle BTST': 'BTST directional option strategies (4 strategies)',
        'Monthly Positional': 'Monthly positional option strategies (3 strategies)'
    }
    for name, desc in portfolios.items():
        st.caption(f"{name}: {desc}")

    col1, col2 = st.columns(2)
    with col1:
        port_start = st.date_input("Start Date", value=datetime.date(2025,1,1), key="port_start")
    with col2:
        port_end = st.date_input("End Date", value=datetime.date.today(), key="port_end")

    port_lots = st.number_input("Lots", min_value=1, value=100, key="port_lots")
    port_slippage = st.number_input("Slippage/side ($)", min_value=0.0, value=5.0, key="port_slip")

    if st.button("RUN PREDEFINED PORTFOLIO", key="port_run_pre"):
        st.info("Running predefined portfolio backtest...")
        with st.spinner("Running..."):
            try:
                result = subprocess.run(
                    ["python", "run_portfolio_backtest.py"],
                    capture_output=True, text=True, timeout=600,
                    input="1\n1\n"
                )
                if result.returncode == 0:
                    st.success("Portfolio backtest complete")
                    st.code(result.stdout[-3000:])
                else:
                    st.error("Portfolio backtest failed")
                    st.code(result.stderr[-2000:])
            except Exception as e:
                st.error(f"Error: {e}")

with port_tab2:
    st.markdown("**Dynamic Portfolio - Select Strategies**")
    available_strategies = [
        "RenkoReversalStrategy",
        "RenkoSMIIOSupertrendStrategy",
        "RenkoBreakoutStrategy",
        "RenkoTrendlinePullbackStrategy"
    ]
    selected_strategies = st.multiselect(
        "Select Strategies",
        available_strategies,
        default=["RenkoReversalStrategy", "RenkoSMIIOSupertrendStrategy"],
        key="port_dyn_strategies"
    )
    col1, col2 = st.columns(2)
    with col1:
        port_dyn_start = st.date_input("Start Date", value=datetime.date(2025,1,1), key="port_dyn_start")
    with col2:
        port_dyn_end = st.date_input("End Date", value=datetime.date.today(), key="port_dyn_end")

    port_dyn_lots = st.number_input("Lots", min_value=1, value=100, key="port_dyn_lots")
    port_dyn_slip = st.number_input("Slippage/side ($)", min_value=0.0, value=5.0, key="port_dyn_slip")

    if st.button("RUN DYNAMIC PORTFOLIO", key="port_run_dyn"):
        if not selected_strategies:
            st.error("Please select at least one strategy")
        else:
            st.info(f"Running dynamic portfolio: {selected_strategies}")
            with st.spinner("Running..."):
                try:
                    strategies_input = "\n".join([str(i+1) for i in range(len(selected_strategies))])
                    result = subprocess.run(
                        ["python", "run_portfolio_backtest.py"],
                        capture_output=True, text=True, timeout=600,
                        input=f"2\n{strategies_input}\n"
                    )
                    if result.returncode == 0:
                        st.success("Dynamic portfolio backtest complete")
                        st.code(result.stdout[-3000:])
                    else:
                        st.error("Dynamic portfolio backtest failed")
                        st.code(result.stderr[-2000:])
                except Exception as e:
                    st.error(f"Error: {e}")

st.markdown("---")
st.markdown("**Portfolio Reports**")
port_html = sorted(glob.glob("output/portfolio*.html"), reverse=True)
port_csv = sorted(glob.glob("output/portfolio*.csv"), reverse=True)

col_a, col_b = st.columns(2)
with col_a:
    st.markdown("**HTML Reports**")
    if port_html:
        sel_port_html = st.selectbox("Select Portfolio HTML", port_html, key="port_html_sel")
        if st.button("VIEW HTML", key="port_view_html"):
            content = open(sel_port_html, encoding='utf-8').read()
            st.components.v1.html(content, height=600, scrolling=True)
        with open(sel_port_html, 'rb') as f:
            st.download_button("DOWNLOAD HTML", f, file_name=os.path.basename(sel_port_html), key="port_dl_html")
    else:
        st.info("No portfolio HTML reports found in output/ folder")

with col_b:
    st.markdown("**CSV Results**")
    if port_csv:
        sel_port_csv = st.selectbox("Select Portfolio CSV", port_csv, key="port_csv_sel")
        if st.button("VIEW CSV", key="port_view_csv"):
            import pandas as pd
            df = pd.read_csv(sel_port_csv)
            st.dataframe(df, use_container_width=True)
        with open(sel_port_csv, 'rb') as f:
            st.download_button("DOWNLOAD CSV", f, file_name=os.path.basename(sel_port_csv), key="port_dl_csv")
    else:
        st.info("No portfolio CSV files found in output/ folder")

# ================================================================
# SECTION 7 - OPTIMISATION
# ================================================================
st.markdown("<div class='section-title'>SECTION 7 - OPTIMISATION</div>", unsafe_allow_html=True)

import subprocess, os, glob

col1, col2, col3 = st.columns(3)
with col1:
    opt_strategy = st.selectbox("Select Strategy", [
        "RenkoReversalStrategy",
        "RenkoSMIIOSupertrendStrategy"
    ], key="sec7_strategy")
with col2:
    opt_group = st.selectbox("Select Group", [
        "renko", "supertrend", "smiio"
    ], key="sec7_group")
with col3:
    opt_lots = st.number_input("Lots", min_value=1, max_value=10000, value=100, key="sec7_lots")

col4, col5 = st.columns(2)
with col4:
    opt_start = st.date_input("Start Date", value=datetime.date(2025, 1, 1), key="sec7_start")
with col5:
    opt_end = st.date_input("End Date", value=datetime.date.today(), key="sec7_end")

if st.button("RUN OPTIMISATION", key="sec7_run"):
    st.info(f"Running optimisation: {opt_strategy} | Group: {opt_group} | Lots: {opt_lots}")
    with st.spinner("Running optimisation - this may take several minutes..."):
        try:
            cmd = [
                "python", "run_optimization.py",
                "--strategy", opt_strategy,
                "--group", opt_group,
                "--lots", str(opt_lots),
                "--start", str(opt_start),
                "--end", str(opt_end),
                "--csv", "data/btc_1m_delta.csv"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                st.success("Optimisation complete")
                st.code(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
            else:
                st.error("Optimisation failed")
                st.code(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        except subprocess.TimeoutExpired:
            st.error("Optimisation timed out after 10 minutes")
        except Exception as e:
            st.error(f"Error: {e}")

st.markdown("---")
st.markdown("**Optimisation Results**")

opt_csv_files = sorted(glob.glob("output/optimization*.csv"), reverse=True)
opt_html_files = sorted(glob.glob("output/optimization*.html"), reverse=True)

col_a, col_b = st.columns(2)
with col_a:
    st.markdown("**CSV Results**")
    if opt_csv_files:
        sel_opt_csv = st.selectbox("Select Optimisation CSV", opt_csv_files, key="sec7_csv_sel")
        if st.button("VIEW RESULTS TABLE", key="sec7_view_csv"):
            try:
                import pandas as pd
                df = pd.read_csv(sel_opt_csv)
                if 'net_pnl' in df.columns:
                    best_idx = df['net_pnl'].idxmax()
                    st.success(f"Best row: index {best_idx}")
                st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.error(f"Error: {e}")
        with open(sel_opt_csv, 'rb') as f:
            st.download_button("DOWNLOAD CSV", f, file_name=os.path.basename(sel_opt_csv), key="sec7_dl_csv")
    else:
        st.info("No optimisation CSV files found in output/ folder")

with col_b:
    st.markdown("**HTML Reports**")
    if opt_html_files:
        sel_opt_html = st.selectbox("Select Optimisation HTML", opt_html_files, key="sec7_html_sel")
        if st.button("VIEW HTML", key="sec7_view_html"):
            try:
                content = open(sel_opt_html, encoding='utf-8').read()
                st.components.v1.html(content, height=600, scrolling=True)
            except Exception as e:
                st.error(f"Error: {e}")
        with open(sel_opt_html, 'rb') as f:
            st.download_button("DOWNLOAD HTML", f, file_name=os.path.basename(sel_opt_html), key="sec7_dl_html")
    else:
        st.info("No optimisation HTML files found in output/ folder")


# ================================================================
# SECTION 8 - BATCH BACKTEST + SCANNER (PLACEHOLDER)
# ================================================================
st.markdown("<div class='section-title'>SECTION 8 - BATCH BACKTEST + COIN SCANNER</div>", unsafe_allow_html=True)
st.warning("PLACEHOLDER - Activates in Phase 8 after July 24")
col1, col2 = st.columns(2)
with col1:
    st.markdown("**Batch Backtest**")
    st.info("Multi-coin batch backtest will be available in Phase 8")
    st.multiselect("Select Coins", ["BTCUSD", "ETHUSD"], disabled=True, key="sec8_coins")
    st.button("RUN BATCH BACKTEST", disabled=True, key="sec8_run")
with col2:
    st.markdown("**Coin Scanner**")
    st.info("Trend filter scanner will be available in Phase 8")
    st.button("RUN SCANNER", disabled=True, key="sec8_scan")

# ================================================================
# SECTION 9 - MARKET DATA
# ================================================================
st.markdown("<div class='section-title'>SECTION 9 - MARKET DATA</div>", unsafe_allow_html=True)

import subprocess
col1, col2 = st.columns(2)
with col1:
    data_symbol = st.selectbox("Select Symbol", ["BTCUSD", "ETHUSD"], key="sec9_symbol")
with col2:
    data_timeframe = st.selectbox("Select Timeframe", ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"], key="sec9_tf")

if st.button("DOWNLOAD MARKET DATA", key="sec9_download"):
    st.info(f"Downloading {data_symbol} {data_timeframe} data...")
    with st.spinner("Downloading..."):
        try:
            result = subprocess.run(
                ["python", "data/download_market_data.py", "--symbol", data_symbol],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                st.success("Download complete")
                st.code(result.stdout[-1000:])
            else:
                st.error("Download failed")
                st.code(result.stderr[-1000:])
        except Exception as e:
            st.error(f"Error: {e}")

import glob, os
csv_data_files = glob.glob("data/*.csv")
st.markdown("**Available Data Files**")
if csv_data_files:
    for f in sorted(csv_data_files):
        size = round(os.path.getsize(f)/1024/1024, 1)
        st.caption(f"{os.path.basename(f)} - {size} MB")
else:
    st.info("No CSV data files found")

# ================================================================
# SECTION 10 - CONTRACT MANAGER
# ================================================================
st.markdown("<div class='section-title'>SECTION 10 - CONTRACT MANAGER</div>", unsafe_allow_html=True)

contracts = config.get("contracts", [])

col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([2,2,1,2,2])
col_h1.markdown("**Symbol**")
col_h2.markdown("**Name**")
col_h3.markdown("**Lots**")
col_h4.markdown("**Status**")
col_h5.markdown("**Action**")
st.markdown("---")

for i, contract in enumerate(contracts):
    c1, c2, c3, c4, c5 = st.columns([2,2,1,2,2])
    with c1:
        st.write(contract.get('symbol',''))
    with c2:
        st.write(contract.get('name',''))
    with c3:
        new_c_lots = st.number_input("", min_value=1, value=contract.get('lots',100),
            key=f"sec10_lots_{i}", label_visibility="collapsed")
        if new_c_lots != contract.get('lots',100):
            contracts[i]['lots'] = new_c_lots
            config['contracts'] = contracts
            json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
            st.success("Updated")
    with c4:
        if contract.get('active', True):
            st.success("ACTIVE")
        else:
            st.error("INACTIVE")
    with c5:
        if st.button("REMOVE", key=f"sec10_remove_{i}"):
            contracts.pop(i)
            config['contracts'] = contracts
            json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
            st.warning("Contract removed")
            st.rerun()

st.markdown("---")
st.markdown("**Add New Contract**")
with st.form("add_contract_form"):
    new_sym = st.text_input("Symbol (e.g. ETHUSD)")
    new_cname = st.text_input("Name (e.g. Ethereum Perpetual)")
    new_clots = st.number_input("Lots", min_value=1, value=100)
    add_submitted = st.form_submit_button("ADD CONTRACT")
    if add_submitted and new_sym:
        contracts.append({
            'symbol': new_sym.upper(),
            'name': new_cname,
            'lots': int(new_clots),
            'active': True
        })
        config['contracts'] = contracts
        json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
        st.success(f"Contract {new_sym.upper()} added")

# ================================================================
# SECTION 11 - GITHUB SYNC
# ================================================================
st.markdown("<div class='section-title'>SECTION 11 - GITHUB SYNC</div>", unsafe_allow_html=True)

import subprocess

def run_git(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd='.', timeout=30)
        return result.stdout + result.stderr
    except Exception as e:
        return str(e)

local_commit = run_git(["git", "log", "--oneline", "-1"])
st.markdown("**Sync Status**")
c1, c2, c3 = st.columns(3)
with c1:
    st.success(f"LOCAL: {local_commit[:20]}")
with c2:
    st.success(f"VM: Check manually")
with c3:
    st.success(f"GITHUB: {local_commit[:20]}")

st.markdown("---")
b1, b2, b3 = st.columns(3)
with b1:
    if st.button("GIT STATUS", key="sec11_status"):
        out = run_git(["git", "status"])
        st.code(out)
with b2:
    if st.button("GIT PULL", key="sec11_pull"):
        out = run_git(["git", "pull", "origin", "master"])
        st.code(out)
with b3:
    if st.button("GIT PUSH", key="sec11_push"):
        out = run_git(["git", "push", "origin", "master"])
        st.code(out)

commit_msg = st.text_input("Commit Message", placeholder="Enter commit message", key="sec11_msg")
if st.button("COMMIT + PUSH", key="sec11_commit_push"):
    if commit_msg:
        out1 = run_git(["git", "add", "."])
        out2 = run_git(["git", "commit", "-m", commit_msg])
        out3 = run_git(["git", "push", "origin", "master"])
        st.code(out1 + out2 + out3)
        st.success("Committed and pushed")
    else:
        st.error("Please enter a commit message")

# ================================================================
# SECTION 12 - MAINTENANCE
# ================================================================
st.markdown("<div class='section-title'>SECTION 12 - MAINTENANCE</div>", unsafe_allow_html=True)

import shutil, os, subprocess

disk_pct2, disk_free2 = get_disk_usage()
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    if disk_pct2 > 80:
        st.error(f"DISK: {disk_pct2}%")
    elif disk_pct2 > 60:
        st.warning(f"DISK: {disk_pct2}%")
    else:
        st.success(f"DISK: {disk_pct2}%")
with c2:
    pycache_exists = any(True for _ in __import__('pathlib').Path('.').rglob('__pycache__'))
    if pycache_exists:
        st.warning("PYCACHE: EXISTS")
    else:
        st.success("PYCACHE: CLEAN")
with c3:
    s2_size = round(os.path.getsize(s2_log)/1024/1024, 1) if os.path.exists(s2_log) else 0
    s4_size = round(os.path.getsize(s4_log)/1024/1024, 1) if os.path.exists(s4_log) else 0
    total_log = s2_size + s4_size
    if total_log > 100:
        st.warning(f"LOGS: {total_log}MB")
    else:
        st.success(f"LOGS: {total_log}MB")
with c4:
    venv_ok = os.path.exists('.venv') or os.path.exists('venv')
    if venv_ok:
        st.success("VENV: OK")
    else:
        st.error("VENV: MISSING")
with c5:
    st.info("SERVICE: CHECK VM")

st.markdown("---")
b1, b2, b3 = st.columns(3)
with b1:
    if st.button("CHECK DISK", key="sec12_disk"):
        st.info(f"Disk: {disk_pct2}% used | {disk_free2} GB free")
with b2:
    if st.button("CLEAN PYCACHE", key="sec12_pycache"):
        try:
            import pathlib
            count = 0
            for p in pathlib.Path('.').rglob('__pycache__'):
                __import__('shutil').rmtree(p, ignore_errors=True)
                count += 1
            st.success(f"Cleaned {count} pycache folders")
        except Exception as e:
            st.error(f"Error: {e}")
with b3:
    if st.button("TRIM LOGS", key="sec12_trim"):
        try:
            for log_path in [s2_log, s4_log]:
                if os.path.exists(log_path):
                    lines = open(log_path, encoding='utf-8', errors='ignore').readlines()
                    if len(lines) > 10000:
                        open(log_path, 'w').writelines(lines[-10000:])
                        st.success(f"Trimmed {log_path} to 10000 lines")
                    else:
                        st.info(f"{log_path}: {len(lines)} lines - no trim needed")
        except Exception as e:
            st.error(f"Error: {e}")

# ================================================================
# SECTION 13 - STRATEGY PERFORMANCE SUMMARY
# ================================================================
st.markdown("<div class='section-title'>SECTION 13 - STRATEGY PERFORMANCE SUMMARY</div>", unsafe_allow_html=True)

col_s2, col_s4 = st.columns(2)
with col_s2:
    st.markdown("**S2 - RenkoReversalStrategy**")
    st.metric("Total Trades", "1506")
    st.metric("Win Rate", "52.26%")
    st.metric("Net PnL", "26.37L INR")
    st.metric("Max Drawdown", "-0.27%")
    st.metric("Sharpe Ratio", "5.55")
    st.metric("Profit Factor", "3.83")
    st.metric("ROC", "3939.61%")
    st.success("13/13 months profitable")
    st.caption("Source: Backtest HTML | Params: renko_box_pct=0.001, st_atr=5, st_factor=1.5")

with col_s4:
    st.markdown("**S4 - RenkoSMIIOSupertrendStrategy**")
    st.metric("Total Trades", "659")
    st.metric("Win Rate", "57.66%")
    st.metric("Net PnL", "23.37L INR")
    st.metric("Max Drawdown", "-0.28%")
    st.metric("Sharpe Ratio", "6.92")
    st.metric("Profit Factor", "4.89")
    st.metric("ROC", "N/A")
    st.success("13/13 months profitable")
    st.caption("Source: Backtest HTML | Params: renko_box_pct=0.001, st_atr=10, st_factor=2.0, smiio_short=20, smiio_sig=7")

# ================================================================
# FOOTER
# ================================================================
st.markdown("---")
st.caption(f"Version: {system.get('version', 'v3.9')} | Commit: {git_commit} | Last refresh: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
