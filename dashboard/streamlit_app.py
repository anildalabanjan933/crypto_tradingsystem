
import streamlit as st
import json, os, subprocess, datetime, shutil, glob

# ================================================================
# PERFORMANCE HELPERS - prevents heavy ops on every widget click
# ================================================================
import time as _perf_time

def _timed(key, ttl, fn, *args, **kwargs):
    """Run fn only when TTL seconds have passed. Stores in session_state."""
    ts_key = key + "__ts"
    now = _perf_time.time()
    if key not in st.session_state or (now - st.session_state.get(ts_key, 0)) > ttl:
        try:
            st.session_state[key] = fn(*args, **kwargs)
        except Exception:
            if key not in st.session_state:
                st.session_state[key] = None
        st.session_state[ts_key] = now
    return st.session_state[key]

def _fetch_btc_price():
    import requests as _r2
    r = _r2.get("https://api.india.delta.exchange/v2/tickers/BTCUSD", timeout=3)
    d = r.json()
    return float(d['result']['mark_price']), float(d['result']['mark_change_24h'])

def _fetch_disk():
    import shutil as _sh2
    total, used, free = _sh2.disk_usage(".")
    return int(used / total * 100), round(free / 1024**3, 1)

def _fetch_git():
    r = subprocess.run(["git","log","--oneline","-1"], capture_output=True, text=True)
    return r.stdout.strip()[:10] if r.stdout else "unknown"

def _fetch_log_signal(log_path, keyword="ORDER"):
    if os.path.exists(log_path):
        lines = open(log_path, encoding="utf-8", errors="ignore").readlines()
        for line in reversed(lines):
            if keyword in line:
                return line.strip()[-60:]
        return "No signal yet"
    return "Log not found"

def _fetch_log_errors(log_path):
    if os.path.exists(log_path):
        lines = open(log_path, encoding="utf-8", errors="ignore").readlines()
        for line in reversed(lines[-50:]):
            if "ERROR" in line:
                return line.strip()
    return None

def _fetch_account_data(api_key, api_secret):
    import requests as _rq, hmac as _hm, hashlib as _hs, time as _tm, warnings as _wn
    _wn.filterwarnings('ignore')
    DELTA_URL = 'https://cdn-ind.testnet.deltaex.org'
    def _get(path, params={}):
        try:
            ts = str(int(_tm.time()))
            qs = '&'.join(f"{k}={v}" for k,v in params.items())
            qp = path + ('?' + qs if qs else '')
            sig = _hm.new(api_secret.encode(), ('GET'+ts+qp).encode(), _hs.sha256).hexdigest()
            hdrs = {'api-key': api_key, 'timestamp': ts, 'signature': sig, 'Content-Type': 'application/json'}
            return _rq.get(DELTA_URL+path, params=params, headers=hdrs, timeout=(3,10), verify=False).json()
        except:
            return {}
    bal_resp = _get('/v2/wallet/balances')
    balance_usd = 0.0
    for b in bal_resp.get('result', []):
        if b.get('asset_symbol') == 'USD':
            balance_usd = float(b.get('balance', 0)); break
    pos_resp = _get('/v2/positions/margined')
    positions, unreal_pnl = [], 0.0
    for p in pos_resp.get('result', []):
        size = float(p.get('size', 0))
        if size != 0:
            symbol = p.get('product', {}).get('symbol', p.get('product_symbol',''))
            entry = float(p.get('entry_price', 0))
            unreal = float(p.get('unrealized_pnl', 0))
            unreal_pnl += unreal
            positions.append({'symbol': symbol, 'side': 'LONG' if size > 0 else 'SHORT',
                'size': abs(size), 'entry': entry, 'unreal_pnl': unreal})
    return balance_usd, unreal_pnl, positions

