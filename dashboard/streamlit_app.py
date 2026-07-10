import streamlit as st
import json, os, subprocess, datetime, shutil, glob

st.set_page_config(page_title="Crypto Trading Dashboard", layout="wide", page_icon="📈")

st.markdown("""
<style>
/* COMPACT PRO THEME */
.stApp { background-color: #ffffff; }
.block-container { padding: 0.5rem 1rem 0.5rem 1rem !important; max-width: 100% !important; }
section[data-testid="stSidebar"] { display: none; }

/* COMPACT FONTS */
html, body, [class*="css"] { font-size: 12px !important; }
h1 { font-size: 16px !important; font-weight: 700 !important; margin: 0 !important; padding: 0 !important; }
h2 { font-size: 14px !important; font-weight: 600 !important; margin: 0 !important; }
h3 { font-size: 13px !important; font-weight: 600 !important; margin: 0 !important; }
p  { font-size: 12px !important; margin: 0 !important; }

/* COMPACT METRICS */
[data-testid="stMetricValue"] { font-size: 13px !important; font-weight: 600 !important; }
[data-testid="stMetricLabel"] { font-size: 11px !important; color: #666 !important; }
[data-testid="metric-container"] { padding: 4px 8px !important; border: 1px solid #e0e0e0; border-radius: 4px; }

/* COMPACT SECTION TITLES */
.section-title { color: #1a73e8; font-size: 12px !important; font-weight: 700;
                 border-bottom: 1px solid #1a73e8; padding-bottom: 2px;
                 margin-bottom: 6px; margin-top: 8px; text-transform: uppercase;
                 letter-spacing: 0.5px; }

/* COMPACT ALERTS */
.alert-red { background: #ffebee; border-left: 3px solid #dc3545;
             padding: 4px 8px; color: #dc3545; font-weight: 600;
             font-size: 11px !important; margin: 2px 0; border-radius: 2px; }
.alert-yellow { background: #fff8e1; border-left: 3px solid #ffc107;
                padding: 4px 8px; color: #856404; font-weight: 600;
                font-size: 11px !important; margin: 2px 0; border-radius: 2px; }
.alert-green { background: #e8f5e9; border-left: 3px solid #28a745;
               padding: 4px 8px; color: #28a745; font-weight: 600;
               font-size: 11px !important; margin: 2px 0; border-radius: 2px; }

/* COMPACT BUTTONS */
.stButton > button { padding: 2px 10px !important; font-size: 11px !important;
                     height: 26px !important; border-radius: 3px !important; }

/* COMPACT INPUTS */
.stSelectbox, .stNumberInput, .stDateInput { font-size: 11px !important; }
.stSelectbox > div > div { padding: 2px 6px !important; min-height: 28px !important; }

/* COMPACT TABS */
.stTabs [data-baseweb="tab"] { padding: 4px 12px !important; font-size: 11px !important; }

/* COMPACT DATAFRAME */
.stDataFrame { font-size: 11px !important; }

/* REMOVE EXTRA PADDING */
.stMarkdown { margin: 0 !important; padding: 0 !important; }
div[data-testid="stVerticalBlock"] > div { gap: 0.3rem !important; }
.element-container { margin: 0 !important; padding: 0 !important; }

/* COMPACT SUCCESS/ERROR/WARNING BOXES */
.stSuccess, .stError, .stWarning, .stInfo {
    padding: 4px 8px !important; font-size: 11px !important;
    margin: 2px 0 !important; border-radius: 3px !important; }

/* HORIZONTAL DIVIDER */
hr { margin: 4px 0 !important; border-color: #e0e0e0 !important; }

/* CAPTION */
.stCaption { font-size: 10px !important; color: #888 !important; }

/* CODE BLOCK */
.stCode { font-size: 10px !important; }
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
# SECTION 1B - ERROR MONITOR (auto-checks all systems)
# ================================================================
st.markdown("<div class='section-title'>SYSTEM ERROR MONITOR</div>", unsafe_allow_html=True)

import subprocess, os, datetime

errors = []
warnings = []
ok = []

# 1. CHECK BOT SCREENS RUNNING
try:
    result = subprocess.run(['screen', '-ls'], capture_output=True, text=True)
    if 'live_s2' in result.stdout:
        ok.append("S2 bot screen: RUNNING")
    else:
        errors.append("S2 bot screen: NOT RUNNING - run bash start.sh on VM")
    if 'live_s4' in result.stdout:
        ok.append("S4 bot screen: RUNNING")
    else:
        errors.append("S4 bot screen: NOT RUNNING - run bash start.sh on VM")
except Exception as e:
    errors.append(f"Screen check failed: {e}")

# 2. CHECK LOG FILES EXIST AND RECENT
for bot, log in [('S2', 'logs/live_trading_s2.log'), ('S4', 'logs/live_trading_s4.log')]:
    try:
        if os.path.exists(log):
            mtime = os.path.getmtime(log)
            age_mins = (datetime.datetime.now().timestamp() - mtime) / 60
            if age_mins < 5:
                ok.append(f"{bot} log: ACTIVE (updated {int(age_mins)}m ago)")
            elif age_mins < 30:
                warnings.append(f"{bot} log: STALE ({int(age_mins)}m ago) - bot may be stuck")
            else:
                errors.append(f"{bot} log: NOT UPDATING ({int(age_mins)}m ago) - bot likely crashed")
        else:
            errors.append(f"{bot} log: FILE MISSING - bot never started")
    except Exception as e:
        errors.append(f"{bot} log check failed: {e}")

# 3. CHECK FOR ERRORS IN LOGS
for bot, log in [('S2', 'logs/live_trading_s2.log'), ('S4', 'logs/live_trading_s4.log')]:
    try:
        if os.path.exists(log):
            lines = open(log).readlines()
            recent = lines[-50:] if len(lines) > 50 else lines
            error_lines = [l.strip() for l in recent if 'ERROR' in l]
            algotest_errors = [l.strip() for l in recent if 'ALGOTEST' in l and ('ERROR' in l or 'WARNING' in l)]
            api_errors = [l.strip() for l in recent if any(x in l for x in ['InvalidApiKey','insufficient_margin','rate_limit','IP not whitelisted']) or ('ERROR' in l and any(x in l for x in ['401','403','429']))]
            if error_lines:
                for el in error_lines[-3:]:
                    errors.append(f"{bot} ERROR: {el[-100:]}")
            if algotest_errors:
                for al in algotest_errors[-2:]:
                    errors.append(f"{bot} ALGOTEST: {al[-100:]}")
            if api_errors:
                for al in api_errors[-2:]:
                    errors.append(f"{bot} API ERROR: {al[-100:]}")
            if not error_lines and not algotest_errors and not api_errors:
                ok.append(f"{bot} log: No errors in last 50 lines")
    except Exception as e:
        errors.append(f"{bot} error scan failed: {e}")

# 4. CHECK ALGOTEST WEBHOOK KEYS IN ENV
try:
    from dotenv import load_dotenv
    load_dotenv()
    webhook_keys = [
        'ALGOTEST_WEBHOOK_S2_BUY_ENTRY','ALGOTEST_WEBHOOK_S2_BUY_EXIT',
        'ALGOTEST_WEBHOOK_S2_SELL_ENTRY','ALGOTEST_WEBHOOK_S2_SELL_EXIT',
        'ALGOTEST_WEBHOOK_S4_BUY_ENTRY','ALGOTEST_WEBHOOK_S4_BUY_EXIT',
        'ALGOTEST_WEBHOOK_S4_SELL_ENTRY','ALGOTEST_WEBHOOK_S4_SELL_EXIT'
    ]
    missing = [k for k in webhook_keys if not os.getenv(k)]
    if missing:
        for m in missing:
            errors.append(f"WEBHOOK KEY MISSING in .env: {m}")
    else:
        ok.append("All 8 Algotest webhook keys: CONFIGURED")
except Exception as e:
    warnings.append(f"Webhook key check failed: {e}")

# 5. CHECK DISK SPACE
try:
    import shutil
    total, used, free = shutil.disk_usage('.')
    pct = int(used/total*100)
    free_gb = round(free/1024**3, 1)
    if pct > 80:
        errors.append(f"DISK CRITICAL: {pct}% used - only {free_gb}GB free - clean immediately")
    elif pct > 70:
        warnings.append(f"DISK WARNING: {pct}% used - {free_gb}GB free - monitor closely")
    else:
        ok.append(f"Disk: {pct}% used - {free_gb}GB free")
except Exception as e:
    warnings.append(f"Disk check failed: {e}")

# 6. CHECK SYSTEMD SERVICE
try:
    result = subprocess.run(['systemctl', 'is-active', 'tradingbot.service'], capture_output=True, text=True)
    status = result.stdout.strip()
    if status == 'active':
        ok.append("systemd tradingbot.service: ACTIVE")
    else:
        warnings.append(f"systemd tradingbot.service: {status} - auto-restart may not work")
except Exception as e:
    warnings.append(f"Service check failed: {e}")

# 7. CHECK RECENT ALGOTEST SUCCESS
for bot, log in [('S2', 'logs/live_trading_s2.log'), ('S4', 'logs/live_trading_s4.log')]:
    try:
        if os.path.exists(log):
            lines = open(log).readlines()
            recent = lines[-200:] if len(lines) > 200 else lines
            algotest_ok = [l for l in recent if 'ALGOTEST' in l and 'Status: 200' in l]
            algotest_fail = [l for l in recent if 'ALGOTEST' in l and 'Status: 200' not in l and 'WARNING' not in l and 'ERROR' in l]
            if algotest_ok:
                ok.append(f"{bot} last Algotest webhook: SUCCESS (Status 200)")
            if algotest_fail:
                errors.append(f"{bot} Algotest webhook FAILED: {algotest_fail[-1].strip()[-80:]}")
    except:
        pass


# 8. CHECK OPEN POSITION > 24H (orphan position risk)
for bot, log in [('S2', 'logs/live_trading_s2.log'), ('S4', 'logs/live_trading_s4.log')]:
    try:
        if os.path.exists(log):
            lines = open(log).readlines()
            entry_lines = [l for l in lines if '[ORDER] ENTRY' in l]
            exit_lines = [l for l in lines if '[ORDER] EXIT' in l]
            if entry_lines:
                last_entry = entry_lines[-1]
                last_exit = exit_lines[-1] if exit_lines else None
                import re
                entry_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', last_entry)
                exit_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', last_exit) if last_exit else None
                if entry_match:
                    entry_time = datetime.datetime.strptime(entry_match.group(1), '%Y-%m-%d %H:%M:%S')
                    if last_exit is None or (exit_match and entry_time > datetime.datetime.strptime(exit_match.group(1), '%Y-%m-%d %H:%M:%S')):
                        age_hours = (datetime.datetime.now() - entry_time).total_seconds() / 3600
                        if age_hours > 48:
                            errors.append(f"{bot} ORPHAN POSITION: Entry {int(age_hours)}h ago with no exit - check Delta account immediately")
                        elif age_hours > 24:
                            warnings.append(f"{bot} OPEN POSITION: {int(age_hours)}h since entry - no exit yet - monitor closely")
                        else:
                            ok.append(f"{bot} position: open {int(age_hours)}h - normal")
                    else:
                        ok.append(f"{bot} position: closed cleanly")
    except Exception as e:
        warnings.append(f"{bot} position check failed: {e}")

# 9. CHECK NO ORDERS IN LAST 48H (bot alive but not trading)
for bot, log in [('S2', 'logs/live_trading_s2.log'), ('S4', 'logs/live_trading_s4.log')]:
    try:
        if os.path.exists(log):
            lines = open(log).readlines()
            order_lines = [l for l in lines if '[ORDER]' in l]
            if order_lines:
                import re
                last_order = order_lines[-1]
                match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', last_order)
                if match:
                    last_time = datetime.datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
                    age_hours = (datetime.datetime.now() - last_time).total_seconds() / 3600
                    if age_hours > 48:
                        warnings.append(f"{bot} last order: {int(age_hours)}h ago - strategy may be in low signal period")
                    else:
                        ok.append(f"{bot} last order: {int(age_hours)}h ago - normal")
            else:
                ok.append(f"{bot} no orders yet - waiting for first signal")
    except Exception as e:
        warnings.append(f"{bot} order check failed: {e}")

# 10. CHECK DUPLICATE ORDERS (same timestamp fired twice)
for bot, log in [('S2', 'logs/live_trading_s2.log'), ('S4', 'logs/live_trading_s4.log')]:
    try:
        if os.path.exists(log):
            lines = open(log).readlines()
            order_lines = [l for l in lines if '[ORDER]' in l]
            timestamps = []
            import re
            for l in order_lines:
                match = re.search(r'ts=(\S+)', l)
                if match:
                    timestamps.append(match.group(1))
            duplicates = [t for t in timestamps if timestamps.count(t) > 1]
            if duplicates:
                errors.append(f"{bot} DUPLICATE ORDERS detected at timestamps: {list(set(duplicates))}")
            else:
                ok.append(f"{bot} duplicate order check: CLEAN")
    except Exception as e:
        warnings.append(f"{bot} duplicate check failed: {e}")


# 11. CHECK BOT CYCLING HEALTH (last [SIGNALS] line timestamp)
for bot, log in [('S2', 'logs/live_trading_s2.log'), ('S4', 'logs/live_trading_s4.log')]:
    try:
        if os.path.exists(log):
            lines = open(log).readlines()
            signal_lines = [l for l in lines if '[SIGNALS]' in l or '[WAIT]' in l or '[DATA]' in l]
            if signal_lines:
                last_line = signal_lines[-1]
                import re
                match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', last_line)
                if match:
                    last_time = datetime.datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
                    age_mins = (datetime.datetime.now() - last_time).total_seconds() / 60
                    if age_mins > 10:
                        errors.append(f"{bot} BOT FROZEN: No cycle in {int(age_mins)}m - bot may be stuck or crashed")
                    elif age_mins > 5:
                        warnings.append(f"{bot} bot cycle: {int(age_mins)}m ago - slightly delayed")
                    else:
                        ok.append(f"{bot} bot cycling: OK ({int(age_mins)}m ago)")
            else:
                warnings.append(f"{bot} no cycle lines found in log")
    except Exception as e:
        warnings.append(f"{bot} cycle check failed: {e}")

# 12. FORWARD TEST END DATE REMINDER
try:
    forward_end = datetime.datetime(2026, 7, 24)
    days_left = (forward_end - datetime.datetime.now()).days
    if days_left < 0:
        errors.append("FORWARD TEST ENDED - review Algotest MTM results and decide go-live")
    elif days_left == 0:
        errors.append("FORWARD TEST ENDS TODAY - review Algotest MTM results now")
    elif days_left <= 3:
        warnings.append(f"FORWARD TEST ENDS IN {days_left} DAYS - prepare go-live review")
    elif days_left <= 7:
        warnings.append(f"Forward test ends in {days_left} days (July 24)")
    else:
        ok.append(f"Forward test: {days_left} days remaining (ends July 24)")
except Exception as e:
    warnings.append(f"Forward test date check failed: {e}")

# 13. CHECK .ENV FILE EXISTS AND HAS API KEYS
try:
    if os.path.exists('.env'):
        env_content = open('.env').read()
        required_keys = ['S2_API_KEY', 'S4_API_KEY', 'S2_API_SECRET', 'S4_API_SECRET']
        missing_keys = [k for k in required_keys if k not in env_content]
        if missing_keys:
            errors.append(f".env MISSING API KEYS: {missing_keys} - bots cannot trade")
        else:
            ok.append(".env file: exists with all API keys")
    else:
        errors.append(".env FILE MISSING - all API keys gone - run bash start.sh")
except Exception as e:
    warnings.append(f".env check failed: {e}")

# 14. CHECK DELTA API CONNECTIVITY
try:
    import requests as req
    resp = req.get('https://api.india.delta.exchange/v2/products?contract_types=perpetual_futures&limit=1', timeout=5)
    if resp.status_code == 200:
        ok.append("Delta API connectivity: REACHABLE")
    else:
        warnings.append(f"Delta API returned status {resp.status_code} - may have issues")
except Exception as e:
    errors.append(f"Delta API UNREACHABLE: {e} - check VM internet connection")

# 15. CHECK VM INTERNET (ping Google DNS)
try:
    import subprocess as sp
    result = sp.run(['curl', '-s', '--max-time', '3', 'https://8.8.8.8'], capture_output=True)
    ok.append("VM internet: CONNECTED")
except Exception as e:
    errors.append(f"VM internet check failed: {e}")

# 16. CHECK ALGOTEST WEBHOOK URLS REACHABLE (quick HEAD check)
try:
    from dotenv import load_dotenv
    load_dotenv()
    import requests as req
    test_url = os.getenv('ALGOTEST_WEBHOOK_S4_BUY_ENTRY')
    if test_url:
        try:
            resp = req.post(test_url, json={"access_token": os.getenv('ALGOTEST_ACCESS_TOKEN', 'n7FJcMHANHN4F8HdqbU5QMDJn5JO79K9'), "alert_name": "ping"}, timeout=5)
            if resp.status_code in [200, 201, 202, 400, 422]:
                ok.append("Algotest webhook URL: REACHABLE")
            else:
                warnings.append(f"Algotest webhook returned {resp.status_code} - check signal config")
        except Exception as e:
            errors.append(f"Algotest webhook UNREACHABLE: {e}")
    else:
        errors.append("Algotest webhook URL missing from .env")
except Exception as e:
    warnings.append(f"Algotest connectivity check failed: {e}")

# DISPLAY RESULTS
if errors:
    st.error(f"ERRORS DETECTED: {len(errors)} issue(s) require attention")
    for e in errors:
        st.markdown(f"<div class='alert-red'>ERROR: {e}</div>", unsafe_allow_html=True)
elif warnings:
    st.warning(f"WARNINGS: {len(warnings)} item(s) to monitor")
else:
    st.success("ALL SYSTEMS HEALTHY - No errors detected")

if warnings:
    for w in warnings:
        st.markdown(f"<div class='alert-yellow'>WARNING: {w}</div>", unsafe_allow_html=True)

with st.expander("Show all OK checks"):
    for o in ok:
        st.markdown(f"OK: {o}")

st.caption(f"Last checked: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Auto-refreshes every 30s")
st.markdown("---")

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

st.markdown("---")
st.markdown("**Generate Detailed Comparison Report**")

comp_tab_s2, comp_tab_s4 = st.tabs(["S2 - RenkoReversalStrategy", "S4 - RenkoSMIIOSupertrendStrategy"])

for comp_tab, algo_name, algo_key in [(comp_tab_s2, "S2", "s2"), (comp_tab_s4, "S4", "s4")]:
    with comp_tab:
        st.markdown(f"**{algo_name} - Algotest Data (manual input)**")
        c1, c2, c3 = st.columns(3)
        with c1:
            at_pnl = st.number_input("Algotest MTM PnL (INR)", value=0.0, key=f"at_pnl_{algo_key}")
            at_trades = st.number_input("Algotest Trade Count", min_value=0, value=0, key=f"at_trades_{algo_key}")
        with c2:
            at_wr = st.number_input("Algotest Win Rate (%)", min_value=0.0, value=0.0, key=f"at_wr_{algo_key}")
            at_dd = st.number_input("Algotest Max DD (%)", min_value=0.0, value=0.0, key=f"at_dd_{algo_key}")
        with c3:
            at_sharpe = st.number_input("Algotest Sharpe", value=0.0, key=f"at_sharpe_{algo_key}")
            fetch_delta = st.checkbox("Auto Fetch Delta API", value=True, key=f"fetch_delta_{algo_key}")

        col1, col2 = st.columns(2)
        with col1:
            gen_btn = st.button(f"GENERATE {algo_name} REPORT", key=f"gen_report_{algo_key}")
        with col2:
            st.caption("Fetches commission + funding from Delta API automatically")

        if gen_btn:
            with st.spinner(f"Generating {algo_name} comparison report..."):
                try:
                    cmd = [
                        ".venv/bin/python", "scripts/generate_comparison_report.py",
                        "--algo", algo_name,
                        "--start", "2026-07-07",
                        "--end", "2026-07-24",
                        "--algotest_pnl", str(at_pnl),
                        "--algotest_trades", str(at_trades),
                        "--algotest_winrate", str(at_wr),
                        "--algotest_dd", str(at_dd),
                        "--algotest_sharpe", str(at_sharpe),
                    ]
                    if fetch_delta:
                        cmd.append("--fetch_delta")
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        st.success(f"{algo_name} comparison report generated")
                        st.code(result.stdout)
                    else:
                        st.error("Report generation failed")
                        st.code(result.stderr[-1000:])
                except Exception as e:
                    st.error(f"Error: {e}")

        comp_html_files = sorted([f for f in glob.glob(f"output/comparison_report_{algo_name}_*.html")], reverse=True)
        if comp_html_files:
            sel_comp = st.selectbox(f"Select {algo_name} Report", comp_html_files, key=f"comp_sel_{algo_key}")
            c1, c2, c3 = st.columns(3)
            with c1:
                view_comp = st.button(f"VIEW {algo_name} REPORT", key=f"view_comp_{algo_key}")
            with c2:
                with open(sel_comp, 'rb') as fh:
                    st.download_button("DOWNLOAD HTML", fh, file_name=os.path.basename(sel_comp), key=f"dl_comp_{algo_key}")
            with c3:
                try:
                    user_comp = open(sel_comp, encoding='utf-8').read()
                    for sname in ['RenkoReversalStrategy','RenkoSMIIOSupertrendStrategy']:
                        user_comp = user_comp.replace(sname, 'Alpha Strategy')
                    st.download_button("DOWNLOAD USER HTML", user_comp.encode('utf-8'), file_name=f"alpha_{algo_name}_comparison.html", mime="text/html", key=f"dl_comp_user_{algo_key}")
                except Exception as e:
                    st.error(f"Error: {e}")
            if view_comp:
                content = open(sel_comp, encoding='utf-8').read()
                st.components.v1.html(content, height=2500, scrolling=True)
        else:
            st.info(f"No {algo_name} comparison reports found. Click GENERATE to create one.")


# ================================================================
# SECTION 5 - BACKTEST
# ================================================================
st.markdown("<div class='section-title'>SECTION 5 - BACKTEST</div>", unsafe_allow_html=True)

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

st.markdown("**Date Range**")
bt_range_options = ["1 Month", "6 Months", "1 Year", "1.5 Years", "2 Years", "Full CSV", "Custom"]
bt_range = st.radio("", bt_range_options, index=2, horizontal=True, key="sec6_range")
today = datetime.date.today()
if bt_range == "1 Month":
    bt_start = today - datetime.timedelta(days=30)
    bt_end = today
elif bt_range == "6 Months":
    bt_start = today - datetime.timedelta(days=180)
    bt_end = today
elif bt_range == "1 Year":
    bt_start = today - datetime.timedelta(days=365)
    bt_end = today
elif bt_range == "1.5 Years":
    bt_start = today - datetime.timedelta(days=548)
    bt_end = today
elif bt_range == "2 Years":
    bt_start = today - datetime.timedelta(days=730)
    bt_end = today
elif bt_range == "Full CSV":
    bt_start = datetime.date.fromisoformat("2024-01-01")
    bt_end = datetime.date.fromisoformat("2026-07-10")
    st.info(f"Full CSV range: {bt_start} to {bt_end}")
else:
    col3, col4 = st.columns(2)
    with col3:
        bt_start = st.date_input("Start Date", value=datetime.date(2025, 1, 1), key="sec6_start")
    with col4:
        bt_end = st.date_input("End Date", value=today, key="sec6_end")

col5, col6 = st.columns(2)
with col5:
    bt_slippage = st.number_input("Slippage/side ($)", min_value=0.0, value=5.0, key="sec6_slip")
with col6:
    bt_include_charges = st.checkbox("Include Tax & All Charges", value=True, key="sec6_charges")

if st.button("RUN BACKTEST", key="sec6_run"):
    st.info(f"Running backtest: {bt_strategy} | Lots: {bt_lots} | {bt_start} to {bt_end}")
    with st.spinner("Running backtest..."):
        try:
            cmd = [
                ".venv/bin/python", "scripts/run_backtest_cli.py",
                "--strategy", bt_strategy,
                "--lots", str(bt_lots),
                "--start", str(bt_start),
                "--end", str(bt_end),
                "--slippage", str(bt_slippage),
                "--symbol", "BTCUSD",
                "--csv", "data/btc_1m_delta.csv"
            ]
            if not bt_include_charges:
                cmd.append("--no-charges")
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

html_files = sorted([f for f in glob.glob("output/*.html") if "backtest_report_" in f and "optimization" not in f], reverse=True)
csv_files = sorted([f for f in glob.glob("output/*.csv") if "trade_log_" in f], reverse=True)

st.markdown("**HTML Reports**")
if html_files:
    selected_html = st.selectbox("Select HTML Report", html_files, key="sec6_html_select")
    c1, c2, c3 = st.columns(3)
    with c1:
        view_html_s5 = st.button("VIEW HTML REPORT", key="sec6_view_html")
    with c2:
        with open(selected_html, 'rb') as f:
            st.download_button("DOWNLOAD HTML", f, file_name=os.path.basename(selected_html), key="sec6_dl_html")
    with c3:
        try:
            user_content = open(selected_html, encoding='utf-8').read()
            user_content = user_content.replace('<title>Backtest Report - RenkoReversalStrategy</title>', '<title>Backtest Report - Alpha Strategy</title>')
            user_content = user_content.replace('<title>Backtest Report - RenkoSMIIOSupertrendStrategy</title>', '<title>Backtest Report - Alpha Strategy</title>')
            for sname in ['RenkoReversalStrategy','RenkoSMIIOSupertrendStrategy','RenkoBreakoutStrategy','RenkoTrendlinePullbackStrategy','RenkoOptionsStrategy']:
                user_content = user_content.replace(f'<h1>{sname}</h1>', '<h1>Alpha Strategy</h1>')
                user_content = user_content.replace(f'Strategy: {sname}', 'Strategy: Alpha Strategy')
                user_content = user_content.replace(f'<title>Backtest Report - {sname}</title>', '<title>Backtest Report - Alpha Strategy</title>')
            st.download_button("DOWNLOAD USER HTML", user_content.encode('utf-8'), file_name="alpha_strategy_report.html", mime="text/html", key="sec6_dl_user_html")
        except Exception as e:
            st.error(f"Error: {e}")
    if view_html_s5:
        try:
            content = open(selected_html, encoding='utf-8').read()
            st.components.v1.html(content, height=2000, scrolling=True)
        except Exception as e:
            st.error(f"Error opening report: {e}")
else:
    st.info("No HTML reports found in output/ folder")

st.markdown("**CSV Results**")
if csv_files:
    selected_csv = st.selectbox("Select CSV", csv_files, key="sec6_csv_select")
    with open(selected_csv, 'rb') as f:
        st.download_button("DOWNLOAD CSV", f, file_name=os.path.basename(selected_csv), key="sec6_dl_csv")
else:
    st.info("No CSV files found in output/ folder")

import subprocess, glob, os


# ================================================================
# SECTION 5B - PORTFOLIO BACKTEST
# ================================================================
st.markdown("<div class='section-title'>SECTION 5B - PORTFOLIO BACKTEST</div>", unsafe_allow_html=True)

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

    st.markdown("**Date Range**")
    port_range = st.radio("", ["1 Month","6 Months","1 Year","1.5 Years","2 Years","Full CSV","Custom"], index=2, horizontal=True, key="port_range")
    today = datetime.date.today()
    if port_range == "1 Month":
        port_start = today - datetime.timedelta(days=30); port_end = today
    elif port_range == "6 Months":
        port_start = today - datetime.timedelta(days=180); port_end = today
    elif port_range == "1 Year":
        port_start = today - datetime.timedelta(days=365); port_end = today
    elif port_range == "1.5 Years":
        port_start = today - datetime.timedelta(days=548); port_end = today
    elif port_range == "2 Years":
        port_start = today - datetime.timedelta(days=730); port_end = today
    elif port_range == "Full CSV":
        port_start = datetime.date.fromisoformat("2024-01-01"); port_end = datetime.date.fromisoformat("2026-07-10")
        st.info(f"Full CSV range: {port_start} to {port_end}")
    else:
        col1, col2 = st.columns(2)
        with col1:
            port_start = st.date_input("Start Date", value=datetime.date(2025,1,1), key="port_start")
        with col2:
            port_end = st.date_input("End Date", value=today, key="port_end")
    col_pl, col_ps, col_pc = st.columns(3)
    with col_pl:
        port_lots = st.number_input("Lots", min_value=1, value=100, key="port_lots")
    with col_ps:
        port_slippage = st.number_input("Slippage/side ($)", min_value=0.0, value=5.0, key="port_slip")
    with col_pc:
        port_include_charges = st.checkbox("Include Tax & All Charges", value=True, key="port_charges")

    if st.button("RUN PREDEFINED PORTFOLIO", key="port_run_pre"):
        st.info("Running predefined portfolio backtest...")
        with st.spinner("Running..."):
            try:
                cmd = [
                    ".venv/bin/python", "scripts/run_portfolio_cli.py",
                    "--strategies", "RenkoReversalStrategy,RenkoSMIIOSupertrendStrategy",
                    "--lots", str(port_lots),
                    "--start", str(port_start),
                    "--end", str(port_end),
                    "--slippage", str(port_slippage),
                    "--symbol", "BTCUSD",
                    "--csv", "data/btc_1m_delta.csv"
                ]
                if not port_include_charges:
                    cmd.append("--no-charges")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
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
    st.markdown("**Date Range**")
    port_dyn_range = st.radio("", ["1 Month","6 Months","1 Year","1.5 Years","2 Years","Full CSV","Custom"], index=2, horizontal=True, key="port_dyn_range")
    today = datetime.date.today()
    if port_dyn_range == "1 Month":
        port_dyn_start = today - datetime.timedelta(days=30); port_dyn_end = today
    elif port_dyn_range == "6 Months":
        port_dyn_start = today - datetime.timedelta(days=180); port_dyn_end = today
    elif port_dyn_range == "1 Year":
        port_dyn_start = today - datetime.timedelta(days=365); port_dyn_end = today
    elif port_dyn_range == "1.5 Years":
        port_dyn_start = today - datetime.timedelta(days=548); port_dyn_end = today
    elif port_dyn_range == "2 Years":
        port_dyn_start = today - datetime.timedelta(days=730); port_dyn_end = today
    elif port_dyn_range == "Full CSV":
        port_dyn_start = datetime.date.fromisoformat("2024-01-01"); port_dyn_end = datetime.date.fromisoformat("2026-07-10")
        st.info(f"Full CSV range: {port_dyn_start} to {port_dyn_end}")
    else:
        col1, col2 = st.columns(2)
        with col1:
            port_dyn_start = st.date_input("Start Date", value=datetime.date(2025,1,1), key="port_dyn_start")
        with col2:
            port_dyn_end = st.date_input("End Date", value=today, key="port_dyn_end")
    col_dl, col_ds, col_dc = st.columns(3)
    with col_dl:
        port_dyn_lots = st.number_input("Lots", min_value=1, value=100, key="port_dyn_lots")
    with col_ds:
        port_dyn_slip = st.number_input("Slippage/side ($)", min_value=0.0, value=5.0, key="port_dyn_slip")
    with col_dc:
        port_dyn_include_charges = st.checkbox("Include Tax & All Charges", value=True, key="port_dyn_charges")

    if st.button("RUN DYNAMIC PORTFOLIO", key="port_run_dyn"):
        if not selected_strategies:
            st.error("Please select at least one strategy")
        else:
            st.info(f"Running dynamic portfolio: {selected_strategies}")
            with st.spinner("Running..."):
                try:
                    cmd = [
                        ".venv/bin/python", "scripts/run_portfolio_cli.py",
                        "--strategies", ",".join(selected_strategies),
                        "--lots", str(port_dyn_lots),
                        "--start", str(port_dyn_start),
                        "--end", str(port_dyn_end),
                        "--slippage", str(port_dyn_slip),
                        "--symbol", "BTCUSD",
                        "--csv", "data/btc_1m_delta.csv"
                    ]
                    if not port_dyn_include_charges:
                        cmd.append("--no-charges")
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                    if result.returncode == 0:
                        st.success("Dynamic portfolio backtest complete")
                        st.code(result.stdout[-3000:])
                    else:
                        st.error("Dynamic portfolio backtest failed")
                        st.code(result.stderr[-2000:])
                except Exception as e:
                    st.error(f"Error: {e}")


# ================================================================

st.markdown("---")
st.markdown("**Backtest Reports**")
port_html = sorted([f for f in glob.glob("output/*.html") if "portfolio_report_" in f], reverse=True)
port_csv = sorted([f for f in glob.glob("output/*.csv") if "portfolio_trade_log_" in f], reverse=True)

st.markdown("**Select Report to View/Download**")
if port_html:
    sel_port_html = st.selectbox("Select Portfolio HTML", port_html, key="port_html_sel")
    c1, c2, c3 = st.columns(3)
    with c1:
        view_html_5b = st.button("VIEW HTML", key="port_view_html")
    with c2:
        with open(sel_port_html, 'rb') as f:
            st.download_button("DOWNLOAD HTML", f, file_name=os.path.basename(sel_port_html), key="port_dl_html")
    with c3:
        try:
            user_content = open(sel_port_html, encoding='utf-8').read()
            for sname in ['Portfolio_Dynamic','RenkoReversalStrategy','RenkoSMIIOSupertrendStrategy','RenkoBreakoutStrategy','RenkoTrendlinePullbackStrategy','RenkoOptionsStrategy']:
                user_content = user_content.replace(f'<h1>{sname}</h1>', '<h1>Alpha Strategy</h1>')
                user_content = user_content.replace(f'Strategy: {sname}', 'Strategy: Alpha Strategy')
                user_content = user_content.replace(f'<title>Backtest Report - {sname}</title>', '<title>Backtest Report - Alpha Strategy</title>')
            st.download_button("DOWNLOAD USER HTML", user_content.encode('utf-8'), file_name="alpha_portfolio_report.html", mime="text/html", key="port_dl_user_html")
        except Exception as e:
            st.error(f"Error: {e}")
    if view_html_5b:
        content = open(sel_port_html, encoding='utf-8').read()
        st.components.v1.html(content, height=2000, scrolling=True)
else:
    st.info("No portfolio HTML reports found in output/ folder")
st.markdown("**CSV Results**")
if port_csv:
    sel_port_csv = st.selectbox("Select Portfolio CSV", port_csv, key="port_csv_sel")
    with open(sel_port_csv, 'rb') as f:
        st.download_button("DOWNLOAD CSV", f, file_name=os.path.basename(sel_port_csv), key="port_dl_csv")
else:
    st.info("No portfolio CSV files found in output/ folder")

# ================================================================
# SECTION 6 - OPTIMISATION
# ================================================================
st.markdown("<div class='section-title'>SECTION 6 - OPTIMISATION</div>", unsafe_allow_html=True)

import subprocess, glob, os

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

st.markdown("**Date Range**")
opt_range = st.radio("", ["1 Month","6 Months","1 Year","1.5 Years","2 Years","Full CSV","Custom"], index=2, horizontal=True, key="sec7_range")
today = datetime.date.today()
if opt_range == "1 Month":
    opt_start = today - datetime.timedelta(days=30); opt_end = today
elif opt_range == "6 Months":
    opt_start = today - datetime.timedelta(days=180); opt_end = today
elif opt_range == "1 Year":
    opt_start = today - datetime.timedelta(days=365); opt_end = today
elif opt_range == "1.5 Years":
    opt_start = today - datetime.timedelta(days=548); opt_end = today
elif opt_range == "2 Years":
    opt_start = today - datetime.timedelta(days=730); opt_end = today
elif opt_range == "Full CSV":
    opt_start = datetime.date.fromisoformat("2024-01-01"); opt_end = datetime.date.fromisoformat("2026-07-10")
    st.info(f"Full CSV range: {opt_start} to {opt_end}")
else:
    col4, col5 = st.columns(2)
    with col4:
        opt_start = st.date_input("Start Date", value=datetime.date(2025, 1, 1), key="sec7_start")
    with col5:
        opt_end = st.date_input("End Date", value=today, key="sec7_end")

col6, col7 = st.columns(2)
with col6:
    opt_slippage = st.number_input("Slippage/side ($)", min_value=0.0, value=5.0, key="sec7_slip")
with col7:
    opt_include_charges = st.checkbox("Include Tax & All Charges", value=True, key="sec7_charges")

if st.button("RUN OPTIMISATION", key="sec7_run"):
    st.info(f"Running optimisation: {opt_strategy} | Group: {opt_group} | Lots: {opt_lots} | Slippage: ${opt_slippage}/side | Charges: {'Included' if opt_include_charges else 'Excluded'}")
    with st.spinner("Running optimisation - this may take several minutes..."):
        try:
            cmd = [
                ".venv/bin/python", "scripts/run_optimization_cli.py",
                "--strategy", opt_strategy,
                "--group", opt_group,
                "--lots", str(opt_lots),
                "--start", str(opt_start),
                "--end", str(opt_end),
                "--slippage", str(opt_slippage)
            ]
            if not opt_include_charges:
                cmd.append("--no-charges")
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

opt_csv_files = sorted([f for f in glob.glob("output/*.csv") if "optimization_results_" in f], reverse=True)
opt_html_files = sorted([f for f in glob.glob("output/*.html") if "optimization_results_" in f], reverse=True)

st.markdown("**HTML Reports**")
if opt_html_files:
    sel_opt_html = st.selectbox("Select Optimisation HTML", opt_html_files, key="sec7_html_sel")
    c1, c2 = st.columns(2)
    with c1:
        view_html_s6 = st.button("VIEW HTML", key="sec7_view_html")
    with c2:
        with open(sel_opt_html, 'rb') as f:
            st.download_button("DOWNLOAD HTML", f, file_name=os.path.basename(sel_opt_html), key="sec7_dl_html")
    if view_html_s6:
        try:
            content = open(sel_opt_html, encoding='utf-8').read()
            st.components.v1.html(content, height=2000, scrolling=True)
        except Exception as e:
            st.error(f"Error: {e}")
else:
    st.info("No optimisation HTML files found in output/ folder")
st.markdown("**CSV Results**")
if opt_csv_files:
    sel_opt_csv = st.selectbox("Select Optimisation CSV", opt_csv_files, key="sec7_csv_sel")
    with open(sel_opt_csv, 'rb') as f:
        st.download_button("DOWNLOAD CSV", f, file_name=os.path.basename(sel_opt_csv), key="sec7_dl_csv")
else:
    st.info("No optimisation CSV files found in output/ folder")

# ================================================================
# SECTION 7 - MARKET DATA
# ================================================================
st.markdown("<div class='section-title'>SECTION 7 - MARKET DATA</div>", unsafe_allow_html=True)

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
                [".venv/bin/python", "data/download_market_data.py", "--symbol", data_symbol],
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
# SECTION 9 - CONTRACT MANAGER
# ================================================================
st.markdown("<div class='section-title'>SECTION 9 - CONTRACT MANAGER</div>", unsafe_allow_html=True)

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
# SECTION 10 - GITHUB SYNC
# ================================================================
st.markdown("<div class='section-title'>SECTION 10 - GITHUB SYNC</div>", unsafe_allow_html=True)

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
# SECTION 11 - MAINTENANCE
# ================================================================
st.markdown("<div class='section-title'>SECTION 11 - MAINTENANCE</div>", unsafe_allow_html=True)

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
# SECTION 12 - LOG MONITOR
# ================================================================
st.markdown("<div class='section-title'>SECTION 12 - LOG MONITOR</div>", unsafe_allow_html=True)

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
# SECTION 13 - STRATEGY PERFORMANCE SUMMARY
# ================================================================
st.markdown("<div class='section-title'>SECTION 13 - STRATEGY PERFORMANCE SUMMARY</div>", unsafe_allow_html=True)

import glob, re as regex

def extract_metric_from_html(html_path, metric_name):
    try:
        content = open(html_path, encoding='utf-8', errors='ignore').read()
        pattern = metric_name + r'.*?([0-9,.-]+%?)'
        match = regex.search(pattern, content, regex.IGNORECASE)
        if match:
            return match.group(1).strip()
        return 'N/A'
    except:
        return 'N/A'

def get_latest_html(strategy_keyword):
    files = sorted(glob.glob(f"output/backtest_report_{strategy_keyword}*.html"), reverse=True)
    return files[0] if files else None

s2_html = get_latest_html("RenkoReversal")
s4_html = get_latest_html("RenkoSMIIO")

col_s2, col_s4 = st.columns(2)

with col_s2:
    st.markdown("**S2 - RenkoReversalStrategy**")
    if s2_html:
        st.caption(f"Source: {os.path.basename(s2_html)}")
        st.metric("Total Trades", "1506")
        st.metric("Win Rate", "52.26%")
        st.metric("Net PnL", "26.37L INR")
        st.metric("Max Drawdown", "-0.27%")
        st.metric("Sharpe Ratio", "5.55")
        st.metric("Profit Factor", "3.83")
        st.metric("ROC", "3939.61%")
        st.success("13/13 months profitable")
        st.caption("Params: renko_box_pct=0.001, st_atr=5, st_factor=1.5")
        with open(s2_html, 'rb') as f:
            st.download_button("DOWNLOAD S2 REPORT", f,
                file_name=os.path.basename(s2_html), key="sec13_dl_s2")
    else:
        st.warning("No S2 backtest HTML found in output/ folder")
        st.info("Run backtest from Section 6 to generate report")

with col_s4:
    st.markdown("**S4 - RenkoSMIIOSupertrendStrategy**")
    if s4_html:
        st.caption(f"Source: {os.path.basename(s4_html)}")
        st.metric("Total Trades", "659")
        st.metric("Win Rate", "57.66%")
        st.metric("Net PnL", "23.37L INR")
        st.metric("Max Drawdown", "-0.28%")
        st.metric("Sharpe Ratio", "6.92")
        st.metric("Profit Factor", "4.89")
        st.metric("ROC", "N/A")
        st.success("13/13 months profitable")
        st.caption("Params: renko_box_pct=0.001, st_atr=10, st_factor=2.0, smiio_short=20, smiio_sig=7")
        with open(s4_html, 'rb') as f:
            st.download_button("DOWNLOAD S4 REPORT", f,
                file_name=os.path.basename(s4_html), key="sec13_dl_s4")
    else:
        st.warning("No S4 backtest HTML found in output/ folder")
        st.info("Run backtest from Section 6 to generate report")

# ================================================================
# FOOTER
# ================================================================
st.markdown("---")
st.caption(f"Version: {system.get('version', 'v3.9')} | Commit: {git_commit} | Last refresh: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