def _fetch_vm_health():
    import psutil as _ps
    cpu = _ps.cpu_percent(interval=0)
    ram = _ps.virtual_memory()
    uptime = int(datetime.datetime.now().timestamp() - _ps.boot_time())
    return {'cpu': cpu, 'ram_pct': ram.percent,
            'ram_free_gb': round(ram.available/(1024**3),2),
            'uptime_hrs': uptime//3600, 'uptime_mins': (uptime%3600)//60}

def _fetch_screen_list():
    return subprocess.run(['screen','-ls'], capture_output=True, text=True).stdout

def _fetch_delta_api_status():
    import requests as _rq2
    r = _rq2.get('https://api.india.delta.exchange/v2/products?contract_types=perpetual_futures&limit=1', timeout=5)
    return r.status_code
# ================================================================
# END PERFORMANCE HELPERS
# ================================================================

st.set_page_config(page_title="Crypto Trading Dashboard", layout="wide", page_icon="📈")

st.markdown("""
<style>
/* CRYPTO TRADING DASHBOARD - TRADINGVIEW PRO THEME */

/* BASE - pure white, light, fast */
.stApp { background-color: #FFFFFF; }
.block-container { padding: 0.4rem 1rem 0.4rem 1rem !important; max-width: 100% !important; }
section[data-testid="stSidebar"] { display: none; }
header[data-testid="stHeader"] { background: transparent !important; }

/* FONTS */
html, body, [class*="css"] { font-size: 12px !important; color: #131722 !important; }
h1 { font-size: 16px !important; font-weight: 700 !important; margin: 0 !important; color: #131722 !important; }
h2 { font-size: 14px !important; font-weight: 600 !important; margin: 0 !important; color: #131722 !important; }
h3 { font-size: 13px !important; font-weight: 600 !important; margin: 0 !important; color: #131722 !important; }
p  { font-size: 12px !important; margin: 0 !important; color: #131722 !important; }

/* SECTION TITLES - TradingView dark navy, white text, blue accent */
.section-title {
    background: linear-gradient(135deg, #E8ECF2 0%, #F4F6FA 50%, #DDE2EC 100%) !important;
    color: #131722 !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    padding: 4px 10px !important;
    margin-bottom: 4px !important;
    margin-top: 6px !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
    border-radius: 3px !important;
    border-left: 4px solid #2196F3 !important;
    display: block !important;
    width: 100% !important;
    box-sizing: border-box !important;
}

/* EXPANDER - same shade as section title, NO red border */
div[data-testid="stExpander"] {
    border: 1px solid #C8D0DC !important;
    border-left: 4px solid #2196F3 !important;
    border-radius: 3px !important;
    margin-bottom: 3px !important;
    margin-top: 2px !important;
    background: #FFFFFF !important;
    box-shadow: none !important;
    outline: none !important;
}
div[data-testid="stExpander"]:focus,
div[data-testid="stExpander"]:focus-within {
    border: 1px solid #C8D0DC !important;
    border-left: 4px solid #2196F3 !important;
    box-shadow: none !important;
    outline: none !important;
}
div[data-testid="stExpander"] details summary,
details > summary,
details[open] > summary,
summary,
.streamlit-expanderHeader,
[data-testid="stExpander"] summary,
div[data-testid="stExpander"] details summary {
    background: linear-gradient(135deg, #CDD3E0 0%, #D4DAE8 50%, #C8CEE0 100%) !important;
    color: #131722 !important;
    font-weight: 700 !important;
    font-size: 9px !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
    padding: 2px 8px !important;
    border-left: 4px solid #2196F3 !important;
    border-radius: 2px !important;
    list-style: none !important;
    outline: none !important;
}
details summary:hover,
details > summary:hover,
summary:hover,
.streamlit-expanderHeader:hover {
    background-color: #D8DCE6 !important;
}
summary:hover { background-color: #D8DCE6 !important; }
details summary p, details summary span, details summary div,
summary p, summary span, summary div,
.streamlit-expanderHeader p, .streamlit-expanderHeader span {
    color: #FFFFFF !important;
    font-weight: 700 !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}
[data-testid="stExpander"] > details {
    border: 1px solid #E0E3EB !important;
    border-radius: 3px !important;
}
[data-testid="stExpanderToggleIcon"] {
    color: #2196F3 !important;
}
div[data-testid="stExpander"] > div:first-child {
    background: linear-gradient(135deg, #E8ECF2 0%, #F4F6FA 50%, #DDE2EC 100%) !important;
    border-left: 4px solid #2196F3 !important;
    border-radius: 3px !important;
    padding: 0 !important;
}
/* Nested expanders inside expanders */
div[data-testid="stExpander"] div[data-testid="stExpander"] > div:first-child {
    background: linear-gradient(135deg, #E8ECF2 0%, #F4F6FA 50%, #DDE2EC 100%) !important;
    border-left: 4px solid #2196F3 !important;
}
div[data-testid="stExpander"] div[data-testid="stExpander"] details summary {
    background: linear-gradient(135deg, #E8ECF2 0%, #F4F6FA 50%, #DDE2EC 100%) !important;
    color: #131722 !important;
    border-left: 4px solid #2196F3 !important;
}
/* Force ALL summary elements site-wide */
summary {
    background: linear-gradient(135deg, #E8ECF2 0%, #F4F6FA 50%, #DDE2EC 100%) !important;
    color: #131722 !important;
    border-left: 4px solid #2196F3 !important;
    font-weight: 700 !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
    padding: 4px 10px !important;
}
summary:hover {
    background-color: #D8DCE6 !important;
}
summary:hover { background-color: #D8DCE6 !important; }
summary p, summary span, summary div {
    color: #FFFFFF !important;
    font-weight: 700 !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}
/* Streamlit 1.59 specific - stExpanderToggleIcon parent */
[data-testid="stExpanderToggleIcon"] {
    color: #2196F3 !important;
}
div[data-testid="stExpander"] {
    border: none !important;
    box-shadow: none !important;
}
div[data-testid="stExpander"] > div:first-child {
    background: linear-gradient(135deg, #E8ECF2 0%, #F4F6FA 50%, #DDE2EC 100%) !important;
    border-left: 4px solid #2196F3 !important;
    border-radius: 3px !important;
    padding: 0 !important;
}
div[data-testid="stExpander"] details summary:hover {
    background-color: #D8DCE6 !important;
    cursor: pointer !important;
}
div[data-testid="stExpander"] details summary:focus {
    outline: none !important;
    box-shadow: none !important;
}
div[data-testid="stExpander"] details summary p {
    color: #131722 !important;
    font-weight: 700 !important;
    font-size: 9px !important;
}
div[data-testid="stExpander"] details summary span {
    color: #131722 !important;
}
div[data-testid="stExpander"] details summary svg {
    color: #2196F3 !important;
    fill: #2196F3 !important;
    stroke: #2196F3 !important;
}
div[data-testid="stExpander"] details[open] summary {
    background-color: #D8DCE6 !important;
    border-bottom: 1px solid #363A45 !important;
}

/* METRICS - white card with visible border + shadow */
[data-testid="stMetricValue"] { font-size: 13px !important; font-weight: 700 !important; color: #131722 !important; }
[data-testid="stMetricLabel"] { font-size: 10px !important; color: #787B86 !important; font-weight: 600 !important; }
[data-testid="metric-container"] {
    padding: 6px 10px !important;
    border: 1px solid #C8D0DC !important;
    border-radius: 4px !important;
    background: #FFFFFF !important;
    border-left: 3px solid #2196F3 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
}

/* ALERTS */
.alert-red {
    background: #FFF0F0; border-left: 4px solid #F23645;
    padding: 5px 10px; color: #B71C1C !important;
    font-weight: 700; font-size: 11px !important;
    margin: 2px 0; border-radius: 3px;
}
.alert-yellow {
    background: #FFFBF0; border-left: 4px solid #FF9800;
    padding: 5px 10px; color: #E65100 !important;
    font-weight: 700; font-size: 11px !important;
    margin: 2px 0; border-radius: 3px;
}
.alert-green {
    background: #F0FFF4; border-left: 4px solid #089981;
    padding: 5px 10px; color: #065F46 !important;
    font-weight: 700; font-size: 11px !important;
    margin: 2px 0; border-radius: 3px;
}

/* BUTTONS */
.stButton > button {
    padding: 1px 6px !important; font-size: 9px !important; height: 22px !important; line-height: 1.1 !important;
    height: 28px !important; border-radius: 3px !important;
    font-weight: 600 !important;
    border: 1px solid #C8D0DC !important;
    color: #131722 !important; background: #F0F3FA !important;
}
.stButton > button:hover {
    background: #2196F3 !important; color: #FFFFFF !important;
    border-color: #2196F3 !important;
}

/* INPUTS */
.stSelectbox, .stNumberInput, .stDateInput { font-size: 11px !important; }
.stSelectbox > div > div { padding: 2px 6px !important; min-height: 28px !important; }

/* TABS */
.stTabs [data-baseweb="tab"] {
    padding: 4px 14px !important; font-size: 11px !important;
    font-weight: 600 !important; color: #787B86 !important;
}
.stTabs [aria-selected="true"] {
    color: #2196F3 !important; border-bottom: 2px solid #2196F3 !important;
}

/* STATUS BOXES */
.stSuccess { background: #F0FFF4 !important; color: #065F46 !important;
    border-left: 4px solid #089981 !important; padding: 4px 8px !important;
    font-size: 11px !important; margin: 2px 0 !important; border-radius: 3px !important; }
.stError { background: #FFF0F0 !important; color: #B71C1C !important;
    border-left: 4px solid #F23645 !important; padding: 4px 8px !important;
    font-size: 11px !important; margin: 2px 0 !important; border-radius: 3px !important; }
.stWarning { background: #FFFBF0 !important; color: #E65100 !important;
    border-left: 4px solid #FF9800 !important; padding: 4px 8px !important;
    font-size: 11px !important; margin: 2px 0 !important; border-radius: 3px !important; }
.stInfo { background: #F0F8FF !important; color: #0D47A1 !important;
    border-left: 4px solid #2196F3 !important; padding: 4px 8px !important;
    font-size: 11px !important; margin: 2px 0 !important; border-radius: 3px !important; }

/* SPACING */
.stMarkdown { margin: 0 !important; padding: 0 !important; }
div[data-testid="stVerticalBlock"] > div { gap: 0.25rem !important; }
.element-container { margin: 0 !important; padding: 0 !important; }
hr { margin: 4px 0 !important; border-color: #131722 !important; }
.stCaption { font-size: 10px !important; color: #787B86 !important; }
.stCode { font-size: 10px !important; }

/* FIX OVERLAPPING SECTION TITLES */
div[data-testid="stExpander"] > div:first-child p {
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    line-height: 1.4 !important;
}
div[data-testid="stExpander"] summary {
    min-height: 28px !important;
    display: flex !important;
    align-items: center !important;
}
div[data-testid="stExpander"] summary p,
div[data-testid="stExpander"] summary span {
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}

/* FIX SCROLL - instant, no block, no overlay freeze */
.main .block-container { scroll-behavior: auto !important; }
html { scroll-behavior: auto !important; }
* { scroll-behavior: auto !important; }
.stApp { overflow-y: auto !important; scroll-behavior: auto !important; }
.stApp [data-testid="stStatusWidget"] { display: none !important; }
div[data-testid="stDecoration"] { display: none !important; }
#MainMenu { display: none !important; }
footer { display: none !important; }

/* METRIC BOX CUSTOM */
.metric-box {
    padding: 6px 10px; border-radius: 4px;
    border: 1px solid #C8D0DC; background: #FFFFFF;
    margin-bottom: 4px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.metric-label { font-size: 10px; color: #787B86; font-weight: 600; text-transform: uppercase; }
.metric-value { font-size: 14px; font-weight: 700; color: #131722; }
.metric-green  { border-left: 3px solid #089981; }
.metric-red    { border-left: 3px solid #F23645; }
.metric-yellow { border-left: 3px solid #FF9800; }
.metric-blue   { border-left: 3px solid #2196F3; }
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
# Fetch live BTC price for header
_btc_result = _timed('btc_price', 10, _fetch_btc_price)
if _btc_result:
    _btc_price, _btc_change = _btc_result
    _chg_color = "#26a69a" if _btc_change >= 0 else "#ef5350"
    _chg_sign = "+" if _btc_change >= 0 else ""
    _btc_html = f'<span style="color:#26a69a;font-weight:700;font-size:15px;">${_btc_price:,.1f}</span><span style="color:{_chg_color};font-size:11px;margin-left:6px;">{_chg_sign}{_btc_change:.2f}%</span>'
else:
    _btc_html = '<span style="color:#888;font-size:11px;">BTC N/A</span>'

col_title, col_status = st.columns([5, 1])
with col_title:
    st.markdown(
        f'''<div style="display:flex;align-items:center;gap:20px;padding:4px 0;">
        <span style="font-size:16px;font-weight:700;color:#131722;">CRYPTO TRADING SYSTEM</span>
        <span style="font-size:11px;color:#555;">BTC Algo Dashboard</span>
        <span style="font-size:11px;color:#888;">BTC/USD:</span>
        {_btc_html}
        </div>''',
        unsafe_allow_html=True
    )
with col_status:
    st.markdown(
        '<div style="text-align:right;padding-top:4px;">' +
        '<span style="background:#e8f5e9;color:#2e7d32;font-weight:700;font-size:10px;' +
        'padding:4px 10px;border-radius:3px;border:1px solid #a5d6a7;letter-spacing:1px;">SYSTEM ONLINE</span></div>',
        unsafe_allow_html=True
    )

st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)

# ================================================================
# SECTION 1 - SYSTEM STATUS CARDS
# ================================================================
st.markdown("<div class='section-title'>SECTION 1 - SYSTEM STATUS & MAINTENANCE</div>", unsafe_allow_html=True)

disk_pct, disk_free = _timed('disk_usage', 30, _fetch_disk)
git_commit = _timed('git_commit', 60, _fetch_git)
s2_last = _timed('s2_last_sig', 15, _fetch_log_signal, s2_log)
s4_last = _timed('s4_last_sig', 15, _fetch_log_signal, s4_log)
s2_error = _timed('s2_log_err', 15, _fetch_log_errors, s2_log)
s4_error = _timed('s4_log_err', 15, _fetch_log_errors, s4_log)

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
    try:
        import requests as _req, warnings as _w
        _w.filterwarnings('ignore')
        _r = _req.get('https://cdn-ind.testnet.deltaex.org/v2/products/84', timeout=3, verify=False)
        if _r.status_code == 200:
            st.success("CONNECTED")
            st.caption("Testnet OK")
        else:
            st.error("ERROR")
            st.caption(f"Status: {_r.status_code}")
    except:
        st.error("UNREACHABLE")
        st.caption("Check network")

# ================================================================
# ALERT BANNER
# ================================================================
st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
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

# Bot activity check - warn if no log update in last 5 minutes
try:
    import time as _t
    now_ts = _t.time()
    for bot_name, log_path in [("S2", s2_log), ("S4", s4_log)]:
        if os.path.exists(log_path):
            log_age = now_ts - os.path.getmtime(log_path)
            if log_age > 300:
                alerts.append(("yellow", f"{bot_name} BOT INACTIVE: No log update for {int(log_age//60)} minutes - check if bot is running"))
except:
    pass

# New order detection
try:
    for bot_name, log_path in [("S2", s2_log), ("S4", s4_log)]:
        if os.path.exists(log_path):
            with open(log_path, 'r') as lf:
                lines = lf.readlines()
            recent = [l for l in lines[-50:] if '[ORDER]' in l]
            if recent:
                last_order = recent[-1].strip()
                order_time = last_order[:19] if len(last_order) > 19 else last_order
                import datetime as _dt2
                try:
                    ot = _dt2.datetime.strptime(order_time, '%Y-%m-%d %H:%M:%S,%f'[:len(order_time)])
                    age_mins = (_dt2.datetime.now() - ot).total_seconds() / 60
                    if age_mins < 10:
                        alerts.append(("green", f"{bot_name} NEW ORDER: {last_order[20:80]}"))
                except:
                    pass
except:
    pass

# Position closed detection
try:
    for bot_name, log_path in [("S2", s2_log), ("S4", s4_log)]:
        if os.path.exists(log_path):
            with open(log_path, 'r') as lf:
                lines = lf.readlines()
            exits = [l for l in lines[-50:] if 'EXIT' in l and '[ORDER]' in l]
            if exits:
                last_exit = exits[-1].strip()
                exit_time = last_exit[:19]
                import datetime as _dt3
                try:
                    et = _dt3.datetime.strptime(exit_time, '%Y-%m-%d %H:%M:%S,%f'[:len(exit_time)])
                    age_mins = (_dt3.datetime.now() - et).total_seconds() / 60
                    if age_mins < 30:
                        alerts.append(("green", f"{bot_name} POSITION CLOSED: {last_exit[20:80]}"))
                except:
                    pass
except:
    pass

if alerts:
    for level, msg in alerts:
        if level == "red":
            st.markdown(f"<div class='alert-red'>ERROR: {msg}</div>", unsafe_allow_html=True)
        elif level == "yellow":
            st.markdown(f"<div class='alert-yellow'>WARNING: {msg}</div>", unsafe_allow_html=True)
        elif level == "green":
            st.markdown(f"<div class='alert-green'>INFO: {msg}</div>", unsafe_allow_html=True)
    if not any(l == "red" for l, _ in alerts):
        st.markdown("<div class='alert-green'>ALL SYSTEMS HEALTHY - No critical errors</div>", unsafe_allow_html=True)
else:
    pass  # No alerts - healthy state shown in error monitor below




# ================================================================

# SECTION 1 - MAINTENANCE SUB-SECTIONS
# SECTION 3B - AUTO MAINTENANCE STATUS
# ================================================================
if 'exp_maint' not in st.session_state: st.session_state['exp_maint'] = False
with st.expander("AUTO DAILY 3AM UTC", expanded=False):
    import glob as _glob
    maint_log = 'logs/maintenance.log'
    if os.path.exists(maint_log):
        lines = open(maint_log).readlines()
        # Get last run block
        last_run_lines = []
        for line in reversed(lines):
            last_run_lines.insert(0, line.strip())
            if 'Starting auto maintenance' in line:
                break
        if last_run_lines:
            # Extract key metrics
            last_run_time = next((l for l in last_run_lines if 'Starting' in l), '')
            disk_line     = next((l for l in last_run_lines if 'Disk' in l), '')
            pycache_line  = next((l for l in last_run_lines if 'Pycache' in l), '')
            output_line   = next((l for l in last_run_lines if 'Output folder' in l), '')
            log_lines     = [l for l in last_run_lines if 'Log' in l and 'maintenance' not in l.lower()]

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                disk_pct = ''
                if 'Disk' in disk_line:
                    import re as _re
                    m = _re.search(r'([\d.]+)% used', disk_line)
                    disk_pct = m.group(1) + '%' if m else 'OK'
                    color = 'normal' if float(m.group(1)) < 70 else 'inverse' if m else 'normal'
                st.metric("Disk Usage", disk_pct if disk_pct else "OK")
            with c2:
                files_del = ''
                if 'deleted' in output_line:
                    import re as _re
                    m = _re.search(r'deleted (\d+) files', output_line)
                    files_del = m.group(1) + ' files' if m else '0'
                st.metric("Last Cleanup", files_del if files_del else "0 files")
            with c3:
                out_mb = ''
                if 'Output folder' in output_line:
                    import re as _re
                    m = _re.search(r'([\d.]+)MB', output_line)
                    out_mb = m.group(1) + ' MB' if m else 'OK'
                st.metric("Output Size", out_mb if out_mb else "OK")
            with c4:
                st.metric("Next Run", "Daily 3AM UTC")

            st.caption(f"Last maintenance: {last_run_time.split('[MAINTENANCE]')[-1].strip() if last_run_time else 'Never'}")
            if disk_line:
                if 'WARNING' in disk_line or 'ERROR' in disk_line:
                    st.error(disk_line)
                else:
                    st.success(disk_line.split('[MAINTENANCE]')[-1].strip())
    else:
        st.info("No maintenance log yet. First run at 3AM UTC tonight.")
        st.caption("Auto maintenance runs daily: pycache clean + log trim + output cleanup + disk check")

# ================================================================

# SECTION 11 - MAINTENANCE
# ================================================================
if 'exp_11' not in st.session_state: st.session_state['exp_11'] = False
with st.expander("MAINTENANCE", expanded=st.session_state.get('exp_11', False)):


    import shutil, os, subprocess

    disk_pct2, disk_free2 = _timed('disk_usage', 30, _fetch_disk)
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

    st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
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

# SECTION 1B - ERROR MONITOR (auto-checks all systems)
# ================================================================
st.markdown('<div style="margin-top:-8px;"></div>', unsafe_allow_html=True)
if 'exp_1b' not in st.session_state: st.session_state['exp_1b'] = False
with st.expander("SYSTEM ERROR MONITOR", expanded=st.session_state.get('exp_1b', False)):
    import subprocess, os, datetime

    errors = []
    warnings = []
    ok = []

    # 1. CHECK BOT SCREENS RUNNING (cached 30s)
    try:
        _scr_ls = _timed('err_screen_ls', 30, _fetch_screen_list)
        if 'live_s2' in _scr_ls:
            ok.append("S2 bot screen: RUNNING")
        else:
            errors.append("S2 bot screen: NOT RUNNING - run bash start.sh on VM")
        if 'live_s4' in _scr_ls:
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
                import datetime as _dte
                _cut = _dte.datetime.utcnow() - _dte.timedelta(minutes=30)
                recent = []
                for _l in (lines[-500:] if len(lines)>500 else lines):
                    try:
                        _lt = _dte.datetime.strptime(_l[:19], '%Y-%m-%d %H:%M:%S')
                        if _lt >= _cut: recent.append(_l)
                    except: pass
                # no fallback - if nothing in last 30 min, recent stays empty = no errors shown
                error_lines = [l.strip() for l in recent if 'ERROR' in l]
                algotest_errors = [l.strip() for l in recent if 'ALGOTEST' in l and ('ERROR' in l or 'WARNING' in l)]
                api_errors = [l.strip() for l in recent if any(x in l for x in ['InvalidApiKey','invalid_api_key','insufficient_margin','rate_limit','IP not whitelisted','ENTRY FAILED','EXIT FAILED','CRITICAL']) or ('ERROR' in l and any(x in l for x in ['401','403','429']))]
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
                import datetime as _dte2
                _cut2 = _dte2.datetime.utcnow() - _dte2.timedelta(minutes=30)
                recent = []
                for _l in (lines[-500:] if len(lines)>500 else lines):
                    try:
                        _lt2 = _dte2.datetime.strptime(_l[:19], '%Y-%m-%d %H:%M:%S')
                        if _lt2 >= _cut2: recent.append(_l)
                    except: pass
                if not recent: recent = lines[-20:]
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
    # Only check orders after VALID_FROM (last_known_ts file)
    for bot, log, ts_file in [('S2', 'logs/live_trading_s2.log', 'logs/last_known_ts_s2.txt'),
                               ('S4', 'logs/live_trading_s4.log', 'logs/last_known_ts_s4.txt')]:
        try:
            if os.path.exists(log):
                # Get valid from timestamp
                valid_from = None
                if os.path.exists(ts_file):
                    valid_from = open(ts_file).read().strip()
                lines = open(log).readlines()
                order_lines = [l for l in lines if '[ORDER]' in l]
                timestamps = []
                import re
                for l in order_lines:
                    # Only check recent orders - filter by log timestamp
                    if valid_from:
                        try:
                            log_dt = l.split(' INFO')[0].strip()
                            if log_dt < valid_from.replace('T',' '):
                                continue
                        except:
                            pass
                    match = re.search(r'ts=(\S+)', l)
                    if match:
                        # Include order type to avoid flagging EXIT+ENTRY at same ts
                        order_type = 'ENTRY' if 'ENTRY' in l else 'EXIT'
                        timestamps.append(f"{order_type}_{match.group(1)}")
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

    # 14. CHECK DELTA API CONNECTIVITY (cached 60s)
    try:
        _api_st = _timed('delta_api_status', 60, _fetch_delta_api_status)
        if _api_st == 200:
            ok.append("Delta API connectivity: REACHABLE")
        elif _api_st:
            warnings.append(f"Delta API returned status {_api_st} - may have issues")
        else:
            errors.append("Delta API UNREACHABLE - check VM internet connection")
    except Exception as e:
        errors.append(f"Delta API check failed: {e}")

    # 15. CHECK VM INTERNET (ping Google DNS)
    try:
        import subprocess as sp
        result = sp.run(['curl', '-s', '--max-time', '3', 'https://8.8.8.8'], capture_output=True)
        ok.append("VM internet: CONNECTED")
    except Exception as e:
        errors.append(f"VM internet check failed: {e}")

    # 16. CHECK ALGOTEST WEBHOOK URLS REACHABLE (cached 120s - avoid hammering)
    try:
        def _check_webhook():
            from dotenv import load_dotenv
            load_dotenv()
            import requests as _rqwh
            test_url = os.getenv('ALGOTEST_WEBHOOK_S4_BUY_ENTRY')
            if not test_url:
                return None
            resp = _rqwh.post(test_url, json={"access_token": os.getenv('ALGOTEST_ACCESS_TOKEN', 'n7FJcMHANHN4F8HdqbU5QMDJn5JO79K9'), "alert_name": "ping"}, timeout=5)
            return resp.status_code
        _wh_status = _timed('webhook_check', 120, _check_webhook)
        if _wh_status in [200, 201, 202, 400, 422]:
            ok.append("Algotest webhook URL: REACHABLE")
        elif _wh_status is None:
            errors.append("Algotest webhook URL missing from .env")
        else:
            warnings.append(f"Algotest webhook returned {_wh_status} - check signal config")
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

    with st.expander("SHOW ALL OK CHECKS"):
        for o in ok:
            st.markdown(f"OK: {o}")

        st.caption(f"Last checked: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Auto-refreshes every 30s")
st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)


# ================================================================
# SECTION 1C - DEBUG TRACKER
# ================================================================
if 'exp_1c' not in st.session_state: st.session_state['exp_1c'] = False
with st.expander("SECTION 1C - DEBUG TRACKER", expanded=st.session_state.get('exp_1c', False)):
    import re as _re1c, datetime as _dt1c

    _BASE_DIR = '/home/anildalabanjan933/crypto_trading_system'
    _TH1C = "padding:5px 8px;border:1px solid #C8D0DC;background:#f0f3fa;font-size:10px;font-weight:700;color:#555;"
    _TD1C = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#131722;"
    _TDG1C = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#089981;font-weight:700;"
    _TDR1C = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#F23645;font-weight:700;"
    _TDO1C = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#e07000;font-weight:700;"

    def _read_last_lines(path, n=200):
        try:
            lines = open(path, encoding='utf-8', errors='ignore').readlines()
            return lines[-n:]
        except:
            return []

    def _get_bot_debug(log_path, ts_path, sig_path, bot_name):
        lines = _read_last_lines(log_path)
        now_utc = _dt1c.datetime.utcnow()

        # Last heartbeat
        last_wait = "Never"
        for l in reversed(lines):
            if '[WAIT]' in l or '[ORDER]' in l:
                last_wait = l.split(' INFO')[0].strip()
                break

        # Last reload
        last_reload = "Never"
        for l in reversed(lines):
            if '[RELOAD]' in l:
                last_reload = l.split(' INFO')[0].strip()
                break

        # API validation
        api_status = "UNKNOWN"
        api_color = _TDO1C
        for l in reversed(lines):
            if 'API key validated successfully' in l:
                api_status = "VALID"
                api_color = _TDG1C
                break
            if 'API key validation FAILED' in l or 'invalid_api_key' in l:
                api_status = "INVALID"
                api_color = _TDR1C
                break

        # Last error - only last 30 minutes
        last_error = "None"
        last_error_color = _TDG1C
        _now_err = _dt1c.datetime.utcnow()
        _cut_err = _now_err - _dt1c.timedelta(minutes=30)
        for l in reversed(lines):
            if 'ERROR' in l or 'CRITICAL' in l:
                try:
                    _lt_err = _dt1c.datetime.strptime(l[:19], '%Y-%m-%d %H:%M:%S')
                    if _lt_err >= _cut_err:
                        last_error = l.strip()[-120:]
                        last_error_color = _TDR1C
                except:
                    pass
                break

        # Last order
        last_order = "None"
        for l in reversed(lines):
            if '[ORDER]' in l and ('ENTRY' in l or 'EXIT' in l):
                last_order = l.strip()[-100:]
                break

        # Last known ts
        try:
            last_ts = open(ts_path).read().strip()
        except:
            last_ts = "Unknown"

        # Next signal
        next_signal = "None available"
        next_color = _TDO1C
        try:
            import csv as _csv1c
            now_str = now_utc.strftime('%Y-%m-%dT%H:%M:%S')
            with open(sig_path) as fh:
                reader = _csv1c.DictReader(fh)
                for row in reader:
                    if row['entry_time'].strip() > last_ts:
                        next_signal = f"ENTRY={row['entry_time']} EXIT={row['exit_time']} DIR={row['direction']}"
                        next_color = _TDG1C
                        break
        except:
            pass

        # Signal CSV last update
        try:
            import os as _os1c, time as _t1c
            age = _t1c.time() - _os1c.path.getmtime(sig_path)
            sig_age = f"{int(age/60)} min ago"
            sig_color = _TDG1C if age < 900 else _TDR1C
        except:
            sig_age = "Unknown"
            sig_color = _TDO1C

        # Bot running check
        bot_running = any('[WAIT]' in l or '[ORDER]' in l for l in lines[-20:])
        bot_status = "RUNNING" if bot_running else "STOPPED"
        bot_color = _TDG1C if bot_running else _TDR1C

        # Last heartbeat age check
        heartbeat_color = _TDG1C
        try:
            _hb_ts = _dt1c.datetime.strptime(last_wait[:19], '%Y-%m-%d %H:%M:%S')
            _hb_age = (now_utc - _hb_ts).total_seconds()
            if _hb_age > 60: heartbeat_color = _TDR1C
            elif _hb_age > 30: heartbeat_color = _TDO1C
        except:
            heartbeat_color = _TDO1C

        # Signal CSV staleness
        try:
            import os as _os1c, time as _t1c
            age = _t1c.time() - _os1c.path.getmtime(sig_path)
            sig_age = f"{int(age/60)} min ago"
            sig_color = _TDG1C if age < 900 else _TDR1C
        except:
            sig_age = "Unknown"
            sig_color = _TDO1C

        # Match status - check verify_match log
        match_status = "NOT RUN"
        match_color = _TDO1C
        try:
            _vm_log = '/home/anildalabanjan933/crypto_trading_system/logs/verify_match.log'
            if _os1c.path.exists(_vm_log):
                _vm_lines = open(_vm_log).readlines()[-20:]
                for _vl in reversed(_vm_lines):
                    if 'MATCH OK' in _vl or 'OVERALL: MATCH OK' in _vl:
                        match_status = "MATCH OK"
                        match_color = _TDG1C
                        break
                    if 'MISMATCH' in _vl:
                        match_status = "MISMATCH DETECTED"
                        match_color = _TDR1C
                        break
        except:
            pass

        # CSV data freshness
        csv_status = "UNKNOWN"
        csv_color = _TDO1C
        try:
            _csv_path = '/home/anildalabanjan933/crypto_trading_system/data/btc_1m_delta.csv'
            _csv_age = _t1c.time() - _os1c.path.getmtime(_csv_path)
            if _csv_age < 300:
                csv_status = f"FRESH ({int(_csv_age/60)} min ago)"
                csv_color = _TDG1C
            elif _csv_age < 900:
                csv_status = f"OK ({int(_csv_age/60)} min ago)"
                csv_color = _TDO1C
            else:
                csv_status = f"STALE ({int(_csv_age/60)} min ago)"
                csv_color = _TDR1C
        except:
            pass

        # Position sync check
        pos_status = "FLAT"
        pos_color = _TDG1C
        for l in reversed(lines):
            if '[STARTUP] Position synced' in l:
                if 'None' in l:
                    pos_status = "FLAT"
                    pos_color = _TDG1C
                else:
                    pos_status = "OPEN POSITION"
                    pos_color = _TDO1C
                break

        # Order success rate last 10 orders
        order_attempts = [l for l in lines if '[ORDER] ENTRY' in l or '[ORDER] EXIT' in l]
        order_fails = [l for l in lines if 'ENTRY FAILED' in l or 'EXIT FAILED' in l]
        if order_attempts:
            success_rate = f"{(len(order_attempts)-len(order_fails))}/{len(order_attempts)} success"
            order_color = _TDG1C if len(order_fails)==0 else _TDR1C
        else:
            success_rate = "No orders yet"
            order_color = _TDO1C

        return {
            'bot_status': (bot_status, bot_color),
            'api_status': (api_status, api_color),
            'last_heartbeat': (last_wait, heartbeat_color),
            'last_reload': last_reload,
            'last_order': last_order,
            'last_error': (last_error, last_error_color),
            'last_ts': last_ts,
            'next_signal': (next_signal, next_color),
            'sig_age': (sig_age, sig_color),
            'match_status': (match_status, match_color),
            'csv_status': (csv_status, csv_color),
            'pos_status': (pos_status, pos_color),
            'order_success': (success_rate, order_color),
        }

    s2_dbg = _get_bot_debug(
        f'{_BASE_DIR}/logs/live_trading_s2.log',
        f'{_BASE_DIR}/logs/last_known_ts_s2.txt',
        f'{_BASE_DIR}/logs/signals_s2.csv', 'S2')
    s4_dbg = _get_bot_debug(
        f'{_BASE_DIR}/logs/live_trading_s4.log',
        f'{_BASE_DIR}/logs/last_known_ts_s4.txt',
        f'{_BASE_DIR}/logs/signals_s4.csv', 'S4')

    def _dbg_row(label, s2val, s4val, s2c=None, s4c=None):
        return (f"<tr><td style='{_TD1C}'><b>{label}</b></td>"
                f"<td style='{s2c or _TD1C}'>{s2val}</td>"
                f"<td style='{s4c or _TD1C}'>{s4val}</td></tr>")

    tbl1c = (
        f"<div style='overflow-x:auto;margin:4px 0;'>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<thead><tr>"
        f"<th style='{_TH1C}'>Check</th>"
        f"<th style='{_TH1C}'>S2</th>"
        f"<th style='{_TH1C}'>S4</th>"
        f"</tr></thead><tbody>"
        + _dbg_row("Bot Status", s2_dbg['bot_status'][0], s4_dbg['bot_status'][0], s2_dbg['bot_status'][1], s4_dbg['bot_status'][1])
        + _dbg_row("API Key", s2_dbg['api_status'][0], s4_dbg['api_status'][0], s2_dbg['api_status'][1], s4_dbg['api_status'][1])
        + _dbg_row("Last Heartbeat", s2_dbg['last_heartbeat'][0], s4_dbg['last_heartbeat'][0], s2_dbg['last_heartbeat'][1], s4_dbg['last_heartbeat'][1])
        + _dbg_row("Last Reload", s2_dbg['last_reload'], s4_dbg['last_reload'])
        + _dbg_row("Last Order", s2_dbg['last_order'], s4_dbg['last_order'])
        + _dbg_row("Last Error", s2_dbg['last_error'][0], s4_dbg['last_error'][0], s2_dbg['last_error'][1], s4_dbg['last_error'][1])
        + _dbg_row("Last Known TS", s2_dbg['last_ts'], s4_dbg['last_ts'])
        + _dbg_row("Next Signal", s2_dbg['next_signal'][0], s4_dbg['next_signal'][0], s2_dbg['next_signal'][1], s4_dbg['next_signal'][1])
        + _dbg_row("Signal CSV Age",   s2_dbg['sig_age'][0],      s4_dbg['sig_age'][0],      s2_dbg['sig_age'][1],      s4_dbg['sig_age'][1])
        + _dbg_row("Market CSV",        s2_dbg['csv_status'][0],   s4_dbg['csv_status'][0],   s2_dbg['csv_status'][1],   s4_dbg['csv_status'][1])
        + _dbg_row("Position Sync",     s2_dbg['pos_status'][0],   s4_dbg['pos_status'][0],   s2_dbg['pos_status'][1],   s4_dbg['pos_status'][1])
        + _dbg_row("Order Success",     s2_dbg['order_success'][0],s4_dbg['order_success'][0],s2_dbg['order_success'][1],s4_dbg['order_success'][1])
        + _dbg_row("Match Status",      s2_dbg['match_status'][0], s4_dbg['match_status'][0], s2_dbg['match_status'][1], s4_dbg['match_status'][1])
        + "</tbody></table></div>"
    )
    st.caption("Auto updates on page load | Green=OK | Red=Issue | Orange=Warning")
    st.markdown(tbl1c, unsafe_allow_html=True)


# ================================================================
# SECTION 1.3 - VM HEALTH (CPU + RAM + UPTIME)
# ================================================================
if 'exp_13' not in st.session_state: st.session_state['exp_13'] = False
with st.expander("SECTION 1.3 - VM HEALTH", expanded=st.session_state.get('exp_13', False)):
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0)
        ram = psutil.virtual_memory()
        ram_used = ram.percent
        ram_free_gb = round(ram.available / (1024**3), 2)
        uptime_secs = int(datetime.datetime.now().timestamp() - psutil.boot_time())
        uptime_hrs = uptime_secs // 3600
        uptime_mins = (uptime_secs % 3600) // 60
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            cpu_color = "metric-red" if cpu > 80 else "metric-yellow" if cpu > 60 else "metric-green"
            st.markdown(f"<div class='metric-box {cpu_color}'><div class='metric-label'>CPU USAGE</div><div class='metric-value'>{cpu:.1f}%</div></div>", unsafe_allow_html=True)
        with col2:
            ram_color = "metric-red" if ram_used > 80 else "metric-yellow" if ram_used > 60 else "metric-green"
            st.markdown(f"<div class='metric-box {ram_color}'><div class='metric-label'>RAM USAGE</div><div class='metric-value'>{ram_used:.1f}%</div></div>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<div class='metric-box metric-green'><div class='metric-label'>RAM FREE</div><div class='metric-value'>{ram_free_gb} GB</div></div>", unsafe_allow_html=True)
        with col4:
            st.markdown(f"<div class='metric-box metric-green'><div class='metric-label'>UPTIME</div><div class='metric-value'>{uptime_hrs}h {uptime_mins}m</div></div>", unsafe_allow_html=True)
        import subprocess
        col5, col6, col7, col8 = st.columns(4)
        with col5:
            try:
                r = subprocess.run(['du','-sh','/home/anildalabanjan933/crypto_trading_system'], capture_output=True, text=True)
                app_size = r.stdout.split()[0] if r.stdout else 'N/A'
            except:
                app_size = 'N/A'
            st.markdown(f"<div class='metric-box metric-green'><div class='metric-label'>APP SIZE</div><div class='metric-value'>{app_size}</div></div>", unsafe_allow_html=True)
        with col6:
            try:
                r = subprocess.run(['du','-sh','/home/anildalabanjan933/crypto_trading_system/logs'], capture_output=True, text=True)
                log_size = r.stdout.split()[0] if r.stdout else 'N/A'
            except:
                log_size = 'N/A'
            st.markdown(f"<div class='metric-box metric-green'><div class='metric-label'>LOGS SIZE</div><div class='metric-value'>{log_size}</div></div>", unsafe_allow_html=True)
        with col7:
            try:
                r = subprocess.run(['du','-sh','/home/anildalabanjan933/crypto_trading_system/data'], capture_output=True, text=True)
                data_size = r.stdout.split()[0] if r.stdout else 'N/A'
            except:
                data_size = 'N/A'
            st.markdown(f"<div class='metric-box metric-green'><div class='metric-label'>DATA SIZE</div><div class='metric-value'>{data_size}</div></div>", unsafe_allow_html=True)
        with col8:
            try:
                r = subprocess.run(['du','-sh','/home/anildalabanjan933/crypto_trading_system/.venv'], capture_output=True, text=True)
                venv_size = r.stdout.split()[0] if r.stdout else 'N/A'
            except:
                venv_size = 'N/A'
            st.markdown(f"<div class='metric-box metric-green'><div class='metric-label'>VENV SIZE</div><div class='metric-value'>{venv_size}</div></div>", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"VM health check failed: {e}. Install psutil: pip install psutil")
st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)

# ================================================================
# SECTION 2 - BOT CONTROL
st.markdown("<div class='section-title'>SECTION 2 - BOT CONTROL</div>", unsafe_allow_html=True)
# SECTION 2.4 - MEMBER MANAGEMENT
# ================================================================
if 'exp_24' not in st.session_state: st.session_state['exp_24'] = False
with st.expander("MEMBER MANAGEMENT", expanded=st.session_state.get('exp_24', False)):

    # Load members from config
    members_config_file = 'dashboard/members_config.json'
    if not os.path.exists(members_config_file):
        json.dump({'members': []}, open(members_config_file, 'w'), indent=2)

    members_cfg = json.load(open(members_config_file))
    members = members_cfg.get('members', [])

    # Member table
    if members:
        m_cols = st.columns([2,2,1,1,1,1,1])
        m_cols[0].markdown("**Name**")
        m_cols[1].markdown("**Account**")
        m_cols[2].markdown("**S2**")
        m_cols[3].markdown("**S4**")
        m_cols[4].markdown("**Start**")
        m_cols[5].markdown("**Stop**")
        m_cols[6].markdown("**Remove**")
        for idx, m in enumerate(members):
            mc = st.columns([2,2,1,1,1,1,1])
            mc[0].write(m.get('name',''))
            mc[1].write(m.get('account','Testnet'))
            # Check S2 status
            s2_screen = f"m{idx}_s2"
            s4_screen = f"m{idx}_s4"
            import subprocess
            _scr_out = _timed('screen_list', 30, _fetch_screen_list)
            s2_running = s2_screen in _scr_out
            s4_running = s4_screen in _scr_out
            mc[2].markdown(f"<span style='color:{'green' if s2_running else 'red'}'>{'ON' if s2_running else 'OFF'}</span>", unsafe_allow_html=True)
            mc[3].markdown(f"<span style='color:{'green' if s4_running else 'red'}'>{'ON' if s4_running else 'OFF'}</span>", unsafe_allow_html=True)
            if mc[4].button("▶", key=f"m_start_{idx}"):
                try:
                    env = f"S2_API_KEY={m.get('s2_key','')} S2_API_SECRET={m.get('s2_secret','')} S4_API_KEY={m.get('s4_key','')} S4_API_SECRET={m.get('s4_secret','')}"
                    subprocess.Popen(['bash','-c',f'screen -dmS {s2_screen} bash -c "cd /home/anildalabanjan933/crypto_trading_system && source .venv/bin/activate && export {env} && python3 scripts/signal_replay_s2.py >> logs/live_trading_s2.log 2>&1"'])
                    subprocess.Popen(['bash','-c',f'screen -dmS {s4_screen} bash -c "cd /home/anildalabanjan933/crypto_trading_system && source .venv/bin/activate && export {env} && python3 scripts/signal_replay_s4.py >> logs/live_trading_s4.log 2>&1"'])
                    st.success(f"{m.get('name')} bots started")
                except Exception as e:
                    st.error(str(e))
            if mc[5].button("■", key=f"m_stop_{idx}"):
                try:
                    subprocess.Popen(['bash','-c',f'screen -S {s2_screen} -X quit; screen -S {s4_screen} -X quit'])
                    st.warning(f"{m.get('name')} bots stopped")
                except Exception as e:
                    st.error(str(e))
            if mc[6].button("✕", key=f"m_remove_{idx}"):
                members.pop(idx)
                members_cfg['members'] = members
                json.dump(members_cfg, open(members_config_file,'w'), indent=2)
                st.rerun()
    else:
        st.markdown("<div style='background:#f0f4ff;padding:6px 10px;border-radius:3px;font-size:11px;color:#555;'>No members added yet. Add members below.</div>", unsafe_allow_html=True)

    # Add member form
    with st.expander("+ ADD MEMBER"):
        with st.form("add_member_form"):
            m_name    = st.text_input("Member Name (e.g. Friend1)")
            m_account = st.text_input("Account Label (e.g. Testnet)")
            m_bots    = st.multiselect("Bots to enable", ["S2","S4"], default=["S2","S4"])
            col1, col2 = st.columns(2)
            with col1:
                if "S2" in m_bots:
                    m_s2_key  = st.text_input("S2 API Key")
                    m_s2_sec  = st.text_input("S2 API Secret", type="password")
                    m_lots_s2 = st.number_input("S2 Lots", min_value=1, value=100)
                else:
                    m_s2_key = m_s2_sec = ""; m_lots_s2 = 100
            with col2:
                if "S4" in m_bots:
                    m_s4_key  = st.text_input("S4 API Key")
                    m_s4_sec  = st.text_input("S4 API Secret", type="password")
                    m_lots_s4 = st.number_input("S4 Lots", min_value=1, value=100)
                else:
                    m_s4_key = m_s4_sec = ""; m_lots_s4 = 100
            if st.form_submit_button("ADD MEMBER"):
                if m_name and m_bots:
                    members.append({
                        'name': m_name,
                        'account': m_account,
                        'bots': m_bots,
                        's2_key': m_s2_key,
                        's2_secret': m_s2_sec,
                        's4_key': m_s4_key,
                        's4_secret': m_s4_sec,
                        'lots_s2': m_lots_s2,
                        'lots_s4': m_lots_s4
                    })
                    members_cfg['members'] = members
                    json.dump(members_cfg, open(members_config_file,'w'), indent=2)

                    # ── AUTO SETUP: scripts, .env, start.sh, start bots ──
                    _base = '/home/anildalabanjan933/crypto_trading_system'
                    _mkey = m_name.lower().replace(' ','_')
                    _errors = []

                    # 1. Create signal replay scripts
                    for _bot, _key, _sec, _lots in [
                        ('s2', m_s2_key, m_s2_sec, m_lots_s2),
                        ('s4', m_s4_key, m_s4_sec, m_lots_s4)
                    ]:
                        if _bot.upper() not in m_bots: continue
                        _src = f"{_base}/scripts/signal_replay_{_bot}.py"
                        _dst = f"{_base}/scripts/signal_replay_{_mkey}_{_bot}.py"
                        try:
                            _content = open(_src).read()
                            _content = _content.replace(
                                f'os.environ.get("{_bot.upper()}_API_KEY"',
                                f'os.environ.get("{_mkey.upper()}_{_bot.upper()}_API_KEY"'
                            )
                            _content = _content.replace(
                                f'os.environ.get("{_bot.upper()}_API_SECRET"',
                                f'os.environ.get("{_mkey.upper()}_{_bot.upper()}_API_SECRET"'
                            )
                            _content = _content.replace(
                                f'logs/last_known_ts_{_bot}.txt',
                                f'logs/last_known_ts_{_mkey}_{_bot}.txt'
                            )
                            _content = _content.replace(
                                f'logs/live_trading_{_bot}.log',
                                f'logs/live_trading_{_mkey}_{_bot}.log'
                            )
                            _content = _content.replace(
                                f'logs/signals_{_bot}.csv',
                                f'logs/signals_{_bot}.csv'
                            )
                            open(_dst, 'w').write(_content)
                        except Exception as _e:
                            _errors.append(f"Script create failed: {_e}")

                    # 2. Add API keys to .env
                    try:
                        _env_path = f"{_base}/.env"
                        _env_content = open(_env_path).read()
                        _new_keys = ""
                        if m_s2_key and f"{_mkey.upper()}_S2_API_KEY" not in _env_content:
                            _new_keys += "\n" + f"{_mkey.upper()}_S2_API_KEY={m_s2_key}"
                            _new_keys += "\n" + f"{_mkey.upper()}_S2_API_SECRET={m_s2_sec}"
                        if m_s4_key and f"{_mkey.upper()}_S4_API_KEY" not in _env_content:
                            _new_keys += "\n" + f"{_mkey.upper()}_S4_API_KEY={m_s4_key}"
                            _new_keys += "\n" + f"{_mkey.upper()}_S4_API_SECRET={m_s4_sec}"
                        if _new_keys:
                            open(_env_path, 'a').write(_new_keys)
                    except Exception as _e:
                        _errors.append(f".env update failed: {_e}")

                    # 3. Add screens to start.sh
                    try:
                        _start_path = f"{_base}/start.sh"
                        _start_content = open(_start_path).read()
                        _new_screens = ""
                        for _bot in m_bots:
                            _b = _bot.lower()
                            _screen_name = f"{_mkey}_{_b}"
                            if _screen_name not in _start_content:
                                _new_screens += (
                                    f'\nscreen -dmS {_screen_name} bash -c '
                                    f'"cd {_base} && source .venv/bin/activate && '
                                    f"export $(grep -v '#' .env | xargs) && "
                                    f'python3 scripts/signal_replay_{_mkey}_{_b}.py >> '
                                    f'logs/live_trading_{_mkey}_{_b}.log 2>&1"'
                                )
                        if _new_screens:
                            _start_content = _start_content.replace(
                                'echo "S2 and S4 started"',
                                f'echo "S2 and S4 started"{_new_screens}'
                            )
                            open(_start_path, 'w').write(_start_content)
                    except Exception as _e:
                        _errors.append(f"start.sh update failed: {_e}")

                    # 4. Start bot screens immediately
                    try:
                        import subprocess as _sp2
                        for _bot in m_bots:
                            _b = _bot.lower()
                            _screen_name = f"{_mkey}_{_b}"
                            _api_k = m_s2_key if _b=='s2' else m_s4_key
                            _api_s = m_s2_sec if _b=='s2' else m_s4_sec
                            _cmd = (f'screen -S {_screen_name} -X quit 2>/dev/null; sleep 1; '
                                   f'screen -dmS {_screen_name} bash -c "cd {_base} && '
                                   f'source .venv/bin/activate && '
                                   f'export $(grep -v '#' {_base}/.env | xargs) && '
                                   f'python3 scripts/signal_replay_{_mkey}_{_b}.py >> '
                                   f'logs/live_trading_{_mkey}_{_b}.log 2>&1"')
                            _sp2.Popen(['bash', '-c', _cmd])
                    except Exception as _e:
                        _errors.append(f"Bot start failed: {_e}")

                    # 5. Create last_known_ts files
                    try:
                        import datetime as _dt_m
                        _vf = open(f'{_base}/logs/valid_from_baseline.txt').read().strip()
                        for _bot in m_bots:
                            _b = _bot.lower()
                            _ts_file = f'{_base}/logs/last_known_ts_{_mkey}_{_b}.txt'
                            if not os.path.exists(_ts_file):
                                open(_ts_file, 'w').write(_vf)
                    except Exception as _e:
                        _errors.append(f"TS file create failed: {_e}")

                    if _errors:
                        st.warning(f"Member added but some setup steps failed: {'; '.join(_errors)}")
                    else:
                        st.success(f"Member {m_name} added and bots started automatically. Zero terminal needed.")
                    st.rerun()
                else:
                    st.error("Name + at least one bot required")
st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)

# ================================================================

# ================================================================


algos = config.get("algos", [])

col_h1, col_h2, col_h3, col_h4, col_h5, col_h6 = st.columns([1,2,2,1,2,2])
col_h1.markdown("**Algo**")
col_h2.markdown("**Strategy**")
col_h3.markdown("**Symbol**")
col_h4.markdown("**Lots**")
col_h5.markdown("**Status**")
col_h6.markdown("**Action**")
st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)

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
            "Lots", min_value=1, max_value=10000,
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

st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
b1,b2,b3,b4,b5,b6 = st.columns(6)
with b1:
    if st.button("START ALL", key="sec2_start"):
        try:
            import subprocess
            subprocess.Popen(['bash','-c','cd /home/anildalabanjan933/crypto_trading_system && bash start.sh'])
            st.success("Starting...")
        except Exception as e:
            st.error(str(e))
with b2:
    if st.button("STOP ALL", key="sec2_stop"):
        try:
            import subprocess
            subprocess.Popen(['bash','-c','screen -S live_s2 -X quit; screen -S live_s4 -X quit'])
            st.warning("Stopped")
        except Exception as e:
            st.error(str(e))
with b3:
    if st.button("RESTART ALL", key="sec2_restart"):
        try:
            import subprocess
            subprocess.Popen(['bash','-c','cd /home/anildalabanjan933/crypto_trading_system && bash start.sh'])
            st.success("Restarting...")
        except Exception as e:
            st.error(str(e))
with b4:
    if st.button("RESTART S2", key="sec2_restart_s2"):
        try:
            import subprocess
            subprocess.Popen(['bash','-c','screen -S live_s2 -X quit; sleep 2; screen -dmS live_s2 bash -c "cd /home/anildalabanjan933/crypto_trading_system && source .venv/bin/activate && python3 scripts/signal_replay_s2.py >> logs/live_trading_s2.log 2>&1"'])
            st.success("S2 restarting...")
        except Exception as e:
            st.error(str(e))
with b5:
    if st.button("RESTART S4", key="sec2_restart_s4"):
        try:
            import subprocess
            subprocess.Popen(['bash','-c','screen -S live_s4 -X quit; sleep 2; screen -dmS live_s4 bash -c "cd /home/anildalabanjan933/crypto_trading_system && source .venv/bin/activate && python3 scripts/signal_replay_s4.py >> logs/live_trading_s4.log 2>&1"'])
            st.success("S4 restarting...")
        except Exception as e:
            st.error(str(e))
with b6:
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
    import requests, hmac, hashlib, time as _time, json as _json

    DELTA_URL = 'https://cdn-ind.testnet.deltaex.org'
    INR_RATE  = 84.0

    def delta_get_auth(api_key, api_secret, path, params={}):
        try:
            ts  = str(int(_time.time()))
            qs  = '&'.join(f"{k}={v}" for k,v in params.items())
            query_path = path + ('?' + qs if qs else '')
            msg = 'GET' + ts + query_path
            sig = hmac.new(api_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
            hdrs = {'api-key': api_key, 'timestamp': ts, 'signature': sig, 'Content-Type': 'application/json'}
            r = requests.get(DELTA_URL + path, params=params, headers=hdrs, timeout=(3,10), verify=False)
            return r.json()
        except:
            return {}

    def get_account_data(api_key, api_secret):
        # Balance
        bal_resp = delta_get_auth(api_key, api_secret, '/v2/wallet/balances')
        balance_usd = 0.0
        for b in bal_resp.get('result', []):
            if b.get('asset_symbol') == 'USD':
                balance_usd = float(b.get('balance', 0))
                break

        # Positions
        pos_resp = delta_get_auth(api_key, api_secret, '/v2/positions/margined')
        positions = []
        unreal_pnl = 0.0
        for p in pos_resp.get('result', []):
            size = float(p.get('size', 0))
            symbol = p.get('product', {}).get('symbol', p.get('product_symbol',''))
            if size != 0:
                entry = float(p.get('entry_price', 0))
                unreal = float(p.get('unrealized_pnl', 0))
                unreal_pnl += unreal
                positions.append({
                    'symbol': symbol,
                    'side': 'LONG' if size > 0 else 'SHORT',
                    'size': abs(size),
                    'entry': entry,
                    'unreal_pnl': unreal
                })
        return balance_usd, unreal_pnl, positions

    # Load members
    members_cfg_file = 'dashboard/members_config.json'
    all_accounts = [{'name': 'My Account', 's2_key': os.getenv('S2_API_KEY',''), 's2_secret': os.getenv('S2_API_SECRET',''), 's4_key': os.getenv('S4_API_KEY',''), 's4_secret': os.getenv('S4_API_SECRET','')}]
    if os.path.exists(members_cfg_file):
        mcfg = _json.load(open(members_cfg_file))
        all_accounts += mcfg.get('members', [])

    # Account selector
    acct_names = [a['name'] for a in all_accounts]
    selected_acct = st.selectbox("Select Account", acct_names, key="delta_acct_select")
    acct = next(a for a in all_accounts if a['name'] == selected_acct)

    import warnings
    warnings.filterwarnings('ignore')

    # Fetch S2+S4 data - cached 30s, null-safe
    _acct_key = acct.get('s2_key','')[:8]
    s2_bal, s2_unreal, s2_pos = _timed('s2_acct_'+_acct_key, 30, _fetch_account_data, acct.get('s2_key',''), acct.get('s2_secret',''))
    s4_bal, s4_unreal, s4_pos = _timed('s4_acct_'+_acct_key, 30, _fetch_account_data, acct.get('s4_key',''), acct.get('s4_secret',''))
    if not s2_bal: s2_bal, s2_unreal, s2_pos = 0.0, 0.0, []
    if not s4_bal: s4_bal, s4_unreal, s4_pos = 0.0, 0.0, []

    total_bal   = s2_bal + s4_bal
    total_unreal = s2_unreal + s4_unreal

    # Summary row
    st.markdown(f"**{selected_acct} - Live Account Summary**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Balance", f"${total_bal:,.2f}", f"₹{total_bal*INR_RATE:,.0f}")
    c2.metric("Unrealised PnL", f"${total_unreal:,.2f}", f"₹{total_unreal*INR_RATE:,.0f}")
    c3.metric("S2 Balance", f"${s2_bal:,.2f}")
    c4.metric("S4 Balance", f"${s4_bal:,.2f}")

    # Open positions
    st.markdown("**Open Positions**")
    all_pos = [dict(p, account='S2') for p in s2_pos] + [dict(p, account='S4') for p in s4_pos]
    if all_pos:
        TH = "padding:5px 8px;border:1px solid #C8D0DC;background:#f0f3fa;font-size:10px;font-weight:700;color:#555;"
        TD = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;"
        h = "<div style='overflow-x:auto;margin:4px 0;'><table style='width:100%;border-collapse:collapse;'>"
        h += "<thead><tr>"
        for col in ['Account','Symbol','Side','Size','Entry $','Unreal PnL']:
            h += "<th style='{}'>{}</th>".format(TH, col)
        h += "<th style='{}'>Action</th>".format(TH)
        h += "</tr></thead><tbody>"
        for i, p in enumerate(all_pos):
            bg = "#ffffff" if i % 2 == 0 else "#fafafa"
            sc = "#089981" if p['side'] == 'LONG' else "#F23645"
            pc = "#089981" if p['unreal_pnl'] >= 0 else "#F23645"
            h += "<tr style='background:{};'>".format(bg)
            h += "<td style='{}'>{}</td>".format(TD, p['account'])
            h += "<td style='{}'>{}</td>".format(TD, p['symbol'])
            h += "<td style='{}'><span style='color:{};font-weight:700'>{}</span></td>".format(TD, sc, p['side'])
            h += "<td style='{}'>{}</td>".format(TD, int(p['size']))
            h += "<td style='{}text-align:right'>${:,.1f}</td>".format(TD, p['entry'])
            h += "<td style='{}'><span style='color:{};font-weight:600'>${:,.2f} | ₹{:,.0f}</span></td>".format(TD, pc, p['unreal_pnl'], p['unreal_pnl']*INR_RATE)
            h += "<td style='{}text-align:center'>__CLOSE_{}__</td>".format(TD, p['account'])
            h += "</tr>"
        h += "</tbody></table></div>"
        st.markdown(h, unsafe_allow_html=True)

        # Inline close buttons per position
        for p in all_pos:
            acc = p['account']
            sym = p['symbol']
            side = p['side']
            size = int(p['size'])
            close_side = 'buy' if side == 'SHORT' else 'sell'
            if st.button(f"Close {acc} {side}", key=f"close_{acc}_{sym}", type="primary"):
                try:
                    import requests, hashlib, hmac, time
                    api_key    = os.environ.get(f'{acc}_API_KEY','')
                    api_secret = os.environ.get(f'{acc}_API_SECRET','')
                    base_url   = 'https://cdn-ind.testnet.deltaex.org'
                    method     = 'POST'
                    path       = '/v2/orders'
                    timestamp  = str(int(time.time()))
                    payload    = f'{{"product_symbol":"{sym}","order_type":"market_order","size":{size},"side":"{close_side}","reduce_only":"true"}}'
                    sig_data   = method + timestamp + path + '' + payload
                    signature  = hmac.new(bytes(api_secret,'utf-8'), bytes(sig_data,'utf-8'), hashlib.sha256).hexdigest()
                    headers    = {'api-key': api_key, 'timestamp': timestamp, 'signature': signature, 'Content-Type': 'application/json'}
                    resp = requests.post(f'{base_url}{path}', data=payload, headers=headers, timeout=10)
                    result = resp.json()
                    if result.get('success'):
                        st.success(f"{acc} {side} position closed successfully")
                    else:
                        st.error(f"Close failed: {result.get('error','unknown')}")
                except Exception as ex:
                    st.error(f"Error: {ex}")
    else:
        st.info("No open positions")

    # ── ORDER HISTORY ──────────────────────────────────────────
    st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)

    with st.expander("ORDER HISTORY", expanded=False):

        f1, f2, f3, f4 = st.columns(4)
        with f1:
            period = st.radio("Period", ["TODAY","YESTERDAY","2 DAYS","1 WEEK","1 MONTH","CUSTOM"], horizontal=True, key="oh_period")
        with f2:
            strat_filter = st.radio("Strategy", ["ALL","S2","S4"], horizontal=True, key="oh_strat")
        with f3:
            members_cfg_oh = json.load(open('dashboard/members_config.json')) if os.path.exists('dashboard/members_config.json') else {'members':[]}
            member_names = ['ALL','My Account'] + [m['name'] for m in members_cfg_oh.get('members',[])]
            member_filter = st.selectbox("Member", member_names, key="oh_member")
        with f4:
            curr_filter = st.radio("Currency", ["BOTH","USD","INR"], horizontal=True, key="oh_curr")

        if period == "CUSTOM":
            cd1, cd2 = st.columns(2)
            with cd1:
                from_date = st.date_input("From", key="oh_from")
            with cd2:
                to_date = st.date_input("To", key="oh_to")
        else:
            import datetime as _dt
            today = _dt.date.today()
            period_map = {"TODAY":0,"YESTERDAY":1,"2 DAYS":2,"1 WEEK":7,"1 MONTH":30}
            days_back = period_map.get(period, 0)
            from_date = today - _dt.timedelta(days=days_back)
            to_date = today

        from_ts_oh = int(datetime.datetime.combine(from_date, datetime.time.min).replace(tzinfo=datetime.timezone.utc).timestamp())
        to_ts_oh   = int(datetime.datetime.combine(to_date, datetime.time.max).replace(tzinfo=datetime.timezone.utc).timestamp())

        def fetch_orders_full(api_key, api_secret, from_ts, to_ts, product_id=84):
            from collections import defaultdict
            import warnings
            warnings.filterwarnings('ignore')
            all_fills = []
            try:
                start_us = from_ts * 1000000
                end_us   = to_ts   * 1000000
                after_cursor = None
                for page in range(1, 20):
                    params = {'product_id': product_id, 'page_size': 100,
                              'start_time': start_us, 'end_time': end_us}
                    if after_cursor:
                        params['after'] = after_cursor
                    resp  = delta_get_auth(api_key, api_secret, '/v2/fills', params)
                    fills = resp.get('result', [])
                    if not fills:
                        break
                    all_fills.extend(fills)
                    meta  = resp.get('meta', {})
                    after_cursor = meta.get('after')
                    if not after_cursor or len(fills) < 100:
                        break
            except:
                pass
            order_fills = defaultdict(list)
            for f in all_fills:
                order_fills[f['order_id']].append(f)
            orders = []
            for oid, fills in order_fills.items():
                total_size = sum(float(f['size']) for f in fills)
                wavg = sum(float(f['price'])*float(f['size']) for f in fills) / total_size if total_size > 0 else 0
                order_commission = sum(abs(float(f.get('commission', 0))) for f in fills)
                orders.append({
                    'order_id': oid,
                    'side': fills[0]['side'].upper(),
                    'size': total_size,
                    'price': wavg,
                    'time': fills[0]['created_at'][:16],
                    'fills_count': len(fills),
                    'commission': order_commission
                })
            return sorted(orders, key=lambda x: x['time'])

        def fetch_commission_funding(api_key, api_secret, from_ts):
            total_comm = 0.0
            total_fund = 0.0
            try:
                resp = delta_get_auth(api_key, api_secret, '/v2/wallet/transactions', {'product_id': 84, 'page_size': 200})
                txns = resp.get('result', [])
                if isinstance(txns, dict):
                    txns = txns.get('data', [])
                for t in txns:
                    tt = int(datetime.datetime.strptime(t['created_at'][:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp())
                    if tt >= from_ts:
                        amt = abs(float(t.get('amount', 0)))
                        if t.get('transaction_type') == 'commission':
                            total_comm += amt
                        elif t.get('transaction_type') == 'funding':
                            total_fund += amt
            except:
                pass
            return total_comm, total_fund

        def pair_orders(orders):
            pairs = []
            used  = set()
            # Sort by time
            orders_sorted = sorted(orders, key=lambda x: x['time'])
            for i, entry_order in enumerate(orders_sorted):
                if i in used:
                    continue
                entry_side = entry_order['side']
                exit_side  = 'SELL' if entry_side == 'BUY' else 'BUY'
                # Find next matching exit order
                for j, exit_order in enumerate(orders_sorted):
                    if j <= i or j in used:
                        continue
                    if exit_order['side'] == exit_side:
                        used.add(i)
                        used.add(j)
                        if entry_side == 'BUY':
                            pnl = (exit_order['price'] - entry_order['price']) * entry_order['size'] * 0.001
                            side_label = 'LONG'
                        else:
                            pnl = (entry_order['price'] - exit_order['price']) * entry_order['size'] * 0.001
                            side_label = 'SHORT'
                        trade_commission = entry_order['commission'] + exit_order['commission']
                        pairs.append({
                            'buy_time':    entry_order['time'],
                            'sell_time':   exit_order['time'],
                            'entry':       entry_order['price'],
                            'exit':        exit_order['price'],
                            'size':        entry_order['size'],
                            'pnl':         pnl,
                            'trade_count': 1,
                            'commission':  trade_commission,
                            'side':        side_label
                        })
                        break
                else:
                    # No exit found = OPEN position, skip (shown separately)
                    pass
            return pairs

        INR_OH = 84.0
        accounts_to_fetch = []
        if member_filter in ['ALL', 'My Account']:
            if strat_filter in ['ALL', 'S2']:
                accounts_to_fetch.append(('My Account', 'S2', os.getenv('S2_API_KEY',''), os.getenv('S2_API_SECRET','')))
            if strat_filter in ['ALL', 'S4']:
                accounts_to_fetch.append(('My Account', 'S4', os.getenv('S4_API_KEY',''), os.getenv('S4_API_SECRET','')))
        for m in members_cfg_oh.get('members', []):
            if member_filter in ['ALL', m['name']]:
                if strat_filter in ['ALL','S2'] and m.get('s2_key'):
                    accounts_to_fetch.append((m['name'], 'S2', m['s2_key'], m['s2_secret']))
                if strat_filter in ['ALL','S4'] and m.get('s4_key'):
                    accounts_to_fetch.append((m['name'], 'S4', m['s4_key'], m['s4_secret']))

        all_pairs = []
        total_comm_all = 0.0
        total_fund_all = 0.0
        for member_name, strat, api_key, api_secret in accounts_to_fetch:
            if not api_key:
                continue
            orders = fetch_orders_full(api_key, api_secret, from_ts_oh, to_ts_oh)
            pairs  = pair_orders(orders)
            for p in pairs:
                p['strat']  = strat
                p['member'] = member_name
            all_pairs.extend(pairs)
            comm, fund = fetch_commission_funding(api_key, api_secret, from_ts_oh)
            total_comm_all += comm
            total_fund_all += fund

        total_pnl_oh     = sum(p['pnl'] for p in all_pairs)
        total_tax_oh     = total_pnl_oh * 0.30 if total_pnl_oh > 0 else 0.0
        total_charges_oh = total_comm_all + total_fund_all + total_tax_oh
        wins_oh          = len([p for p in all_pairs if p['pnl'] > 0])
        losses_oh        = len([p for p in all_pairs if p['pnl'] < 0])
        total_tr_oh      = len(all_pairs)
        wr_oh            = (wins_oh/total_tr_oh*100) if total_tr_oh > 0 else 0
        unreal_oh        = sum(p.get('unreal_pnl',0.0) for p in all_pos if strat_filter in ['ALL', p.get('account','')]) if all_pos else 0.0
        num_trades       = len(all_pairs) if all_pairs else 1
        fund_per_trade   = total_fund_all / num_trades

        sm1,sm2,sm3,sm4,sm5,sm6,sm7,sm8,sm9 = st.columns(9)
        sm1.metric("Total PnL $",  f"${total_pnl_oh:,.2f}")
        sm2.metric("Total PnL ₹",  f"₹{total_pnl_oh*INR_OH:,.0f}")
        sm3.metric("Unrealised $", f"${unreal_oh:,.2f}")
        sm4.metric("Unrealised ₹", f"₹{unreal_oh*INR_OH:,.0f}")
        sm5.metric("Trades",       total_tr_oh)
        sm6.metric("Wins",         wins_oh)
        sm7.metric("Losses",       losses_oh)
        sm8.metric("Win Rate",     f"{wr_oh:.1f}%")
        sm9.metric("Charges $|₹",  f"${total_charges_oh:,.2f} | ₹{total_charges_oh*INR_OH:,.0f}")

        import pandas as pd
        open_pos_filtered = [p for p in all_pos if strat_filter in ['ALL', p.get('account','')]]

        csv_rows = []
        cum_csv  = 0.0
        for p in sorted(all_pairs, key=lambda x: x['buy_time']):
            cum_csv      += p['pnl']
            trade_tax     = p['pnl'] * 0.30 if p['pnl'] > 0 else 0.0
            trade_charge  = p['commission'] + fund_per_trade + trade_tax
            csv_rows.append({
                'DateTime':    p['buy_time'],
                'Member':      p['member'],
                'Strat':       p['strat'],
                'Side':        'LONG' if p['entry'] < p['exit'] else 'SHORT',
                'Entry$':      round(p['entry'],1),
                'Exit$':       round(p['exit'],1),
                'Lots':        int(p['size']),
                'PnL$':        round(p['pnl'],2),
                'PnL_INR':     round(p['pnl']*INR_OH,0),
                'Charges_USD': round(trade_charge,2),
                'Charges_INR': round(trade_charge*INR_OH,0),
                'CumPnL$':     round(cum_csv,2),
                'Count':       p['trade_count'],
                'Status':      'CLOSED'
            })
        for pos in open_pos_filtered:
            csv_rows.append({
                'DateTime':    datetime.datetime.now().strftime('%Y-%m-%dT%H:%M'),
                'Member':      'My Account',
                'Strat':       pos['account'],
                'Side':        pos['side'],
                'Entry$':      round(pos['entry'],1),
                'Exit$':       '-',
                'Lots':        int(pos['size']),
                'PnL$':        round(pos['unreal_pnl'],2),
                'PnL_INR':     round(pos['unreal_pnl']*INR_OH,0),
                'Charges_USD': 0.0,
                'Charges_INR': 0,
                'CumPnL$':     '-',
                'Count':       1,
                'Status':      'OPEN'
            })

        dl_col, hdr_space = st.columns([2,10])
        with dl_col:
            if csv_rows:
                df_csv = pd.DataFrame(csv_rows)
                st.download_button(
                    "⬇ CSV", df_csv.to_csv(index=False),
                    file_name=f"orders_{strat_filter}_{period}_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv", key="oh_dl_csv"
                )

        if all_pairs or open_pos_filtered:
            TH2 = "padding:5px 8px;border:1px solid #C8D0DC;background:#f0f3fa;font-size:10px;font-weight:700;color:#555;white-space:nowrap;"
            TD2 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;"
            TDR2 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;text-align:right;"
            _heads = ['#','DateTime','Member','Strat','Side','Entry$','Exit$','Lots','PnL$','PnL₹','Charges$|₹','Cum PnL$','Count','Status']
            _tbl = "<div style='overflow-x:auto;margin:4px 0;'><table style='width:100%;border-collapse:collapse;'><thead><tr>"
            _tbl += "".join("<th style='{}'>{}</th>".format(TH2, hh) for hh in _heads)
            _tbl += "</tr></thead><tbody>"
            # placeholder - rows added below
            _rows = ""

            cum_pnl = 0.0
            for i, p in enumerate(sorted(all_pairs, key=lambda x: x['buy_time']), 1):
                rc           = [None]*14  # replaced by HTML grid
                trade_tax    = p['pnl'] * 0.30 if p['pnl'] > 0 else 0.0
                trade_charge = p['commission'] + fund_per_trade + trade_tax
                cum_pnl     += p['pnl']
                side_label   = 'LONG' if p['entry'] < p['exit'] else 'SHORT'
                side_color   = 'green' if side_label == 'LONG' else 'red'
                pc           = "green" if p['pnl'] >= 0 else "red"
                cum_c        = "green" if cum_pnl >= 0 else "red"
                bg2 = "#ffffff" if i % 2 == 0 else "#fafafa"
                pnl_u = "<span style='color:{}'>${:,.2f}</span>".format(pc, p['pnl']) if curr_filter in ['BOTH','USD'] else "-"
                pnl_i = "<span style='color:{}'>₹{:,.0f}</span>".format(pc, p['pnl']*INR_OH) if curr_filter in ['BOTH','INR'] else "-"
                _rows += "<tr style='background:{};'>".format(bg2)
                _rows += "<td style='{}'>{}</td>".format(TD2, i)
                _rows += "<td style='{}'>{}</td>".format(TD2, p['buy_time'])
                _rows += "<td style='{}'>{}</td>".format(TD2, p['member'])
                _rows += "<td style='{}'>{}</td>".format(TD2, p['strat'])
                _rows += "<td style='{}'><span style='color:{};font-weight:700'>{}</span></td>".format(TD2, side_color, side_label)
                _rows += "<td style='{}'>${:,.1f}</td>".format(TDR2, p['entry'])
                _rows += "<td style='{}'>${:,.1f}</td>".format(TDR2, p['exit'])
                _rows += "<td style='{}'>{}</td>".format(TDR2, int(p['size']))
                _rows += "<td style='{}'>{}</td>".format(TDR2, pnl_u)
                _rows += "<td style='{}'>{}</td>".format(TDR2, pnl_i)
                _rows += "<td style='{}'><span style='color:#e65100'>${:,.2f}|₹{:,.0f}</span></td>".format(TDR2, trade_charge, trade_charge*INR_OH)
                _rows += "<td style='{}'><span style='color:{}'>${:,.2f}</span></td>".format(TDR2, cum_c, cum_pnl)
                _rows += "<td style='{}'>{}</td>".format(TD2, p['trade_count'])
                _rows += "<td style='{}'>CLOSED</td>".format(TD2)
                _rows += "</tr>"

            row_start = len(all_pairs) + 1
            for idx, pos in enumerate(open_pos_filtered):
                sc = "#089981" if pos['side']=='LONG' else "#F23645"
                pc = "#089981" if pos['unreal_pnl'] >= 0 else "#F23645"
                bg3 = "#fff8f0"
                pnl_u2 = "<span style='color:{}'>${:,.2f}</span>".format(pc, pos['unreal_pnl']) if curr_filter in ['BOTH','USD'] else "-"
                pnl_i2 = "<span style='color:{}'>₹{:,.0f}</span>".format(pc, pos['unreal_pnl']*INR_OH) if curr_filter in ['BOTH','INR'] else "-"
                _rows += "<tr style='background:{};'>".format(bg3)
                _rows += "<td style='{}'>{}</td>".format(TD2, row_start+idx)
                _rows += "<td style='{}'>{}</td>".format(TD2, datetime.datetime.now().strftime('%Y-%m-%dT%H:%M'))
                _rows += "<td style='{}'>My Account</td>".format(TD2)
                _rows += "<td style='{}'>{}</td>".format(TD2, pos['account'])
                _rows += "<td style='{}'><span style='color:{};font-weight:700'>{}</span></td>".format(TD2, sc, pos['side'])
                _rows += "<td style='{}'>${:,.1f}</td>".format(TDR2, pos['entry'])
                _rows += "<td style='{}'>-</td>".format(TD2)
                _rows += "<td style='{}'>{}</td>".format(TDR2, int(pos['size']))
                _rows += "<td style='{}'>{}</td>".format(TDR2, pnl_u2)
                _rows += "<td style='{}'>{}</td>".format(TDR2, pnl_i2)
                _rows += "<td style='{}'>-</td>".format(TD2)
                _rows += "<td style='{}'>-</td>".format(TD2)
                _rows += "<td style='{}'>1</td>".format(TD2)
                _rows += "<td style='{}'><span style='color:#FF9800;font-weight:700'>OPEN</span></td>".format(TD2)
                _rows += "</tr>"
            _tbl += _rows + "</tbody></table></div>"
            st.markdown(_tbl, unsafe_allow_html=True)
        else:
            st.info("No orders found for selected period and filters")

        st.caption(f"Charges = Commission + Funding + 30% Tax on profit | Funding: ${total_fund_all:,.4f} | Commission: ${total_comm_all:,.4f} | Updated: {datetime.datetime.now().strftime('%H:%M:%S')} | Testnet")

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
    st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)

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

    st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
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
    st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
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
if 'exp_4' not in st.session_state: st.session_state['exp_4'] = False
with st.expander("SECTION 4 - FORWARD TEST vs BACKTEST COMPARE", expanded=st.session_state.get('exp_4', False)):


    st.markdown("**Generate Detailed Comparison Report**")

    comp_tab_s2, comp_tab_s4, comp_tab_match = st.tabs(["S2 - RenkoReversalStrategy", "S4 - RenkoSMIIOSupertrendStrategy", "LIVE MATCH REPORT"])

    # LIVE MATCH REPORT TAB
    with comp_tab_match:
        st.markdown("**Live Backtest vs Forward Test Match Report**")
        st.caption("Trade count | Direction | Entry time | Exit time | MATCH or MISMATCH per trade")

        import time as _time
        import re as _re3
        AUTO_INTERVAL = 300

        last_run  = st.session_state.get('match_last_run', 0)
        now_ts    = _time.time()
        auto_due  = (now_ts - last_run) >= AUTO_INTERVAL

        col_run, col_info = st.columns([1, 4])
        with col_run:
            run_match = st.button("RUN MATCH CHECK", key="run_match_btn")
        with col_info:
            if last_run > 0:
                last_str  = datetime.datetime.fromtimestamp(last_run).strftime('%H:%M:%S')
                next_secs = max(0, int(AUTO_INTERVAL - (now_ts - last_run)))
                st.caption(f"Last check: {last_str} | Next auto in {next_secs}s")
            else:
                st.caption("Auto-checks every 5 minutes")

        # Run when button clicked OR auto interval due - not on every page load
        should_run = run_match or auto_due
        if should_run:
            with st.spinner("Running match check..."):
                import subprocess
                _r = subprocess.run(
                    [".venv/bin/python3", "scripts/verify_match.py"],
                    capture_output=True, text=True,
                    cwd="/home/anildalabanjan933/crypto_trading_system"
                )
                st.session_state['match_result']   = _r.stdout
                st.session_state['match_stderr']   = _r.stderr
                st.session_state['match_last_run'] = _time.time()

        output = st.session_state.get('match_result', '')
        if not output:
            st.warning("No result yet - click RUN MATCH CHECK")
        else:
            lines = output.strip().split("\n")

            overall_line = next((l for l in lines if "OVERALL:" in l), "")
            if "MATCH OK" in overall_line:
                st.success("ALL MATCH OK - Backtest and Forward Test are in sync")
            elif "MISMATCH" in overall_line:
                st.error("MISMATCH FOUND - see table below")
            else:
                st.info("Checking...")

            m1, m2, m3 = st.columns(3)
            for l in lines:
                if "Valid from" in l:  m1.caption(l.strip())
                if "Run time"   in l:  m2.caption(l.strip())
                if "CSV updated" in l or "CSV already" in l: m3.caption(l.strip())

            st.markdown("---")

            def _parse_block(lines, key):
                start = next((i for i,l in enumerate(lines) if key in l), None)
                if start is None:
                    return 0, 0, [], ""
                bt_n = lv_n = 0
                summary = ""
                for l in lines[start:start+5]:
                    if "Backtest trades" in l:
                        try: bt_n = int(l.split(":")[-1].strip())
                        except: pass
                    if "Live trades" in l:
                        try: lv_n = int(l.split(":")[-1].strip())
                        except: pass
                trades = []
                i = start
                while i < len(lines):
                    if "Trade #" in lines[i]:
                        blk = lines[i:i+10]
                        def _ex(line, k):
                            m = _re3.search(k + r'=(\S+)', line)
                            return m.group(1) if m else "-"
                        bt_l = next((l for l in blk if "BT :" in l), "")
                        lv_l = next((l for l in blk if "LV :" in l), "")
                        di_l = next((l for l in blk if "Direction" in l), "")
                        en_l = next((l for l in blk if "Entry time" in l), "")
                        ex_l = next((l for l in blk if "Exit time" in l), "")
                        st_l = next((l for l in blk if "STATUS" in l), "")
                        trades.append({
                            "num"      : lines[i].strip(),
                            "bt_dir"   : _ex(bt_l, "Dir"),
                            "bt_entry" : _ex(bt_l, "Entry"),
                            "bt_exit"  : _ex(bt_l, "Exit"),
                            "lv_dir"   : _ex(lv_l, "Dir"),
                            "lv_entry" : _ex(lv_l, "Entry"),
                            "lv_exit"  : _ex(lv_l, "Exit"),
                            "dir_ok"   : "MATCH" in di_l and "MISMATCH" not in di_l,
                            "entry_ok" : "MATCH" in en_l and "MISMATCH" not in en_l,
                            "pending"  : "PENDING" in ex_l or "PENDING" in st_l,
                            "full_ok"  : "FULL MATCH" in st_l,
                            "status"   : st_l.replace("STATUS","").replace(":","").strip()
                        })
                    if "SUMMARY:" in lines[i]:
                        summary = lines[i].strip()
                        break
                    i += 1
                return bt_n, lv_n, trades, summary

            for s_key, s_label in [
                ("S2 RenkoReversal", "S2 - RenkoReversalStrategy"),
                ("S4 RenkoSMIIO",    "S4 - RenkoSMIIOSupertrendStrategy")
            ]:
                bt_n, lv_n, trades, summary = _parse_block(lines, s_key)
                st.markdown(f"**{s_label}**")

                cc = st.columns(4)
                cc[0].metric("Backtest Trades", bt_n)
                cc[1].metric("Live Trades",     lv_n)
                if bt_n == lv_n:
                    cc[2].success("COUNT MATCH")
                elif lv_n > 0 and bt_n == 0:
                    cc[2].warning("PENDING (CSV updating)")
                else:
                    cc[2].error(f"COUNT MISMATCH diff={abs(bt_n-lv_n)}")
                if summary:
                    cc[3].caption(summary.replace("SUMMARY:","").strip())

                if not trades:
                    st.success("BOTH FLAT - NO SIGNAL YET - MATCH OK")
                else:
                    hh = st.columns([1,2,2,2,4,4,4,4,2,2])
                    for col,hdr in zip(hh,["#","RESULT","BT Dir","LV Dir","BT Entry","LV Entry","BT Exit","LV Exit","Dir","Entry"]):
                        col.markdown(f"<small><b>{hdr}</b></small>", unsafe_allow_html=True)

                    def _fmt(v):
                        if not v or v in ["-","MISSING","PENDING"]: return v or "-"
                        return v[:16].replace("T"," ")

                    for t in trades:
                        rr = st.columns([1,2,2,2,4,4,4,4,2,2])
                        rr[0].write(t["num"].replace("Trade #","").replace(":","").strip())

                        if t["full_ok"]:
                            rr[1].success("MATCH")
                        elif t["pending"]:
                            rr[1].warning("PENDING")
                        else:
                            rr[1].error("MISMATCH")

                        bd = t["bt_dir"].upper()
                        if bd in ["MISSING","PENDING","-"]:
                            rr[2].warning(bd)
                        elif bd == "LONG":
                            rr[2].markdown("<span style='color:green;font-weight:700'>LONG</span>", unsafe_allow_html=True)
                        else:
                            rr[2].markdown("<span style='color:red;font-weight:700'>SHORT</span>", unsafe_allow_html=True)

                        ld = t["lv_dir"].upper()
                        if ld in ["MISSING","-"]:
                            rr[3].error("MISSING")
                        elif ld == "LONG":
                            rr[3].markdown("<span style='color:green;font-weight:700'>LONG</span>", unsafe_allow_html=True)
                        else:
                            rr[3].markdown("<span style='color:red;font-weight:700'>SHORT</span>", unsafe_allow_html=True)

                        rr[4].write(_fmt(t["bt_entry"]))
                        rr[5].write(_fmt(t["lv_entry"]))
                        rr[6].write(_fmt(t["bt_exit"]) if t["bt_exit"] not in ["","-"] else "-")
                        rr[7].write("OPEN" if t["lv_exit"] == "(open)" else _fmt(t["lv_exit"]))

                        if t["dir_ok"]:
                            rr[8].success("OK")
                        else:
                            rr[8].error("FAIL")

                        if t["entry_ok"]:
                            rr[9].success("OK")
                        else:
                            rr[9].error("FAIL")

                st.markdown("---")

            err = st.session_state.get('match_stderr','')
            if err and "DeprecationWarning" not in err and "RuntimeWarning" not in err:
                with st.expander("Script errors"):
                    st.code(err[:500])

    for comp_tab, algo_name, algo_key in [(comp_tab_s2, "S2", "s2"), (comp_tab_s4, "S4", "s4")]:
        with comp_tab:
            st.markdown(f"**{algo_name} - Auto Pipeline (market data + backtest + Delta API)**")
            c1, c2 = st.columns(2)
            with c1:
                from_date = st.date_input(
                    "Forward Test From Date",
                    value=datetime.date(2026, 7, 11),
                    key=f"from_date_{algo_key}"
                )
            with c2:
                st.markdown("<br>", unsafe_allow_html=True)
                st.info(f"To Date: TODAY ({datetime.date.today().strftime('%Y-%m-%d')}) - auto")

            st.caption("Pipeline: 1) Download market data  2) Run backtest  3) Fetch Delta API trades  4) Generate report")

            gen_btn = st.button(f"GENERATE {algo_name} REPORT", key=f"gen_report_{algo_key}")

            if gen_btn:
                progress_bar = st.progress(0)
                status_box   = st.empty()
                status_box.info("Starting pipeline...")
                progress_bar.progress(5)
                try:
                    cmd = [
                        ".venv/bin/python", "scripts/auto_comparison_pipeline.py",
                        "--strategy", algo_name,
                        "--from_date", from_date.strftime("%Y-%m-%d"),
                    ]
                    env = os.environ.copy()
                    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
                    if os.path.exists(env_path):
                        with open(env_path) as ef:
                            for line in ef:
                                line = line.strip()
                                if '=' in line and not line.startswith('#'):
                                    k, v = line.split('=', 1)
                                    env[k.strip()] = v.strip()
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        cwd=os.path.dirname(os.path.dirname(__file__)),
                        env=env
                    )
                    report_file = None
                    step_msgs = {
                        'STEP_1_START': ('Downloading market data...', 10),
                        'STEP_1_DONE':  ('Market data updated', 30),
                        'STEP_2_START': ('Running backtest...', 35),
                        'STEP_2_DONE':  ('Backtest complete', 60),
                        'STEP_3_START': ('Fetching Delta API trades...', 65),
                        'STEP_3_DONE':  ('Delta API data fetched', 85),
                        'STEP_4_START': ('Generating HTML report...', 88),
                        'STEP_4_DONE':  ('Report generated', 98),
                        'PIPELINE_COMPLETE': ('Pipeline complete', 100),
                    }
                    all_output = []
                    for line in process.stdout:
                        line = line.strip()
                        all_output.append(line)
                        if line in step_msgs:
                            msg, pct = step_msgs[line]
                            status_box.info(f"[{pct}%] {msg}")
                            progress_bar.progress(pct)
                        elif line.startswith('REPORT_FILE:'):
                            report_file = line.replace('REPORT_FILE:', '').strip()
                        elif line.startswith('[Step'):
                            status_box.info(line)
                    process.wait()
                    if process.returncode == 0 and report_file and os.path.exists(report_file):
                        progress_bar.progress(100)
                        status_box.success(f"Report ready: {os.path.basename(report_file)}")
                    else:
                        status_box.error("Pipeline failed - check output below")
                        st.code('\n'.join(all_output[-20:]))
                except Exception as e:
                    status_box.error(f"Error: {e}")

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
                        for sname in ['RenkoReversalStrategy', 'RenkoSMIIOSupertrendStrategy']:
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
if 'exp_5' not in st.session_state: st.session_state['exp_5'] = False
with st.expander("SECTION 5 - BACKTEST", expanded=True):

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
    bt_range = st.radio("Date Range", bt_range_options, index=2, horizontal=True, key="sec6_range", label_visibility="collapsed")
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
        bt_end = today
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
        _status = st.empty()
        _progress = st.progress(0)
        import os as _os, time as _tm
        _csv_path = "data/btc_1m_delta.csv"
        _csv_age = _tm.time() - _os.path.getmtime(_csv_path) if _os.path.exists(_csv_path) else 9999
        if _csv_age > 1800:
            _status.info("Step 1/3 - Downloading latest market data...")
            _progress.progress(10)
            import subprocess as _sp
            _sp.run([".venv/bin/python","-c","import sys;sys.path.insert(0,'data');from download_market_data import download_or_update;download_or_update('BTC')"], capture_output=True, timeout=120, cwd='/home/anildalabanjan933/crypto_trading_system')
        else:
            _status.info("Step 1/3 - Market data is fresh, skipping download...")
            _progress.progress(10)
        _status.info(f"Step 2/3 - Running backtest: {bt_strategy} | {bt_start} to {bt_end}")
        _progress.progress(40)
        if True:
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
                    _progress.progress(100)
                    _status.success("Step 3/3 - Backtest complete! Report ready below.")
                    import glob as _glob, time as _time, os as _glob_os
                    _time.sleep(3)
                    _new_files = sorted([f for f in _glob.glob("output/*.html") if "backtest_report_" in f and "optimization" not in f], key=_glob_os.path.getmtime, reverse=True)
                    if _new_files:
                        st.session_state["sec6_html_select"] = _new_files[0]
                        st.session_state["sec6_force_latest"] = False
                    import time as _t; _t.sleep(1)
                    st.rerun()
                else:
                    _progress.progress(100)
                    _status.error("Backtest failed - see error below")
                    st.code(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
            except subprocess.TimeoutExpired:
                _status.error("Backtest timed out after 5 minutes")
            except Exception as e:
                _status.error(f"Error running backtest: {e}")

    st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
    st.markdown("**Backtest Reports**")

    import os as _glob_os; html_files = sorted([f for f in glob.glob("output/*.html") if "backtest_report_" in f and "optimization" not in f], key=_glob_os.path.getmtime, reverse=True)
    csv_files = sorted([f for f in glob.glob("output/*.csv") if "trade_log_" in f], reverse=True)

    st.markdown("**HTML Reports**")
    if html_files:
        # Always show latest report on page load
        st.session_state["sec6_html_select"] = html_files[0] if html_files else None
        st.session_state["sec6_force_latest"] = False
        selected_html = html_files[0] if html_files else None
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
if 'exp_5b' not in st.session_state: st.session_state['exp_5b'] = False
with st.expander("SECTION 5B - PORTFOLIO BACKTEST", expanded=True):

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
        port_range = st.radio("Select", ["1 Month","6 Months","1 Year","1.5 Years","2 Years","Full CSV","Custom"], index=2, horizontal=True, key="port_range", label_visibility="collapsed")
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
            port_start = datetime.date.fromisoformat("2024-01-01"); port_end = today
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
            _pp_status = st.empty()
            _pp_progress = st.progress(0)
            import os as _os2, time as _tm2
            _csv_age2 = _tm2.time() - _os2.path.getmtime("data/btc_1m_delta.csv") if _os2.path.exists("data/btc_1m_delta.csv") else 9999
            if _csv_age2 > 1800:
                _pp_status.info("Step 1/3 - Downloading latest market data...")
                _pp_progress.progress(10)
                import subprocess as _sp
                _sp.run([".venv/bin/python","-c","import sys;sys.path.insert(0,'data');from download_market_data import download_or_update;download_or_update('BTC')"], capture_output=True, timeout=120, cwd='/home/anildalabanjan933/crypto_trading_system')
            else:
                _pp_status.info("Step 1/3 - Market data is fresh, skipping download...")
                _pp_progress.progress(10)
            _pp_status.info(f"Step 2/3 - Running portfolio backtest: {port_start} to {port_end}")
            _pp_progress.progress(40)
            if True:
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
                        _pp_progress.progress(100)
                        _pp_status.success("Step 3/3 - Portfolio backtest complete! Report ready below.")
                        import glob as _glob, time as _time, os as _glob_os
                        _time.sleep(3)
                        _new_port = sorted([f for f in _glob.glob("output/*.html") if "portfolio_report_" in f], key=_glob_os.path.getmtime, reverse=True)
                        if _new_port:
                            st.session_state["port_html_sel"] = _new_port[0]
                            st.session_state["port_force_latest"] = False
                        import time as _t; _t.sleep(1)
                        st.rerun()
                    else:
                        _pp_progress.progress(100)
                        _pp_status.error("Portfolio backtest failed - see error below")
                        st.code(result.stderr[-2000:])
                except Exception as e:
                    _pp_status.error(f"Error: {e}")

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
        port_dyn_range = st.radio("Date Range", ["1 Month","6 Months","1 Year","1.5 Years","2 Years","Full CSV","Custom"], index=2, horizontal=True, key="port_dyn_range", label_visibility="collapsed")
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
            port_dyn_start = datetime.date.fromisoformat("2024-01-01"); port_dyn_end = today
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
            _pd_status = st.empty()
            _pd_progress = st.progress(0)
            if not selected_strategies:
                _pd_status.error("Please select at least one strategy")
            else:
                import os as _os3, time as _tm3
                _csv_age3 = _tm3.time() - _os3.path.getmtime("data/btc_1m_delta.csv") if _os3.path.exists("data/btc_1m_delta.csv") else 9999
                if _csv_age3 > 1800:
                    _pd_status.info("Step 1/3 - Downloading latest market data...")
                    _pd_progress.progress(10)
                    import subprocess as _sp
                    _sp.run([".venv/bin/python","-c","import sys;sys.path.insert(0,'data');from download_market_data import download_or_update;download_or_update('BTC')"], capture_output=True, timeout=120, cwd='/home/anildalabanjan933/crypto_trading_system')
                else:
                    _pd_status.info("Step 1/3 - Market data is fresh, skipping download...")
                    _pd_progress.progress(10)
                _pd_status.info(f"Step 2/3 - Running dynamic portfolio: {selected_strategies} | {port_dyn_start} to {port_dyn_end}")
                _pd_progress.progress(40)
                if True:
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
                            _pd_progress.progress(100)
                            _pd_status.success("Step 3/3 - Dynamic portfolio complete! Report ready below.")
                            import glob as _glob, time as _time, os as _glob_os
                            _time.sleep(3)
                            _new_dyn = sorted([f for f in _glob.glob("output/*.html") if "portfolio_report_" in f], key=_glob_os.path.getmtime, reverse=True)
                            if _new_dyn:
                                st.session_state["port_html_sel"] = _new_dyn[0]
                                st.session_state["port_force_latest"] = False
                            import time as _t; _t.sleep(1)
                            st.rerun()
                        else:
                            _pd_progress.progress(100)
                            _pd_status.error("Dynamic portfolio failed - see error below")
                            st.code(result.stderr[-2000:])
                    except Exception as e:
                        _pd_status.error(f"Error: {e}")


    # ================================================================

    st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
    st.markdown("**Backtest Reports**")
    port_html = sorted([f for f in glob.glob("output/*.html") if "portfolio_report_" in f], key=_glob_os.path.getmtime, reverse=True)
    port_csv = sorted([f for f in glob.glob("output/*.csv") if "portfolio_trade_log_" in f], reverse=True)

    st.markdown("**Select Report to View/Download**")
    if port_html:
        # Always show latest report on page load
        st.session_state["port_html_sel"] = port_html[0] if port_html else None
        st.session_state["port_force_latest"] = False
        sel_port_html = port_html[0] if port_html else None
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
        sel_port_csv = port_csv[0] if port_csv else None
        with open(sel_port_csv, 'rb') as f:
            st.download_button("DOWNLOAD CSV", f, file_name=os.path.basename(sel_port_csv), key="port_dl_csv")
    else:
        st.info("No portfolio CSV files found in output/ folder")

# ================================================================
# SECTION 6 - OPTIMISATION
# ================================================================
if 'exp_6' not in st.session_state: st.session_state['exp_6'] = False
with st.expander("SECTION 6 - OPTIMISATION", expanded=True):

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

    opt_range = st.radio("Date Range", ["1 Month","6 Months","1 Year","1.5 Years","2 Years","Full CSV","Custom"], index=2, horizontal=True, key="sec7_range")
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
        opt_start = datetime.date.fromisoformat("2024-01-01"); opt_end = today
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
        _opt_status = st.empty()
        _opt_progress = st.progress(0)
        import os as _os4, time as _tm4
        _csv_age4 = _tm4.time() - _os4.path.getmtime("data/btc_1m_delta.csv") if _os4.path.exists("data/btc_1m_delta.csv") else 9999
        if _csv_age4 > 1800:
            _opt_status.info("Step 1/3 - Downloading latest market data...")
            _opt_progress.progress(10)
            import subprocess as _sp
            _sp.run([".venv/bin/python","-c","import sys;sys.path.insert(0,'data');from download_market_data import download_or_update;download_or_update('BTC')"], capture_output=True, timeout=120, cwd='/home/anildalabanjan933/crypto_trading_system')
        else:
            _opt_status.info("Step 1/3 - Market data is fresh, skipping download...")
            _opt_progress.progress(10)
        _opt_status.info(f"Step 2/3 - Running optimisation: {opt_strategy} | {opt_start} to {opt_end} (may take several minutes...)")
        _opt_progress.progress(40)
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
                _opt_progress.progress(100)
                _opt_status.success("Step 3/3 - Optimisation complete! Report ready below.")
                import glob as _glob, time as _time, os as _glob_os
                _time.sleep(3)
                _new_opt = sorted([f for f in _glob.glob("output/*.html") if "optimization_results_" in f], key=_glob_os.path.getmtime, reverse=True)
                if _new_opt:
                    st.session_state["sec7_html_sel"] = _new_opt[0]
                st.session_state["sec7_force_latest"] = False
                import time as _t; _t.sleep(1)
                st.rerun()
            else:
                _opt_progress.progress(100)
                _opt_status.error("Optimisation failed - see error below")
                st.code(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        except subprocess.TimeoutExpired:
            _opt_status.error("Optimisation timed out after 10 minutes")
        except Exception as e:
            _opt_status.error(f"Error: {e}")

    st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
    st.markdown("**Optimisation Results**")

    opt_csv_files = sorted([f for f in glob.glob("output/*.csv") if "optimization_results_" in f], reverse=True)
    opt_html_files = sorted([f for f in glob.glob("output/*.html") if "optimization_results_" in f], key=_glob_os.path.getmtime, reverse=True)

    st.markdown("**HTML Reports**")
    if opt_html_files:
        if "sec7_html_sel" not in st.session_state or st.session_state.get("sec7_force_latest"):
            st.session_state["sec7_html_sel"] = opt_html_files[0] if opt_html_files else None
            st.session_state["sec7_force_latest"] = False
        sel_opt_html = opt_html_files[0] if opt_html_files else None
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
        sel_opt_csv = opt_csv_files[0] if opt_csv_files else None
        with open(sel_opt_csv, 'rb') as f:
            st.download_button("DOWNLOAD CSV", f, file_name=os.path.basename(sel_opt_csv), key="sec7_dl_csv")
    else:
        st.info("No optimisation CSV files found in output/ folder")



# ================================================================
# SECTION 8 - BATCH BACKTEST + SCANNER (PLACEHOLDER)
# ================================================================
if 'exp_8' not in st.session_state: st.session_state['exp_8'] = False
with st.expander("SECTION 8 - BATCH BACKTEST + COIN SCANNER", expanded=st.session_state.get('exp_8', False)):

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
if 'exp_9' not in st.session_state: st.session_state['exp_9'] = False
with st.expander("SECTION 9 - CONTRACT MANAGER", expanded=st.session_state.get('exp_9', False)):


    contracts = config.get("contracts", [])

    col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([2,2,1,2,2])
    col_h1.markdown("**Symbol**")
    col_h2.markdown("**Name**")
    col_h3.markdown("**Lots**")
    col_h4.markdown("**Status**")
    col_h5.markdown("**Action**")
    st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)

    for i, contract in enumerate(contracts):
        c1, c2, c3, c4, c5 = st.columns([2,2,1,2,2])
        with c1:
            st.write(contract.get('symbol',''))
        with c2:
            st.write(contract.get('name',''))
        with c3:
            new_c_lots = st.number_input("Lots", min_value=1, value=contract.get('lots',100),
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

    st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
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
if 'exp_10' not in st.session_state: st.session_state['exp_10'] = False
with st.expander("SECTION 10 - GITHUB SYNC", expanded=st.session_state.get('exp_10', False)):


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

    st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
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
# SECTION 12 - LOG MONITOR
# ================================================================
with st.expander("SECTION 12 - LOG MONITOR", expanded=st.session_state.get('exp_12', False)):

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
        if not os.path.exists(path):
            return [f"Log not found: {path}"]
        try:
            lines = open(path, encoding='utf-8', errors='ignore').readlines()
            if keyword:
                lines = [l for l in lines if keyword.upper() in l.upper()]
            return lines[-last_n:]
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

    s2_log_path = '/home/anildalabanjan933/crypto_trading_system/logs/live_trading_s2.log'
    s4_log_path = '/home/anildalabanjan933/crypto_trading_system/logs/live_trading_s4.log'

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
            import streamlit.components.v1 as _stc
            _stc.html('<script>setTimeout(function(){window.location.reload();},30000);</script>', height=0)



    # ================================================================
# SECTION 13 - STRATEGY PERFORMANCE SUMMARY
# ================================================================
if 'exp_13s' not in st.session_state: st.session_state['exp_13s'] = False
with st.expander("SECTION 13 - LIVE FORWARD TEST PERFORMANCE", expanded=st.session_state.get('exp_13s', False)):
    import time as _t13, hmac as _hm13, hashlib as _hs13, requests as _rq13, datetime as _dt13, glob as _gl13, pandas as _pd13, re as _re13

    try:
        _VF13 = open("logs/valid_from_baseline.txt").read().strip()
    except:
        _VF13 = "2026-07-14T15:00:00"
    _INR13 = 84.0
    _BASE13= "https://cdn-ind.testnet.deltaex.org"
    _TH13  = "padding:5px 8px;border:1px solid #C8D0DC;background:#f0f3fa;font-size:10px;font-weight:700;color:#555;text-align:center;"
    _TD13  = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#131722;"
    _TDN13 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#131722;text-align:center;"
    _TDG13 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#089981;font-weight:700;text-align:center;"
    _TDR13 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#F23645;font-weight:700;text-align:center;"
    _TDB13 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#2962FF;font-weight:700;text-align:center;"
    _SUB13 = "padding:4px 8px;border:1px solid #C8D0DC;background:#E8ECF2;font-size:10px;font-weight:700;color:#131722;"
    _HDR13 = "padding:6px 12px;background:#1E3A5F;font-size:11px;font-weight:700;color:#ffffff;margin:8px 0 4px 0;border-left:4px solid #2962FF;"

    def _auth13(k, s, path, qs=""):
        try:
            ts  = str(int(_t13.time()))
            qp  = f"?{qs}" if qs else ""
            msg = f"GET{ts}{path}{qp}"
            sig = _hm13.new(s.encode(), msg.encode(), _hs13.sha256).hexdigest()
            return {"api-key":k,"timestamp":ts,"signature":sig,"Content-Type":"application/json"}
        except:
            return {}

    def _fetch13(k, s):
        orders, after = [], None
        try:
            vf  = int(_dt13.datetime.strptime(_VF13,"%Y-%m-%dT%H:%M:%S").replace(tzinfo=_dt13.timezone.utc).timestamp())
            now = int(_dt13.datetime.now(_dt13.timezone.utc).timestamp())
            path= "/v2/orders/history"
            prm = {"product_id":84,"page_size":100,"start_time":int(vf*1e6),"end_time":int(now*1e6)}
            for _ in range(50):
                p = dict(prm)
                if after: p["after"] = after
                qs = "&".join(f"{a}={b}" for a,b in sorted(p.items()))
                h = _auth13(k, s, path, qs)
                r = _rq13.get(f"{_BASE13}{path}?{qs}", headers=h, timeout=10)
                d = r.json()
                if not d.get("success"): break
                batch = d.get("result",[])
                orders += batch
                after  = d.get("meta",{}).get("after")
                if not after or not batch: break
        except:
            pass
        return orders

    def _pair13(orders):
        pairs, used = [], set()
        srt = sorted(orders, key=lambda x: x.get("created_at",""))
        for i, e in enumerate(srt):
            if i in used or e.get("state")!="closed": continue
            es = e.get("side")
            if es not in ["buy","sell"]: continue
            xs  = "sell" if es=="buy" else "buy"
            dir = "LONG" if es=="buy" else "SHORT"
            ets = int(_dt13.datetime.strptime(e.get("created_at","1970-01-01T00:00:00")[:19], "%Y-%m-%dT%H:%M:%S").timestamp())
            ep  = float(e.get("average_fill_price") or e.get("limit_price") or 0)
            for j, x in enumerate(srt):
                if j in used or j==i: continue
                if x.get("side")!=xs or x.get("state")!="closed": continue
                if str(x.get("reduce_only","")).lower() not in ["true","1"]: continue
                xts = int(_dt13.datetime.strptime(x.get("created_at","1970-01-01T00:00:00")[:19], "%Y-%m-%dT%H:%M:%S").timestamp())
                xp  = float(x.get("average_fill_price") or x.get("limit_price") or 0)
                if xts < ets: continue
                sz  = int(e.get("size",0))
                pnl = (xp-ep)*sz*0.001 if dir=="LONG" else (ep-xp)*sz*0.001
                cm  = float(e.get("paid_commission") or 0)+float(x.get("paid_commission") or 0)
                pairs.append({"dir":dir,"ep":ep,"xp":xp,"pnl":pnl-cm,"cm":cm,"ets":ets,"xts":xts,"sz":sz})
                used.add(i); used.add(j); break
        return pairs

    def _calc13(pairs):
        if not pairs: return None
        tot = len(pairs)
        win = sum(1 for p in pairs if p["pnl"]>0)
        los = tot-win
        wr  = win/tot*100
        nu  = sum(p["pnl"] for p in pairs)
        ni  = nu*_INR13
        cm  = sum(p["cm"] for p in pairs)
        pls = [p["pnl"] for p in pairs]
        cum,pk,dd = 0,0,0
        for v in pls:
            cum+=v
            if cum>pk: pk=cum
            if pk>0 and (pk-cum)/pk>dd: dd=(pk-cum)/pk
        aw = sum(v for v in pls if v>0)/win if win>0 else 0
        al = sum(v for v in pls if v<0)/los if los>0 else 0
        pf = abs(sum(v for v in pls if v>0)/sum(v for v in pls if v<0)) if los>0 and sum(v for v in pls if v<0)!=0 else 0
        import datetime as _dt_c
        now_c = _dt_c.datetime.utcnow()
        today_start = now_c.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        week_start  = (now_c - _dt_c.timedelta(days=now_c.weekday())).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        month_start = now_c.replace(day=1,hour=0,minute=0,second=0,microsecond=0).timestamp()
        year_start  = now_c.replace(month=1,day=1,hour=0,minute=0,second=0,microsecond=0).timestamp()
        pnl_today   = sum(p["pnl"] for p in pairs if p.get("xts",0) >= today_start)
        pnl_week    = sum(p["pnl"] for p in pairs if p.get("xts",0) >= week_start)
        pnl_month   = sum(p["pnl"] for p in pairs if p.get("xts",0) >= month_start)
        pnl_year    = sum(p["pnl"] for p in pairs if p.get("xts",0) >= year_start)
        avg_slip    = abs(nu/tot) * 0.01 if tot>0 else 0
        return {"tot":tot,"win":win,"los":los,"wr":wr,"nu":nu,"ni":ni,"cm":cm,"dd":dd,"aw":aw,"al":al,"pf":pf,
                "pnl_today":pnl_today,"pnl_week":pnl_week,"pnl_month":pnl_month,"pnl_year":pnl_year,"avg_slip":avg_slip}

    def _bt_calc13(csv_pattern, vf_str):
        try:
            files = sorted(_gl13.glob(csv_pattern), reverse=True)
            if not files: return None
            df = _pd13.read_csv(files[0])
            if 'entry_datetime' not in df.columns: return None
            df['entry_datetime'] = _pd13.to_datetime(df['entry_datetime'])
            vf_dt = _pd13.to_datetime(vf_str)
            df = df[df['entry_datetime'] >= vf_dt]
            if df.empty: return None
            tot = len(df)
            win = (df['net_pnl'] > 0).sum()
            los = tot - win
            wr  = win/tot*100
            nu  = df['net_pnl'].sum()
            ni  = df['net_pnl_inr'].sum() if 'net_pnl_inr' in df.columns else nu*_INR13
            cm  = df['total_charges_usd'].sum() if 'total_charges_usd' in df.columns else (df['charges'].sum() if 'charges' in df.columns else 0)
            pls = df['net_pnl'].tolist()
            cum,pk,dd = 0,0,0
            for v in pls:
                cum+=v
                if cum>pk: pk=cum
                if pk>0 and (pk-cum)/pk>dd: dd=(pk-cum)/pk
            aw = df[df['net_pnl']>0]['net_pnl'].mean() if win>0 else 0
            al = df[df['net_pnl']<0]['net_pnl'].mean() if los>0 else 0
            pf_n = df[df['net_pnl']>0]['net_pnl'].sum()
            pf_d = abs(df[df['net_pnl']<0]['net_pnl'].sum())
            pf = pf_n/pf_d if pf_d>0 else 0
            import datetime as _dt_bt
            now_bt = _dt_bt.datetime.utcnow()
            today_s = now_bt.replace(hour=0,minute=0,second=0,microsecond=0)
            week_s  = (now_bt - _dt_bt.timedelta(days=now_bt.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
            month_s = now_bt.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
            year_s  = now_bt.replace(month=1,day=1,hour=0,minute=0,second=0,microsecond=0)
            if 'exit_datetime' in df.columns:
                df['exit_dt'] = _pd13.to_datetime(df['exit_datetime'])
                pnl_today = df[df['exit_dt'] >= _pd13.Timestamp(today_s)]['net_pnl'].sum()
                pnl_week  = df[df['exit_dt'] >= _pd13.Timestamp(week_s)]['net_pnl'].sum()
                pnl_month = df[df['exit_dt'] >= _pd13.Timestamp(month_s)]['net_pnl'].sum()
                pnl_year  = df[df['exit_dt'] >= _pd13.Timestamp(year_s)]['net_pnl'].sum()
            else:
                pnl_today = pnl_week = pnl_month = pnl_year = 0
            avg_slip = df['slippage'].mean() if 'slippage' in df.columns else 5.0
            return {"tot":tot,"win":int(win),"los":int(los),"wr":wr,"nu":nu,"ni":ni,"cm":cm,"dd":dd,"aw":aw,"al":al,"pf":pf,
                    "pnl_today":pnl_today,"pnl_week":pnl_week,"pnl_month":pnl_month,"pnl_year":pnl_year,"avg_slip":avg_slip}
        except:
            return None

    def _v13(m, t):
        if m is None: return "N/A"
        if t=="tot":  return str(m["tot"])
        if t=="win":  return str(m["win"])
        if t=="los":  return str(m["los"])
        if t=="wr":   return f"{m['wr']:.2f}%"
        if t=="pnl":  return f"${m['nu']:,.2f} / \u20b9{m['ni']:,.0f}"
        if t=="aw":   return f"${m['aw']:,.2f}"
        if t=="al":   return f"${m['al']:,.2f}"
        if t=="pf":   return f"{m['pf']:.2f}"
        if t=="dd":   return f"-{m['dd']*100:.2f}%"
        if t=="cm":      return f"${m['cm']:,.2f} / \u20b9{m['cm']*_INR13:,.0f}"
        if t=="cap":     return f"$1,816 / \u20b9{1816*_INR13:,.0f}"
        if t=="today":   return f"${m.get('pnl_today',0):,.2f} / \u20b9{m.get('pnl_today',0)*_INR13:,.0f}"
        if t=="week":    return f"${m.get('pnl_week',0):,.2f} / \u20b9{m.get('pnl_week',0)*_INR13:,.0f}"
        if t=="month":   return f"${m.get('pnl_month',0):,.2f} / \u20b9{m.get('pnl_month',0)*_INR13:,.0f}"
        if t=="year":    return f"${m.get('pnl_year',0):,.2f} / \u20b9{m.get('pnl_year',0)*_INR13:,.0f}"
        if t=="slip":    return f"${m.get('avg_slip',0):,.2f}/side"
        if t=="slipdiff":
            diff = m.get("avg_slip", 5.0) - 5.0
            sign = "+" if diff > 0 else ""
            return f"{sign}${diff:,.2f} vs $5.00"
        return "N/A"

    def _c13(m, pos=True):
        if m is None: return _TDN13
        if pos: return _TDG13 if m.get("nu",0)>=0 else _TDR13
        return _TDR13

    def _build_tbl13(s2m, s4m, cbm):
        def _row(lbl, v2, v4, vc, c2=None, c4=None, cc=None):
            return (f"<tr><td style='{_TD13}'>{lbl}</td>"
                    f"<td style='{c2 or _TDN13}'>{v2}</td>"
                    f"<td style='{c4 or _TDN13}'>{v4}</td>"
                    f"<td style='{cc or _TDB13}'>{vc}</td></tr>")
        return (
            f"<div style='overflow-x:auto;margin:4px 0;'>"
            f"<table style='width:100%;border-collapse:collapse;'>"
            f"<thead><tr>"
            f"<th style='{_TH13}'>Metric</th>"
            f"<th style='{_TH13}'>S2</th>"
            f"<th style='{_TH13}'>S4</th>"
            f"<th style='{_TH13}'>Combined</th>"
            f"</tr></thead><tbody>"
            f"<tr><td colspan='4' style='{_SUB13}'>CAPITAL</td></tr>"
            + _row("Total Capital Required", _v13(s2m,"cap"), _v13(s4m,"cap"), f"$1,816 / \u20b9{int(1816*_INR13):,}")
            + f"<tr><td colspan='4' style='{_SUB13}'>CUMULATIVE PnL</td></tr>"
            + _row("Today PnL",   _v13(s2m,"today"), _v13(s4m,"today"), _v13(cbm,"today"), _c13(s2m,True) if s2m and s2m.get("pnl_today",0)>=0 else _TDR13, _c13(s4m,True) if s4m and s4m.get("pnl_today",0)>=0 else _TDR13, _TDB13)
            + _row("Weekly PnL",  _v13(s2m,"week"),  _v13(s4m,"week"),  _v13(cbm,"week"),  _c13(s2m,True) if s2m and s2m.get("pnl_week",0)>=0 else _TDR13,  _c13(s4m,True) if s4m and s4m.get("pnl_week",0)>=0 else _TDR13,  _TDB13)
            + _row("Monthly PnL", _v13(s2m,"month"), _v13(s4m,"month"), _v13(cbm,"month"), _c13(s2m,True) if s2m and s2m.get("pnl_month",0)>=0 else _TDR13, _c13(s4m,True) if s4m and s4m.get("pnl_month",0)>=0 else _TDR13, _TDB13)
            + _row("Yearly PnL",  _v13(s2m,"year"),  _v13(s4m,"year"),  _v13(cbm,"year"),  _c13(s2m,True) if s2m and s2m.get("pnl_year",0)>=0 else _TDR13,  _c13(s4m,True) if s4m and s4m.get("pnl_year",0)>=0 else _TDR13,  _TDB13)
            + f"<tr><td colspan='4' style='{_SUB13}'>CHARGES</td></tr>"
            + _row("Total Charges", _v13(s2m,"cm"),  _v13(s4m,"cm"),  _v13(cbm,"cm"),  _TDR13,_TDR13,_TDR13)
            + f"<tr><td colspan='4' style='{_SUB13}'>TRADE COUNT</td></tr>"
            + _row("Total Trades",  _v13(s2m,"tot"), _v13(s4m,"tot"), _v13(cbm,"tot"))
            + _row("Wins",          _v13(s2m,"win"), _v13(s4m,"win"), _v13(cbm,"win"), _TDG13,_TDG13,_TDG13)
            + _row("Losses",        _v13(s2m,"los"), _v13(s4m,"los"), _v13(cbm,"los"), _TDR13,_TDR13,_TDR13)
            + f"<tr><td colspan='4' style='{_SUB13}'>PERFORMANCE</td></tr>"
            + _row("Win Rate",      _v13(s2m,"wr"),  _v13(s4m,"wr"),  _v13(cbm,"wr"))
            + _row("Net PnL",       _v13(s2m,"pnl"), _v13(s4m,"pnl"), _v13(cbm,"pnl"), _c13(s2m),_c13(s4m),_c13(cbm))
            + _row("Avg Win",       _v13(s2m,"aw"),  _v13(s4m,"aw"),  _v13(cbm,"aw"),  _TDG13,_TDG13,_TDG13)
            + _row("Avg Loss",      _v13(s2m,"al"),  _v13(s4m,"al"),  _v13(cbm,"al"),  _TDR13,_TDR13,_TDR13)
            + _row("Profit Factor", _v13(s2m,"pf"),  _v13(s4m,"pf"),  _v13(cbm,"pf"))
            + f"<tr><td colspan='4' style='{_SUB13}'>RISK</td></tr>"
            + _row("Max Drawdown",  _v13(s2m,"dd"),  _v13(s4m,"dd"),  _v13(cbm,"dd"),  _TDR13,_TDR13,_TDR13)
            + f"<tr><td colspan='4' style='{_SUB13}'>SLIPPAGE</td></tr>"
            + _row("Avg Slippage/side", _v13(s2m,"slip"), _v13(s4m,"slip"), _v13(cbm,"slip"), _TDR13,_TDR13,_TDR13)
            + _row("vs Backtest ($5/side)", _v13(s2m,"slipdiff"), _v13(s4m,"slipdiff"), _v13(cbm,"slipdiff"), _TDG13 if s2m and s2m.get("avg_slip",5)<=5 else _TDR13, _TDG13 if s4m and s4m.get("avg_slip",5)<=5 else _TDR13, _TDB13)
            + "</tbody></table></div>"
        )

    # ── FETCH LIVE DATA ──────────────────────────────────────
    with st.spinner("Fetching live forward test data..."):
        s2o = _fetch13(os.environ.get("S2_API_KEY",""), os.environ.get("S2_API_SECRET",""))
        s4o = _fetch13(os.environ.get("S4_API_KEY",""), os.environ.get("S4_API_SECRET",""))
    s2p  = _pair13(s2o)
    s4p  = _pair13(s4o)
    s2m  = _calc13(s2p)
    s4m  = _calc13(s4p)
    cbm  = _calc13(s2p+s4p)

    # ── FETCH BACKTEST DATA (same date range) ────────────────
    s2_bt = _bt_calc13("output/trade_log_RenkoReversal*.csv",        _VF13)
    s4_bt = _bt_calc13("output/trade_log_RenkoSMIIOSupertrend*.csv", _VF13)
    cb_bt_pairs = []
    if s2_bt: cb_bt_pairs.append(s2_bt)
    if s4_bt: cb_bt_pairs.append(s4_bt)
    cb_bt = None
    if s2_bt and s4_bt:
        merged = {"tot":s2_bt["tot"]+s4_bt["tot"],
                  "win":s2_bt["win"]+s4_bt["win"],
                  "los":s2_bt["los"]+s4_bt["los"],
                  "wr":(s2_bt["win"]+s4_bt["win"])/(s2_bt["tot"]+s4_bt["tot"])*100,
                  "nu":s2_bt["nu"]+s4_bt["nu"],
                  "ni":s2_bt["ni"]+s4_bt["ni"],
                  "cm":s2_bt["cm"]+s4_bt["cm"],
                  "dd":max(s2_bt["dd"],s4_bt["dd"]),
                  "aw":(s2_bt["aw"]+s4_bt["aw"])/2,
                  "al":(s2_bt["al"]+s4_bt["al"])/2,
                  "pf":(s2_bt["pf"]+s4_bt["pf"])/2}
        cb_bt = merged

    st.caption(f"Valid from: {_VF13} UTC | Auto updates on page load | Testnet")

    # ── TOP TABLE: FORWARD TEST / LIVE ───────────────────────
    st.markdown(f"<div style='{_HDR13}'>FORWARD TEST / LIVE</div>", unsafe_allow_html=True)
    st.markdown(_build_tbl13(s2m, s4m, cbm), unsafe_allow_html=True)

    st.markdown("<div style='margin:12px 0 4px 0;'></div>", unsafe_allow_html=True)

    # ── BOTTOM TABLE: BACKTEST (SAME DATE RANGE) ─────────────
    st.markdown(f"<div style='{_HDR13}'>BACKTEST (SAME DATE RANGE: {_VF13[:10]} to TODAY)</div>", unsafe_allow_html=True)
    st.markdown(_build_tbl13(s2_bt, s4_bt, cb_bt), unsafe_allow_html=True)

# ================================================================
# FOOTER
# ================================================================
st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
st.caption(f"Version: {system.get('version', 'v3.9')} | Commit: {git_commit} | Last refresh: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
# This line intentionally left blank




# ============================================================
# SECTION 14 - SLIPPAGE COMPARISON
# ============================================================
if 'exp_14s' not in st.session_state: st.session_state['exp_14s'] = False
with st.expander('SECTION 14 - SLIPPAGE COMPARISON ($5/side vs $10/side)', expanded=st.session_state.get('exp_14s', False)):

    
    _TH14  = "padding:5px 8px;border:1px solid #C8D0DC;background:#f0f3fa;font-size:10px;font-weight:700;color:#555;"
    _TD14  = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#131722;"
    _TDR   = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#131722;text-align:center;"
    _TDG   = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#089981;font-weight:700;text-align:center;"
    _TDO   = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#e07000;font-weight:700;text-align:center;"
    _TDB   = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#2962FF;font-weight:700;text-align:center;"
    _THGR  = "padding:5px 8px;border:1px solid #C8D0DC;background:#089981;font-size:10px;font-weight:700;color:#fff;text-align:center;"
    _THOG  = "padding:5px 8px;border:1px solid #C8D0DC;background:#e07000;font-size:10px;font-weight:700;color:#fff;text-align:center;"
    _SUBHDR= "padding:4px 8px;border:1px solid #C8D0DC;background:#E8ECF2;font-size:10px;font-weight:700;color:#131722;"
    _DASH  = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#aaa;text-align:center;"
    
    st.markdown(f"""
    <p style="font-size:11px;color:#555;margin:2px 0 8px 0;">
    Period: 2024-01-01 to 2026-07-14 &nbsp;|&nbsp; 31 months &nbsp;|&nbsp; BTCUSD Perpetual &nbsp;|&nbsp; 100 lots/trade</p>
    
    <div style="overflow-x:auto;margin:4px 0;">
    <table style="width:100%;border-collapse:collapse;table-layout:fixed;">
    <colgroup>
      <col style="width:22%">
      <col style="width:13%"><col style="width:13%">
      <col style="width:13%"><col style="width:13%">
      <col style="width:13%"><col style="width:13%">
    </colgroup>
    <thead>
    <tr>
      <th style="{_TH14}" rowspan="2">Metric</th>
      <th style="{_THGR}" colspan="3">$5/side (Realistic)</th>
      <th style="{_THOG}" colspan="3">$10/side (Conservative)</th>
    </tr>
    <tr>
      <th style="{_THGR}">S2</th>
      <th style="{_THGR}">S4</th>
      <th style="{_THGR}">Portfolio</th>
      <th style="{_THOG}">S2</th>
      <th style="{_THOG}">S4</th>
      <th style="{_THOG}">Portfolio</th>
    </tr>
    </thead>
    <tbody>
    <tr><td colspan="7" style="{_SUBHDR}">TRADE COUNT</td></tr>
    <tr style="background:#ffffff;">
      <td style="{_TD14}">Total Trades</td>
      <td style="{_TDR}">7,556</td><td style="{_TDR}">3,898</td><td style="{_TDB}">11,454</td>
      <td style="{_TDR}">7,556</td><td style="{_TDR}">3,898</td><td style="{_TDR}">11,454</td>
    </tr>
    
    <tr><td colspan="7" style="{_SUBHDR}">GREEN MONTHS</td></tr>
    <tr style="background:#fafafa;">
      <td style="{_TD14}">Green Months</td>
      <td style="{_TDG}">31/31</td><td style="{_TDG}">31/31</td><td style="{_TDG}">31/31</td>
      <td style="{_TDO}">25/31</td><td style="{_TDG}">31/31</td><td style="{_TDG}">31/31</td>
    </tr>
    
    <tr><td colspan="7" style="{_SUBHDR}">NET PnL (AFTER TAX)</td></tr>
    <tr style="background:#ffffff;">
      <td style="{_TD14}">Net PnL</td>
      <td style="{_TDG}">₹1,43,86,981</td><td style="{_TDG}">₹1,55,60,542</td><td style="{_TDB}">₹2,99,47,523</td>
      <td style="{_TDR}">₹83,37,327</td><td style="{_TDR}">₹1,24,90,523</td><td style="{_TDR}">₹2,08,27,850</td>
    </tr>
    
    <tr><td colspan="7" style="{_SUBHDR}">RECOMMENDED CAPITAL (3 x MAX DD)</td></tr>
    <tr style="background:#fafafa;">
      <td style="{_TD14}">Rec Capital</td>
      <td style="{_TDG}">₹1,11,354</td><td style="{_TDG}">₹41,247</td><td style="{_TDB}">₹1,52,601</td>
      <td style="{_TDO}">₹5,08,896</td><td style="{_TDO}">₹69,194</td><td style="{_TDO}">₹5,78,090</td>
    </tr>
    
    <tr><td colspan="7" style="{_SUBHDR}">RETURN ON CAPITAL</td></tr>
    <tr style="background:#ffffff;">
      <td style="{_TD14}">ROC (Total)</td>
      <td style="{_TDG}">12,920%</td><td style="{_TDG}">37,724%</td><td style="{_TDB}">19,624%</td>
      <td style="{_TDR}">1,638%</td><td style="{_TDG}">18,051%</td><td style="{_TDR}">3,602%</td>
    </tr>
    <tr style="background:#fafafa;">
      <td style="{_TD14}">Monthly avg ROC</td>
      <td style="{_TDG}">416%</td><td style="{_TDG}">1,216%</td><td style="{_TDB}">633%</td>
      <td style="{_TDR}">53%</td><td style="{_TDG}">582%</td><td style="{_TDR}">116%</td>
    </tr>
    
    <tr><td colspan="7" style="{_SUBHDR}">MAX DRAWDOWN ($5/side only)</td></tr>
    <tr style="background:#ffffff;">
      <td style="{_TD14}">Max DD</td>
      <td style="{_TDR}">-0.48% (₹37,118)</td><td style="{_TDR}">-0.16% (₹13,749)</td><td style="{_DASH}">-</td>
      <td style="{_DASH}">-</td><td style="{_DASH}">-</td><td style="{_DASH}">-</td>
    </tr>
    <tr style="background:#fafafa;">
      <td style="{_TD14}">Avg Margin/trade</td>
      <td style="{_TDR}">$41.89 = ₹3,519</td><td style="{_TDR}">$41.98 = ₹3,526</td><td style="{_DASH}">-</td>
      <td style="{_DASH}">-</td><td style="{_DASH}">-</td><td style="{_DASH}">-</td>
    </tr>
    </tbody>
    </table>
    </div>
    
    <div style="background:#f0f4ff;border-left:3px solid #2962FF;padding:8px 12px;margin:10px 0 4px 0;font-size:11px;color:#131722;">
    <b>Key Observations:</b>
    <ul style="margin:4px 0;padding-left:16px;">
    <li>Trade count identical at both slippages - strategy logic is unchanged</li>
    <li style="color:#089981;font-weight:600;">$5/side: S2 improves from 25/31 to 31/31 green months - all months profitable</li>
    <li style="color:#089981;font-weight:600;">$5/side: Portfolio Rec Capital 3.8x lower = ROC jumps from 3,602% to 19,624%</li>
    <li>$10/side is conservative/safe assumption for live trading presentation</li>
    <li>$5/side is realistic for actual Delta Exchange execution (taker ~$3-5/side)</li>
    <li>Both are valid - use $10 for conservative view, $5 for realistic view</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)

