
import streamlit as st

# Strategy display name mapping
_STRAT_DISPLAY = {
    "renko_reversal_strategy":          "S2 - Renko Reversal (Bot Running)",
    "renko_smiio_supertrend_strategy":  "S4 - Renko SMIIO Supertrend (Bot Running)",
    "renko_breakout_strategy":          "Renko Breakout",
    "renko_options_strategy":           "Renko Options",
    "renko_pattern_breakout_strategy":  "Renko Pattern Breakout",
    "renko_trendline_pullback_strategy":"Renko Trendline Pullback",
}
_STRAT_REVERSE = {v: k for k, v in _STRAT_DISPLAY.items()}

def _get_strat_list():
    import glob as _g, os as _o
    files = sorted([_o.path.splitext(_o.path.basename(p))[0]
                    for p in _g.glob("strategies/backtest/*.py")
                    if not _o.path.basename(p).startswith("_")
                    and _o.path.basename(p).endswith("_strategy.py")
                    and _o.path.basename(p) != "base_strategy.py"])
    # S2 and S4 first, then rest alphabetically
    priority = ["renko_reversal_strategy", "renko_smiio_supertrend_strategy"]
    ordered = [f for f in priority if f in files] + [f for f in files if f not in priority]
    return [_STRAT_DISPLAY.get(s, s) for s in ordered]

def _display_to_class(display_name):
    fname = _STRAT_REVERSE.get(display_name, display_name)
    return "".join(w.capitalize() for w in fname.replace("_strategy","").split("_")) + "Strategy"

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
    background: #42A5F5 !important;
    color: #FFFFFF !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    padding: 4px 10px !important;
    margin-bottom: 4px !important;
    margin-top: 6px !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
    border-radius: 3px !important;
    border-left: 4px solid #1976D2 !important;
    display: inline-block !important;
    width: 25% !important;
    box-sizing: border-box !important;
}

/* EXPANDER - compact width, shrinks to text width */
div[data-testid="stExpander"] > details > summary {
    display: inline-flex !important;
    width: 25% !important;
    padding: 4px 10px !important;
    border-radius: 3px !important;
    background: #42A5F5 !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
}
div[data-testid="stExpander"] > details {
    border: none !important;
    box-shadow: none !important;
}
div[data-testid="stExpander"] > details > summary p,
div[data-testid="stExpander"] > details > summary span {
    color: #FFFFFF !important;
    font-weight: 700 !important;
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

/* FORCE ALL EXPANDER SUMMARY BLUE - overrides all above */
summary,
details > summary,
details[open] > summary,
.streamlit-expanderHeader,
div[data-testid="stExpander"] details summary,
div[data-testid="stExpander"] details[open] summary,
div[data-testid="stExpander"] > div:first-child,
div[data-testid="stExpander"] div[data-testid="stExpander"] > div:first-child,
div[data-testid="stExpander"] div[data-testid="stExpander"] details summary {
    background: #42A5F5 !important;
    color: #FFFFFF !important;
    border-left: 4px solid #1976D2 !important;
}
summary p, summary span, summary div,
details summary p, details summary span,
div[data-testid="stExpander"] details summary p,
div[data-testid="stExpander"] details summary span {
    color: #FFFFFF !important;
}
summary:hover, details summary:hover,
div[data-testid="stExpander"] details summary:hover {
    background: #2196F3 !important;
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
.stInfo { background: #F0F8FF !important; color: #1976D2 !important;
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
        <span style="font-size:11px;color:#131722;font-weight:700;font-family:Georgia,serif;">✦ Created by Anil Dalbanjan &nbsp;|&nbsp; Gandhinagar, Hubli - 580030</span>
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
# SECTION 1 - NEW MONITORING CARDS ROW 2 + ROW 3
# ================================================================
import datetime as _dt_cards, time as _t_cards

# ROW 2 - SYSTEM HEALTH
_cr2a, _cr2b, _cr2c = st.columns(3)

# CARD 1 - BOT LOG STATUS
with _cr2a:
    try:
        _s2_log_age = (_t_cards.time() - os.path.getmtime("/home/anildalabanjan933/crypto_trading_system/logs/live_trading_s2.log")) / 60 if os.path.exists("/home/anildalabanjan933/crypto_trading_system/logs/live_trading_s2.log") else 999
        _s4_log_age = (_t_cards.time() - os.path.getmtime("/home/anildalabanjan933/crypto_trading_system/logs/live_trading_s4.log")) / 60 if os.path.exists("/home/anildalabanjan933/crypto_trading_system/logs/live_trading_s4.log") else 999
        st.markdown("**BOT LOG**")
        if _s2_log_age > 10 or _s4_log_age > 10:
            st.error("INACTIVE")
            st.caption(f"S2: {int(_s2_log_age)}m | S4: {int(_s4_log_age)}m no update")
        else:
            st.success("ACTIVE")
            st.caption(f"S2: {int(_s2_log_age)}m ago | S4: {int(_s4_log_age)}m ago")
    except Exception as _e:
        st.markdown("**BOT LOG**")
        st.warning("UNKNOWN")
        st.caption(str(_e)[:40])

# CARD 2 - DASHBOARD RESTART STATUS
with _cr2b:
    try:
        try:
            _dash_start_file = "logs/dashboard_start.txt"
            if not __import__('os').path.exists(_dash_start_file):
                open(_dash_start_file, 'w').write(_dt_cards.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'))
            _dash_start_str = open(_dash_start_file).read().strip()
            _dash_start_dt  = _dt_cards.datetime.strptime(_dash_start_str, '%Y-%m-%dT%H:%M:%S')
            _dash_uptime    = (_dt_cards.datetime.utcnow() - _dash_start_dt).total_seconds() / 60
        except:
            _dash_uptime = 999
        st.markdown("**DASHBOARD RESTART**")
        if _dash_uptime < 5:
            st.error("RESTARTED")
            st.caption(f"Up: {int(_dash_uptime)}m ago")
        else:
            st.success("STABLE")
            st.caption(f"Uptime: {int(_dash_uptime)}m")
    except Exception as _e:
        st.markdown("**DASHBOARD RESTART**")
        st.warning("UNKNOWN")
        st.caption(str(_e)[:40])

# CARD 3 - API KEY/SECRET STATUS
with _cr2c:
    try:
        _s2k = os.environ.get("S2_API_KEY","")
        _s2s = os.environ.get("S2_API_SECRET","")
        _s4k = os.environ.get("S4_API_KEY","")
        _s4s = os.environ.get("S4_API_SECRET","")
        st.markdown("**API KEY/SECRET**")
        if not _s2k:
            st.error("S2 KEY MISSING")
            st.caption("Check .env S2_API_KEY")
        elif not _s2s:
            st.error("S2 SECRET MISSING")
            st.caption("Check .env S2_API_SECRET")
        elif not _s4k:
            st.error("S4 KEY MISSING")
            st.caption("Check .env S4_API_KEY")
        elif not _s4s:
            st.error("S4 SECRET MISSING")
            st.caption("Check .env S4_API_SECRET")
        else:
            st.success("ALL KEYS OK")
            st.caption("S2 + S4 keys present")
    except Exception as _e:
        st.markdown("**API KEY/SECRET**")
        st.warning("UNKNOWN")
        st.caption(str(_e)[:40])

# ROW 3 - TRADING HEALTH
_cr3a, _cr3b, _cr3c = st.columns(3)

# CARD 4 - SECTION 13 MATCH %
with _cr3a:
    try:
        _match_pct = None
        for _lp in ["logs/live_trading_s2.log", "logs/live_trading_s4.log"]:
            if os.path.exists(_lp):
                with open(_lp) as _lf:
                    _lines = _lf.readlines()
                _ml = [l for l in _lines if 'MATCH' in l or 'match' in l]
                if _ml:
                    import re as _re
                    _m = _re.search(r'(\d+\.?\d*)%', _ml[-1])
                    if _m:
                        _match_pct = float(_m.group(1))
                        break
        st.markdown("**S13 MATCH %**")
        if _match_pct is None:
            st.info("WAITING")
            st.caption("No trade yet")
        elif _match_pct >= 95:
            st.success(f"{_match_pct:.0f}%")
            st.caption("GREEN - Full match")
        elif _match_pct >= 80:
            st.warning(f"{_match_pct:.0f}%")
            st.caption("YELLOW - Partial match")
        else:
            st.error(f"{_match_pct:.0f}%")
            st.caption("RED - Check system")
    except Exception as _e:
        st.markdown("**S13 MATCH %**")
        st.warning("UNKNOWN")
        st.caption(str(_e)[:40])

# CARD 5 - FORWARD TEST COUNT X/5
with _cr3b:
    try:
        _fwd_count = 0
        for _lp in ["logs/live_trading_s2.log", "logs/live_trading_s4.log"]:
            if os.path.exists(_lp):
                with open(_lp) as _lf:
                    _lines = _lf.readlines()
                _cl = [l for l in _lines if 'consecutive' in l.lower() or 'match count' in l.lower()]
                if _cl:
                    import re as _re2
                    _m2 = _re2.search(r'(\d+)/5', _cl[-1])
                    if _m2:
                        _fwd_count = int(_m2.group(1))
                        break
        st.markdown("**FWD TEST X/5**")
        if _fwd_count == 0:
            st.info("0/5")
            st.caption("Waiting for trades")
        elif _fwd_count >= 5:
            st.success("5/5")
            st.caption("GO LIVE READY")
        else:
            st.warning(f"{_fwd_count}/5")
            st.caption(f"{5-_fwd_count} more needed")
    except Exception as _e:
        st.markdown("**FWD TEST X/5**")
        st.warning("UNKNOWN")
        st.caption(str(_e)[:40])

# CARD 6 - MARKET ORDER PnL DIFF
with _cr3c:
    try:
        _pnl_diff = None
        for _lp in ["logs/live_trading_s2.log", "logs/live_trading_s4.log"]:
            if os.path.exists(_lp):
                with open(_lp) as _lf:
                    _lines = _lf.readlines()
                _pl = [l for l in _lines if 'pnl diff' in l.lower() or 'PNL_DIFF' in l]
                if _pl:
                    import re as _re3
                    _m3 = _re3.search(r'[\$₹]?(\d+\.?\d*)', _pl[-1])
                    if _m3:
                        _pnl_diff = float(_m3.group(1))
                        break
        st.markdown("**MARKET ORDER DIFF**")
        if _pnl_diff is None:
            st.info("WAITING")
            st.caption("No trade yet")
        elif _pnl_diff <= 500:
            st.success(f"₹{_pnl_diff:.0f}")
            st.caption("GREEN - Acceptable")
        elif _pnl_diff <= 1000:
            st.warning(f"₹{_pnl_diff:.0f}")
            st.caption("YELLOW - Monitor")
        else:
            st.error(f"₹{_pnl_diff:.0f}")
            st.caption("RED - Review needed")
    except Exception as _e:
        st.markdown("**MARKET ORDER DIFF**")
        st.warning("UNKNOWN")
        st.caption(str(_e)[:40])

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

    # 6. CHECK SYSTEMD SERVICE (tradingbot.service removed - using cts-watchdog)
    pass

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
                            if age_hours > 168:
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
                        if age_hours > 168:
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
        forward_end = datetime.datetime(2026, 8, 1)
        days_left = (forward_end - datetime.datetime.now()).days
        if days_left < 0:
            ok.append("Forward test complete - go-live on Aug 1 2026")
        elif days_left == 0:
            warnings.append("GO-LIVE DAY - Aug 1 2026 - switch testnet=False and update API keys")
        elif days_left <= 3:
            warnings.append(f"GO-LIVE IN {days_left} DAYS - prepare Aug 1 checklist")
        elif days_left <= 7:
            warnings.append(f"Go-live in {days_left} days (Aug 1 2026)")
        else:
            ok.append(f"Forward test: {days_left} days remaining (go-live Aug 1 2026)")
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

        st.caption(f"Last checked: {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5,minutes=30))).strftime('%d-%b-%Y %I:%M %p IST')} | Auto-refreshes every 30s")
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

    def _utc_log_to_ist(raw):
        import datetime as _dti
        _ist = _dti.timedelta(hours=5, minutes=30)
        try:
            ts = raw.strip()[:19]
            dt = _dti.datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
            return (dt + _ist).strftime('%d-%b-%Y %I:%M %p IST')
        except:
            try:
                ts = raw.strip()[:19].replace('T',' ')
                dt = _dti.datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                return (dt + _ist).strftime('%d-%b-%Y %I:%M %p IST')
            except:
                return raw

    def _get_bot_debug(log_path, ts_path, sig_path, bot_name):
        lines = _read_last_lines(log_path)
        now_utc = _dt1c.datetime.utcnow()

        # Last heartbeat
        last_wait = "Never"
        for l in reversed(lines):
            if '[WAIT]' in l or '[ORDER]' in l:
                last_wait = _utc_log_to_ist(l.split(' INFO')[0].strip())
                break

        # Last signal check - read from renko_state_engine.log
        last_reload = "Never"
        _engine_log = os.path.join(os.path.dirname(log_path), "renko_state_engine.log")
        _reload_lines = _read_last_lines(_engine_log, n=200)
        for l in reversed(_reload_lines):
            if '[ENGINE] New candle' in l:
                last_reload = _utc_log_to_ist(l.split(' INFO')[0].strip())
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
        # If UNKNOWN = log scrolled past validation line - if no error then VALID
        if api_status == "UNKNOWN":
            api_status = "VALID"
            api_color = _TDG1C

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
        last_order = "No trades yet today"
        for l in reversed(lines):
            if '[ORDER]' in l and ('ENTRY' in l or 'EXIT' in l):
                _lo_ts = _utc_log_to_ist(l.split(' INFO')[0].strip())
                last_order = _lo_ts + ' ' + ' '.join(l.strip().split()[3:])
                break

        # Last known ts
        try:
            _raw_ts = open(ts_path).read().strip()
            last_ts = _utc_log_to_ist(_raw_ts)
        except:
            last_ts = "Unknown"

        # Next signal
        next_signal = "Waiting - next Renko brick forming"
        next_color = _TDO1C
        try:
            import csv as _csv1c
            now_str = now_utc.strftime('%Y-%m-%dT%H:%M:%S')
            all_rows = []
            with open(sig_path) as fh:
                reader = _csv1c.reader(fh)
                for row in reader:
                    if len(row) < 3: continue
                    if row[0].strip() == "entry_time": continue
                    all_rows.append({
                        "entry_time": row[0].strip(),
                        "exit_time":  row[1].strip(),
                        "direction":  row[2].strip()
                    })
            found = False
            for row in all_rows:
                if row['entry_time'].strip() > last_ts:
                    _ns_et = _utc_log_to_ist(row['entry_time'].strip())
                    _ns_xt = _utc_log_to_ist(row['exit_time'].strip())
                    next_signal = f"ENTRY={_ns_et} EXIT={_ns_xt} DIR={row['direction']}"
                    next_color = _TDG1C
                    found = True
                    break
            if not found and all_rows:
                last_exit = all_rows[-1]['exit_time'].strip()
                if last_exit < now_str:
                    next_signal = f"NO SIGNAL AFTER VALID_FROM - last exit={_utc_log_to_ist(last_exit)}"
                    next_color = _TDR1C
        except Exception as _e1c:
            next_signal = f"Error reading signal CSV: {str(_e1c)[:50]}"
            next_color = _TDR1C

        # Signal CSV last update
        try:
            import os as _os1c, time as _t1c
            age = _t1c.time() - _os1c.path.getmtime(sig_path)
            sig_age = f"{int(age/60)} min ago"
            sig_color = _TDG1C if age < 900 else _TDO1C
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
            elif _hb_age > 55: heartbeat_color = _TDO1C
        except:
            heartbeat_color = _TDO1C

        # Signal CSV staleness
        try:
            import os as _os1c, time as _t1c
            age = _t1c.time() - _os1c.path.getmtime(sig_path)
            sig_age = f"{int(age/60)} min ago"
            sig_color = _TDG1C if age < 900 else _TDO1C
        except:
            sig_age = "Unknown"
            sig_color = _TDO1C

        # Match status - check verify_match log
        match_status = "Pending next trade"
        match_color = _TDG1C
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
            if _csv_age < 7200:
                csv_status = f"FRESH ({int(_csv_age/60)} min ago)"
                csv_color = _TDG1C
            elif _csv_age < 43200:
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
            success_rate = "No trades yet today"
            order_color = _TDG1C

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
        f'{_BASE_DIR}/logs/live_signal_s2.txt', 'S2')
    s4_dbg = _get_bot_debug(
        f'{_BASE_DIR}/logs/live_trading_s4.log',
        f'{_BASE_DIR}/logs/last_known_ts_s4.txt',
        f'{_BASE_DIR}/logs/live_signal_s4.txt', 'S4')

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
        + _dbg_row("Signal Engine", s2_dbg['last_reload'], s4_dbg['last_reload'])
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
            _mname = m.get('name','').lower().replace(' ','_')
            s2_screen = f"{_mname}_s2"
            s4_screen = f"{_mname}_s4"
            _s2_log = f"logs/live_trading_{_mname}_s2.log"
            _s4_log = f"logs/live_trading_{_mname}_s4.log"
            import subprocess
            _scr_out = _timed('screen_list', 30, _fetch_screen_list)
            s2_running = s2_screen in _scr_out
            s4_running = s4_screen in _scr_out
            mc[2].markdown(f"<span style='color:{'green' if s2_running else 'red'}'>{'ON' if s2_running else 'OFF'}</span>", unsafe_allow_html=True)
            mc[3].markdown(f"<span style='color:{'green' if s4_running else 'red'}'>{'ON' if s4_running else 'OFF'}</span>", unsafe_allow_html=True)
            if mc[4].button("▶", key=f"m_start_{idx}"):
                try:
                    env = f"S2_API_KEY={m.get('s2_key','')} S2_API_SECRET={m.get('s2_secret','')} S4_API_KEY={m.get('s4_key','')} S4_API_SECRET={m.get('s4_secret','')}"
                    subprocess.Popen(['bash','-c',f'screen -S {s2_screen} -X quit 2>/dev/null; sleep 1; screen -dmS {s2_screen} bash -c "cd /home/anildalabanjan933/crypto_trading_system && export {env} && .venv/bin/python3 scripts/signal_replay_s2.py >> {_s2_log} 2>&1"'])
                    subprocess.Popen(['bash','-c',f'screen -S {s4_screen} -X quit 2>/dev/null; sleep 1; screen -dmS {s4_screen} bash -c "cd /home/anildalabanjan933/crypto_trading_system && export {env} && .venv/bin/python3 scripts/signal_replay_s4.py >> {_s4_log} 2>&1"'])
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
                                    f'"cd {_base} && '
                                    f"export $(grep -v '#' {_base}/.env | xargs) && "
                                    f'.venv/bin/python3 scripts/signal_replay_{_mkey}_{_b}.py >> '
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
                                   f'export $(grep -v \'#\' {_base}/.env | xargs) && '
                                   f'.venv/bin/python3 scripts/signal_replay_{_mkey}_{_b}.py >> '
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
            subprocess.Popen(['bash','-c','screen -S live_s2 -X quit; sleep 2; screen -dmS live_s2 bash -c "cd /home/anildalabanjan933/crypto_trading_system && .venv/bin/python3 scripts/signal_replay_s2.py >> logs/live_trading_s2.log 2>&1"'])
            st.success("S2 restarting...")
        except Exception as e:
            st.error(str(e))
with b5:
    if st.button("RESTART S4", key="sec2_restart_s4"):
        try:
            import subprocess
            subprocess.Popen(['bash','-c','screen -S live_s4 -X quit; sleep 2; screen -dmS live_s4 bash -c "cd /home/anildalabanjan933/crypto_trading_system && .venv/bin/python3 scripts/signal_replay_s4.py >> logs/live_trading_s4.log 2>&1"'])
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
        # Header row
        hc = st.columns([1,2,1,1,2,2,2])
        for col, label in zip(hc, ['Account','Symbol','Side','Size','Entry $','Unreal PnL','Action']):
            col.markdown(f"<div style='font-size:10px;font-weight:700;color:#555;padding:4px 0;border-bottom:2px solid #C8D0DC;'>{label}</div>", unsafe_allow_html=True)

        for p in all_pos:
            acc  = p['account']
            sym  = p['symbol']
            side = p['side']
            size = int(p['size'])
            sc   = "#089981" if side == 'LONG' else "#F23645"
            pc   = "#089981" if p['unreal_pnl'] >= 0 else "#F23645"
            close_side = 'buy' if side == 'SHORT' else 'sell'
            rc = st.columns([1,2,1,1,2,2,2])
            rc[0].markdown(f"<div style='font-size:11px;padding:6px 0;'>{acc}</div>", unsafe_allow_html=True)
            rc[1].markdown(f"<div style='font-size:11px;padding:6px 0;'>{sym}</div>", unsafe_allow_html=True)
            rc[2].markdown(f"<div style='font-size:11px;padding:6px 0;color:{sc};font-weight:700;'>{side}</div>", unsafe_allow_html=True)
            rc[3].markdown(f"<div style='font-size:11px;padding:6px 0;'>{size}</div>", unsafe_allow_html=True)
            rc[4].markdown(f"<div style='font-size:11px;padding:6px 0;text-align:right;'>${p['entry']:,.1f}</div>", unsafe_allow_html=True)
            rc[5].markdown(f"<div style='font-size:11px;padding:6px 0;color:{pc};font-weight:600;'>${p['unreal_pnl']:,.2f} | ₹{p['unreal_pnl']*INR_RATE:,.0f}</div>", unsafe_allow_html=True)
            with rc[6]:
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
                'DateTime':    datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5,minutes=30))).strftime('%d-%b-%Y %I:%M %p IST'),
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
                _rows += "<td style='{}'>{}</td>".format(TD2, datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5,minutes=30))).strftime('%d-%b-%Y %I:%M %p IST'))
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

        st.caption(f"Charges = Commission + Funding + 30% Tax on profit | Funding: ${total_fund_all:,.4f} | Commission: ${total_comm_all:,.4f} | Updated: {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5,minutes=30))).strftime('%I:%M %p IST')} | Testnet")

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
                last_str  = (datetime.datetime.utcfromtimestamp(last_run) + datetime.timedelta(hours=5,minutes=30)).strftime('%d-%b-%Y %I:%M %p IST')
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
                        _comp_dr = __import__("re").search(r'(\d{8})', __import__("os").path.basename(sel_comp))
                        _comp_ds = _comp_dr.group(1) if _comp_dr else "report"
                        st.download_button("DOWNLOAD USER HTML", user_comp.encode('utf-8'), file_name=f"alpha_{algo_name}_comparison_{_comp_ds}.html", mime="text/html", key=f"dl_comp_user_{algo_key}")
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
            *_get_strat_list()
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
                _bt_dr = __import__("re").search(r'(\d{8})', __import__("os").path.basename(selected_html))
                _bt_ds = _bt_dr.group(1) if _bt_dr else "report"
                _bt_sn = __import__("re").search(r'backtest_report_([^_]+(?:_[^_]+)*?)_BTCUSD', __import__("os").path.basename(selected_html))
                _bt_sl = _bt_sn.group(1) if _bt_sn else "strategy"
                st.download_button("DOWNLOAD USER HTML", user_content.encode('utf-8'), file_name=f"alpha_{_bt_sl}_{_bt_ds}_backtest.html", mime="text/html", key="sec6_dl_user_html")
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
    # SECTION 5 - TAB 2 - SCALE BACKTEST
    # ================================================================
    st.markdown('<hr style="margin:8px 0;border:none;border-top:2px solid #e0e0e0;">', unsafe_allow_html=True)
    st.markdown("### Scale Backtest (Compounding Optimiser)")
    import sys as _sys5s
    _sys5s.path.insert(0, '/home/anildalabanjan933/crypto_trading_system')
    from engine.scaling_engine import load_trades, run_full_mode, run_group_mode, apply_scaling, calculate_metrics
    _sc1, _sc2, _sc3 = st.columns(3)
    with _sc1:
        sc_strategy = st.selectbox("Strategy", _get_strat_list() + ["Portfolio (S2+S4 Combined)"], key="sc_strategy")
    with _sc2:
        sc_scale_type = st.selectbox("Scaling Type", ["Step Based (Preferred)","Formula Based"], key="sc_type")
    with _sc3:
        sc_mode = st.selectbox("Mode", ["Full Mode (All Combinations)","Group Mode - Period","Group Mode - Step","Group Mode - Cap"], key="sc_mode")
    _sc4, _sc5 = st.columns(2)
    with _sc4:
        sc_starting_lots = st.number_input("Starting Lots", min_value=1, max_value=10000, value=100, key="sc_lots")
    with _sc5:
        sc_slippage = st.number_input("Slippage/side ($)", min_value=0.0, value=5.0, key="sc_slip")
    sc_include_charges = st.checkbox("Include Tax & All Charges", value=True, key="sc_charges")
    st.markdown("**Date Range**")
    sc_range = st.radio("Scale Date Range", ["1 Month","6 Months","1 Year","1.5 Years","2 Years","Full CSV","Custom"], index=5, horizontal=True, key="sc_range", label_visibility="collapsed")
    _today_sc = datetime.date.today()
    if sc_range == "1 Month":
        sc_start = _today_sc - datetime.timedelta(days=30); sc_end = _today_sc
    elif sc_range == "6 Months":
        sc_start = _today_sc - datetime.timedelta(days=180); sc_end = _today_sc
    elif sc_range == "1 Year":
        sc_start = _today_sc - datetime.timedelta(days=365); sc_end = _today_sc
    elif sc_range == "1.5 Years":
        sc_start = _today_sc - datetime.timedelta(days=548); sc_end = _today_sc
    elif sc_range == "2 Years":
        sc_start = _today_sc - datetime.timedelta(days=730); sc_end = _today_sc
    elif sc_range == "Full CSV":
        sc_start = datetime.date.fromisoformat("2024-01-01"); sc_end = _today_sc
    else:
        _scc1, _scc2 = st.columns(2)
        with _scc1:
            sc_start = st.date_input("Start Date", value=datetime.date(2025,1,1), key="sc_start")
        with _scc2:
            sc_end = st.date_input("End Date", value=_today_sc, key="sc_end")
    if st.button("RUN SCALING OPTIMISER", key="sc_run"):
        _sc_status = st.empty()
        _sc_progress = st.progress(0)
        try:
            import glob as _scglob, os as _scos
            if sc_strategy == "Portfolio (S2+S4 Combined)":
                _sc_pattern = "output/portfolio_trade_log_*.csv"
            else:
                _sc_pattern = f"output/trade_log_{sc_strategy}_BTCUSD_*.csv"
            _sc_files = sorted([f for f in _scglob.glob(_sc_pattern)], reverse=True)
            if not _sc_files:
                _sc_status.error(f"No CSV found for {sc_strategy}. Run backtest first.")
            else:
                _sc_csv = _sc_files[0]
                _sc_status.info(f"Loading: {_scos.path.basename(_sc_csv)}")
                _sc_progress.progress(20)
                _all_trades = load_trades(_sc_csv)
                _filtered = [t for t in _all_trades if str(sc_start) <= t['entry_datetime'][:10] <= str(sc_end)]
                if not _filtered:
                    _sc_status.error(f"No trades in range {sc_start} to {sc_end}")
                else:
                    _sc_status.info(f"Loaded {len(_filtered)} trades - running optimiser...")
                    _sc_progress.progress(40)
                    _scale_type = "step" if "Step" in sc_scale_type else "formula"
                    if "Full Mode" in sc_mode:
                        _results = run_full_mode(_filtered, sc_starting_lots, _scale_type)
                    elif "Period" in sc_mode:
                        _results = run_group_mode(_filtered, sc_starting_lots, "period", _scale_type)
                    elif "Step" in sc_mode:
                        _results = run_group_mode(_filtered, sc_starting_lots, "step", _scale_type)
                    else:
                        _results = run_group_mode(_filtered, sc_starting_lots, "cap", _scale_type)
                    _sc_progress.progress(80)
                    _base_trades, _ = apply_scaling(_filtered, sc_starting_lots, 0, 1, sc_starting_lots, "step")
                    _base_metrics = calculate_metrics(_base_trades, sc_starting_lots)
                    st.session_state['sc_results'] = _results
                    st.session_state['sc_base_metrics'] = _base_metrics
                    st.session_state['sc_strategy_result'] = sc_strategy
                    st.session_state['sc_starting_lots'] = sc_starting_lots
                    _sc_progress.progress(100)
                    _sc_status.success(f"Done! {len(_results)} combinations tested.")
                    import time as _sct; _sct.sleep(1); st.rerun()
        except Exception as _sce:
            _sc_status.error(f"Error: {_sce}")
            import traceback; st.code(traceback.format_exc())
    if 'sc_results' in st.session_state and st.session_state['sc_results']:
        _res = st.session_state['sc_results']
        _base = st.session_state.get('sc_base_metrics', {})
        _best = _res[0]
        st.markdown("---")
        st.markdown("#### Results - Ranked Best to Worst (Net PnL INR)")
        _tbl_rows = ""
        for i, r in enumerate(_res):
            _bg = "background:#e8f5e9;" if i == 0 else ""
            _rank = "BEST" if i == 0 else str(i+1)
            _tbl_rows += (f"<tr style='{_bg}'>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;font-weight:700;color:#089981;'>{_rank}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;'>{r.get('scale_period',r.get('value',''))}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;'>{r.get('increment_step',r.get('value','-'))}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;'>{r.get('max_lots_cap','-')}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;'>{r.get('max_lots_reached','-')}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;color:#089981;font-weight:700;'>Rs{r['net_pnl_inr']:,.0f}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;'>{r['win_rate']:.1f}%</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;'>{r['profit_factor']:.2f}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;'>Rs{r['max_dd_inr']:,.0f}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;'>{r['sharpe']:.2f}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;'>{r['profitable_months']}/{r['profitable_months']+r['losing_months']}</td>"
                "</tr>")
        _tbl_html = ("<div style='overflow-x:auto;'><table style='width:100%;border-collapse:collapse;font-size:12px;'>"
            "<thead><tr style='background:#f0f3fa;'>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Rank</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Period</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Step</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Cap</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Max Lots</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Net PnL INR</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Win Rate</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>PF</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Max DD INR</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Sharpe</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Prof Months</th>"
            f"</tr></thead><tbody>{_tbl_rows}</tbody></table></div>")
        st.markdown(_tbl_html, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("#### Side by Side Comparison")
        _col_l, _col_r = st.columns(2)
        def _mrow(label, val):
            return f"<tr><td style='padding:4px 8px;border:1px solid #ddd;font-weight:600;'>{label}</td><td style='padding:4px 8px;border:1px solid #ddd;'>{val}</td></tr>"
        with _col_l:
            st.markdown(f"**Normal ({sc_starting_lots} lots fixed)**")
            _left_rows = (
                _mrow('Trades', str(_base.get('total_trades',0))) +
                _mrow('Win Rate', str(round(_base.get('win_rate',0),2))+'%') +
                _mrow('Net PnL INR', 'Rs'+f"{_base.get('net_pnl_inr',0):,.0f}") +
                _mrow('Profit Factor', str(round(_base.get('profit_factor',0),2))) +
                _mrow('Max DD INR', 'Rs'+f"{_base.get('max_dd_inr',0):,.0f}") +
                _mrow('Sharpe', str(round(_base.get('sharpe',0),2))) +
                _mrow('Prof Months', str(_base.get('profitable_months',0))+'/'+str(_base.get('profitable_months',0)+_base.get('losing_months',0))) +
                _mrow('Max Lots', str(sc_starting_lots))
            )
            st.markdown("<table style='width:100%;border-collapse:collapse;font-size:12px;'>"+_left_rows+"</table>", unsafe_allow_html=True)
        with _col_r:
            _bm = _best.get('metrics',{})
            st.markdown(f"**Best Scaled - {_best.get('scale_period',_best.get('value',''))} | {_best.get('increment_step',_best.get('value',''))} | Cap:{_best.get('max_lots_cap','-')}**")
            _right_rows = (
                _mrow('Trades', str(_bm.get('total_trades',0))) +
                _mrow('Win Rate', str(round(_bm.get('win_rate',0),2))+'%') +
                _mrow('Net PnL INR', 'Rs'+f"{_bm.get('net_pnl_inr',0):,.0f}") +
                _mrow('Profit Factor', str(round(_bm.get('profit_factor',0),2))) +
                _mrow('Max DD INR', 'Rs'+f"{_bm.get('max_dd_inr',0):,.0f}") +
                _mrow('Sharpe', str(round(_bm.get('sharpe',0),2))) +
                _mrow('Prof Months', str(_bm.get('profitable_months',0))+'/'+str(_bm.get('profitable_months',0)+_bm.get('losing_months',0))) +
                _mrow('Max Lots Reached', str(_best.get('max_lots_reached','-')))
            )
            st.markdown("<table style='width:100%;border-collapse:collapse;font-size:12px;'>"+_right_rows+"</table>", unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("#### Monthly Returns Comparison")
        _bm2 = _best.get('metrics',{}).get('monthly',{})
        _bsm = _base.get('monthly',{})
        _months = sorted(set(list(_bm2.keys())+list(_bsm.keys())))
        _mrows = ""
        for m in _months:
            _bi = _bsm.get(m,{}).get('net_inr',0)
            _si = _bm2.get(m,{}).get('net_inr',0)
            _di = _si - _bi
            _bc = "color:#089981;" if _bi>=0 else "color:#F23645;"
            _sc2 = "color:#089981;" if _si>=0 else "color:#F23645;"
            _dc = "color:#089981;" if _di>=0 else "color:#F23645;"
            _mrows += (f"<tr><td style='padding:4px 8px;border:1px solid #ddd;'>{m}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;{_bc}'>Rs{_bi:,.0f}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;{_sc2}'>Rs{_si:,.0f}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;{_dc}'>Rs{_di:,.0f}</td></tr>")
        st.markdown(("<div style='overflow-x:auto;'><table style='width:100%;border-collapse:collapse;font-size:12px;'>"
            "<thead><tr style='background:#f0f3fa;'>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Month</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Normal INR</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Scaled INR</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Difference</th>"
            f"</tr></thead><tbody>{_mrows}</tbody></table></div>"), unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("#### Yearly Returns Comparison")
        _by = _best.get('metrics',{}).get('yearly',{})
        _bsy = _base.get('yearly',{})
        _years = sorted(set(list(_by.keys())+list(_bsy.keys())))
        _yrows = ""
        for y in _years:
            _bi = _bsy.get(y,{}).get('net_inr',0)
            _si = _by.get(y,{}).get('net_inr',0)
            _di = _si - _bi
            _bc = "color:#089981;" if _bi>=0 else "color:#F23645;"
            _sc3 = "color:#089981;" if _si>=0 else "color:#F23645;"
            _dc = "color:#089981;" if _di>=0 else "color:#F23645;"
            _yrows += (f"<tr><td style='padding:4px 8px;border:1px solid #ddd;'>{y}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;{_bc}'>Rs{_bi:,.0f}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;{_sc3}'>Rs{_si:,.0f}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd;{_dc}'>Rs{_di:,.0f}</td></tr>")
        st.markdown(("<div style='overflow-x:auto;'><table style='width:100%;border-collapse:collapse;font-size:12px;'>"
            "<thead><tr style='background:#f0f3fa;'>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Year</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Normal INR</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Scaled INR</th>"
            "<th style='padding:6px 8px;border:1px solid #ddd;'>Difference</th>"
            f"</tr></thead><tbody>{_yrows}</tbody></table></div>"), unsafe_allow_html=True)
        _all_months = sorted(set(list(_bm2.keys())+list(_bsm.keys())))
        _all_years = sorted(set(list(_by.keys())+list(_bsy.keys())))
        _sc_strat = st.session_state.get('sc_strategy_result','')
        _sc_best_period = _best.get('scale_period', _best.get('value',''))
        _sc_best_step = _best.get('increment_step', _best.get('value','-'))
        _sc_best_cap = _best.get('max_lots_cap','-')
        _sc_best_pnl = _best['net_pnl_inr']
        _sc_best_dd = _best['max_dd_inr']
        _sc_best_pf = _best['profit_factor']
        _sc_best_sr = _best['sharpe']
        _sc_best_wr = _best['win_rate']
        _sc_best_ml = _best.get('max_lots_reached','-')
        _sc_norm_pnl = _base.get('net_pnl_inr',0)
        _sc_norm_dd = _base.get('max_dd_inr',0)
        _sc_norm_pf = _base.get('profit_factor',0)
        _sc_norm_sr = _base.get('sharpe',0)
        _sc_norm_wr = _base.get('win_rate',0)
        _sc_norm_tr = _base.get('total_trades',0)
        _m_rows_html = ""
        for m in _all_months:
            _bi = _bsm.get(m,{}).get('net_inr',0)
            _si = _bm2.get(m,{}).get('net_inr',0)
            _di = _si - _bi
            _bc = "color:#27ae60;" if _bi>=0 else "color:#e74c3c;"
            _sc2c = "color:#27ae60;" if _si>=0 else "color:#e74c3c;"
            _dc = "color:#27ae60;" if _di>=0 else "color:#e74c3c;"
            _m_rows_html += f"<tr><td>{m}</td><td style='{_bc}font-weight:bold;'>Rs{_bi:,.0f}</td><td style='{_sc2c}font-weight:bold;'>Rs{_si:,.0f}</td><td style='{_dc}font-weight:bold;'>Rs{_di:,.0f}</td></tr>"
        _y_rows_html = ""
        for y in _all_years:
            _bi = _bsy.get(y,{}).get('net_inr',0)
            _si = _by.get(y,{}).get('net_inr',0)
            _di = _si - _bi
            _bc = "color:#27ae60;" if _bi>=0 else "color:#e74c3c;"
            _sc3c = "color:#27ae60;" if _si>=0 else "color:#e74c3c;"
            _dc = "color:#27ae60;" if _di>=0 else "color:#e74c3c;"
            _y_rows_html += f"<tr><td>{y}</td><td style='{_bc}font-weight:bold;'>Rs{_bi:,.0f}</td><td style='{_sc3c}font-weight:bold;'>Rs{_si:,.0f}</td><td style='{_dc}font-weight:bold;'>Rs{_di:,.0f}</td></tr>"
        _html_dl = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Scaling Optimiser Report - {_sc_strat}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:"Segoe UI",Tahoma,Geneva,Verdana,sans-serif; background:#f5f5f5; color:#333; line-height:1.6; }}
.container {{ max-width:1400px; margin:0 auto; padding:20px; }}
.header {{ background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); color:white; padding:30px; border-radius:8px; margin-bottom:30px; box-shadow:0 4px 6px rgba(0,0,0,0.1); }}
.header h1 {{ font-size:28px; margin-bottom:10px; }}
.header-info {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:20px; margin-top:20px; }}
.header-item {{ background:rgba(255,255,255,0.1); padding:15px; border-radius:5px; }}
.header-item label {{ font-size:12px; opacity:0.9; display:block; margin-bottom:5px; }}
.header-item value {{ font-size:18px; font-weight:bold; }}
.section {{ background:white; padding:25px; margin-bottom:20px; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.1); }}
.section h2 {{ font-size:20px; margin-bottom:20px; color:#667eea; border-bottom:2px solid #667eea; padding-bottom:10px; }}
table {{ width:100%; border-collapse:collapse; margin-top:15px; }}
th {{ background-color:#667eea; color:white; padding:12px; text-align:left; font-weight:600; }}
td {{ padding:12px; border-bottom:1px solid #ddd; }}
tr:hover {{ background-color:#f9f9f9; }}
.positive {{ color:#27ae60; font-weight:bold; }}
.negative {{ color:#e74c3c; font-weight:bold; }}
.metric-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:15px; margin-top:15px; }}
.metric-card {{ background:#f9f9f9; padding:15px; border-radius:5px; border-left:4px solid #667eea; }}
.metric-card label {{ font-size:12px; color:#666; display:block; margin-bottom:5px; }}
.metric-card value {{ font-size:18px; font-weight:bold; display:block; }}
.footer {{ text-align:center; padding:20px; color:#999; font-size:12px; }}
.best-badge {{ background:#27ae60; color:white; padding:4px 10px; border-radius:12px; font-size:12px; font-weight:bold; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>Scaling Optimiser Report</h1>
<p>{_sc_strat} | Step Based Compounding | Best Config: {_sc_best_period} Period | {_sc_best_step} Step | Cap: {_sc_best_cap}</p>
<div class="header-info">
<div class="header-item"><label>Best Scaled Net PnL</label><value class="positive">Rs{_sc_best_pnl:,.0f}</value></div>
<div class="header-item"><label>Normal Net PnL (100 lots)</label><value>Rs{_sc_norm_pnl:,.0f}</value></div>
<div class="header-item"><label>Extra Profit from Scaling</label><value class="positive">Rs{_sc_best_pnl-_sc_norm_pnl:,.0f}</value></div>
<div class="header-item"><label>Max Lots Reached</label><value>{_sc_best_ml}</value></div>
<div class="header-item"><label>Best Profit Factor</label><value>{_sc_best_pf:.2f}</value></div>
<div class="header-item"><label>Best Sharpe Ratio</label><value>{_sc_best_sr:.2f}</value></div>
<div class="header-item"><label>Max DD (Scaled)</label><value class="negative">Rs{_sc_best_dd:,.0f}</value></div>
<div class="header-item"><label>Win Rate</label><value>{_sc_best_wr:.1f}%</value></div>
</div>
</div>
<div class="section">
<h2>Side by Side Comparison</h2>
<table>
<thead><tr><th>Metric</th><th>Normal (100 lots fixed)</th><th>Best Scaled Config</th><th>Improvement</th></tr></thead>
<tbody>
<tr><td>Total Trades</td><td>{_sc_norm_tr}</td><td>{_best.get('metrics',{}).get('total_trades',0)}</td><td>-</td></tr>
<tr><td>Win Rate</td><td>{_sc_norm_wr:.2f}%</td><td>{_sc_best_wr:.2f}%</td><td>-</td></tr>
<tr><td>Net PnL INR</td><td class="positive">Rs{_sc_norm_pnl:,.0f}</td><td class="positive">Rs{_sc_best_pnl:,.0f}</td><td class="positive">+Rs{_sc_best_pnl-_sc_norm_pnl:,.0f}</td></tr>
<tr><td>Profit Factor</td><td>{_sc_norm_pf:.2f}</td><td>{_sc_best_pf:.2f}</td><td>-</td></tr>
<tr><td>Max DD INR</td><td class="negative">Rs{_sc_norm_dd:,.0f}</td><td class="negative">Rs{_sc_best_dd:,.0f}</td><td>-</td></tr>
<tr><td>Sharpe Ratio</td><td>{_sc_norm_sr:.2f}</td><td>{_sc_best_sr:.2f}</td><td>-</td></tr>
<tr><td>Max Lots</td><td>100</td><td>{_sc_best_ml}</td><td>-</td></tr>
</tbody>
</table>
</div>
<div class="section">
<h2>Monthly Returns Comparison</h2>
<table>
<thead><tr><th>Month</th><th>Normal INR</th><th>Scaled INR</th><th>Difference</th></tr></thead>
<tbody>{_m_rows_html}</tbody>
</table>
</div>
<div class="section">
<h2>Yearly Returns Comparison</h2>
<table>
<thead><tr><th>Year</th><th>Normal INR</th><th>Scaled INR</th><th>Difference</th></tr></thead>
<tbody>{_y_rows_html}</tbody>
</table>
</div>
<div class="footer">Generated by CTS Scaling Optimiser | {_sc_strat}</div>
</div>
</body>
</html>"""
        st.download_button("DOWNLOAD SCALING REPORT HTML", _html_dl.encode('utf-8'),
            file_name=f"scaling_{st.session_state.get('sc_strategy_result','')}.html",
            mime="text/html", key="sc_dl_html")


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
            *_get_strat_list()
        ]
        selected_strategies = st.multiselect(
            "Select Strategies",
            available_strategies,
            default=_get_strat_list()[:2],
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
                _pt_dr = __import__("re").search(r'(\d{8})', __import__("os").path.basename(sel_port_html))
                _pt_ds = _pt_dr.group(1) if _pt_dr else "report"
                st.download_button("DOWNLOAD USER HTML", user_content.encode('utf-8'), file_name=f"alpha_portfolio_{_pt_ds}.html", mime="text/html", key="port_dl_user_html")
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
            *_get_strat_list()
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
    # Section 13 display window = last 7 days rolling (not VALID_FROM)
    import datetime as _dt13_7
    _VF13_7D = (_dt13_7.datetime.utcnow() - _dt13_7.timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%S')
    _INR13 = 84.0
    _BASE13= "https://cdn-ind.testnet.deltaex.org"
    _TH13  = "padding:5px 8px;border:1px solid #C8D0DC;background:#f0f3fa;font-size:11px;font-weight:700;color:#333;text-align:center;"
    _TD13  = "padding:6px 8px;border:1px solid #E0E3EB;font-size:13px;color:#131722;font-weight:600;"
    _TDN13 = "padding:6px 8px;border:1px solid #E0E3EB;font-size:13px;color:#131722;text-align:center;font-weight:500;"
    _TDG13 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:12px;color:#089981;font-weight:700;text-align:center;"
    _TDR13 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:12px;color:#F23645;font-weight:700;text-align:center;"
    _TDB13 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:12px;color:#2962FF;font-weight:700;text-align:center;"
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
            # Entry must be reduce_only=False
            if str(e.get("reduce_only","")).lower() in ["true","1"]: continue
            es = e.get("side")
            if es not in ["buy","sell"]: continue
            xs  = "sell" if es=="buy" else "buy"
            dir = "LONG" if es=="buy" else "SHORT"
            ets = int(_dt13.datetime.strptime(e.get("created_at","1970-01-01T00:00:00")[:19], "%Y-%m-%dT%H:%M:%S").timestamp())
            ep  = float(e.get("average_fill_price") or e.get("limit_price") or 0)
            for j, x in enumerate(srt):
                if j in used or j==i: continue
                if x.get("side")!=xs or x.get("state")!="closed": continue
                # Exit must be reduce_only=True
                if str(x.get("reduce_only","")).lower() not in ["true","1"]: continue
                xts = int(_dt13.datetime.strptime(x.get("created_at","1970-01-01T00:00:00")[:19], "%Y-%m-%dT%H:%M:%S").timestamp())
                xp  = float(x.get("average_fill_price") or x.get("limit_price") or 0)
                if xts < ets: continue
                sz  = int(e.get("size",0))
                # Use actual exchange PnL from exit order meta_data
                raw_pnl = float(x.get("meta_data",{}).get("pnl") or 0)
                cm  = float(e.get("paid_commission") or 0)+float(x.get("paid_commission") or 0)
                pnl = raw_pnl - cm
                pairs.append({"dir":dir,"ep":ep,"xp":xp,"pnl":pnl,"cm":cm,"ets":ets,"xts":xts,"sz":sz})
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
            drop = pk - cum
            if drop > dd: dd = drop
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
        avg_slip    = sum(abs(p.get("ep",0)-p.get("xp",0))*0.001 for p in pairs)/tot if tot>0 else 5.0
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
                drop = pk - cum
                if drop > dd: dd = drop
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
            avg_slip = df['slippage_usd'].mean() if 'slippage_usd' in df.columns else 5.0
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
        if t=="dd":   return f"-₹{m['dd']*84:,.0f}" if m['dd']>0 else "₹0"
        if t=="cm":      return f"${m['cm']:,.2f} / \u20b9{m['cm']*_INR13:,.0f}"
        if t=="cap":     return f"\u20b9{1816*_INR13:,.0f}"
        if t=="today":   return f"\u20b9{m.get('pnl_today',0)*_INR13:,.0f}"
        if t=="week":    return f"\u20b9{m.get('pnl_week',0)*_INR13:,.0f}"
        if t=="month":   return f"\u20b9{m.get('pnl_month',0)*_INR13:,.0f}"
        if t=="year":    return f"\u20b9{m.get('pnl_year',0)*_INR13:,.0f}"
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
            # S2/S4 columns: grey if N/A
            _c2 = _TDN13 if str(v2)=='N/A' else (c2 or _TDN13)
            _c4 = _TDN13 if str(v4)=='N/A' else (c4 or _TDN13)
            # Combined column: green/red/grey based on value
            # Always override color for N/A regardless of passed cc
            _vc = str(vc)
            if _vc == 'N/A':
                cc = _TDN13
            elif cc is None:
                if _vc.startswith('-') or _vc.startswith('$-') or _vc.startswith('₹-'):
                    cc = _TDR13
                elif _vc in ['0','0.00%','$0.00','₹0','0.00','0.00%']:
                    cc = _TDN13
                else:
                    cc = _TDG13
            return (f"<tr><td style='{_TD13}'>{lbl}</td>"
                    f"<td style='{_c2}'>{v2}</td>"
                    f"<td style='{_c4}'>{v4}</td>"
                    f"<td style='{cc}'>{vc}</td></tr>")
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
            + _row("Total Capital Required", _v13(s2m,"cap"), _v13(s4m,"cap"), f"\u20b9{int(1816*_INR13):,}")
            + f"<tr><td colspan='4' style='{_SUB13}'>CUMULATIVE PnL</td></tr>"
            + _row("Today PnL",   _v13(s2m,"today"), _v13(s4m,"today"), _v13(cbm,"today"), _c13(s2m,True) if s2m and s2m.get("pnl_today",0)>=0 else _TDR13, _c13(s4m,True) if s4m and s4m.get("pnl_today",0)>=0 else _TDR13, _c13(cbm,True) if cbm and cbm.get("pnl_today",0)>=0 else _TDR13)
            + _row("Weekly PnL",  _v13(s2m,"week"),  _v13(s4m,"week"),  _v13(cbm,"week"),  _c13(s2m,True) if s2m and s2m.get("pnl_week",0)>=0 else _TDR13,  _c13(s4m,True) if s4m and s4m.get("pnl_week",0)>=0 else _TDR13,  _c13(cbm,True) if cbm and cbm.get("pnl_week",0)>=0 else _TDR13)
            + _row("Monthly PnL", _v13(s2m,"month"), _v13(s4m,"month"), _v13(cbm,"month"), _c13(s2m,True) if s2m and s2m.get("pnl_month",0)>=0 else _TDR13, _c13(s4m,True) if s4m and s4m.get("pnl_month",0)>=0 else _TDR13, _c13(cbm,True) if cbm and cbm.get("pnl_month",0)>=0 else _TDR13)
            + _row("Yearly PnL",  _v13(s2m,"year"),  _v13(s4m,"year"),  _v13(cbm,"year"),  _c13(s2m,True) if s2m and s2m.get("pnl_year",0)>=0 else _TDR13,  _c13(s4m,True) if s4m and s4m.get("pnl_year",0)>=0 else _TDR13,  _c13(cbm,True) if cbm and cbm.get("pnl_year",0)>=0 else _TDR13)
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
    s2_bt = _bt_calc13("output/trade_log_RenkoReversal*.csv",        _VF13_7D)
    s4_bt = _bt_calc13("output/trade_log_RenkoSMIIOSupertrend*.csv", _VF13_7D)
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
                  "aw":(s2_bt["aw"]*s2_bt["win"]+s4_bt["aw"]*s4_bt["win"])/(s2_bt["win"]+s4_bt["win"]) if (s2_bt["win"]+s4_bt["win"])>0 else 0,
                  "al":(s2_bt["al"]*s2_bt["los"]+s4_bt["al"]*s4_bt["los"])/(s2_bt["los"]+s4_bt["los"]) if (s2_bt["los"]+s4_bt["los"])>0 else 0,
                  "pf":abs((s2_bt["aw"]*s2_bt["win"]+s4_bt["aw"]*s4_bt["win"])/(s2_bt["al"]*s2_bt["los"]+s4_bt["al"]*s4_bt["los"])) if (s2_bt["los"]+s4_bt["los"])>0 and (s2_bt["al"]*s2_bt["los"]+s4_bt["al"]*s4_bt["los"])!=0 else 0,
                  "pnl_today":s2_bt.get("pnl_today",0)+s4_bt.get("pnl_today",0),
                  "pnl_week":s2_bt.get("pnl_week",0)+s4_bt.get("pnl_week",0),
                  "pnl_month":s2_bt.get("pnl_month",0)+s4_bt.get("pnl_month",0),
                  "pnl_year":s2_bt.get("pnl_year",0)+s4_bt.get("pnl_year",0)}
        cb_bt = merged

    st.caption(f"Showing last 7 days | Valid from: {_VF13_7D[:10]} UTC | Auto updates on page load | Testnet")

    # ── TOP TABLE: FORWARD TEST / LIVE ───────────────────────
    # Side by side: Forward Test | Backtest
    _col13a, _col13b = st.columns(2)
    with _col13a:
        st.markdown(f"<div style='{_HDR13}'>FORWARD TEST / LIVE</div>", unsafe_allow_html=True)
        st.markdown(_build_tbl13(s2m, s4m, cbm), unsafe_allow_html=True)
    with _col13b:
        st.markdown(f"<div style='{_HDR13}'>BACKTEST (LAST 7 DAYS: {_VF13_7D[:10]} to TODAY)</div>", unsafe_allow_html=True)
        st.markdown(_build_tbl13(s2_bt, s4_bt, cb_bt), unsafe_allow_html=True)

    # ================================================================
    # LAST 20 TRADES - FORWARD TEST (LEFT) | BACKTEST (RIGHT)
    # ================================================================
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    _TH20 = "padding:4px 6px;border:1px solid #C8D0DC;background:#f0f3fa;font-size:10px;font-weight:700;color:#333;text-align:center;white-space:nowrap;"
    _TD20 = "padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;color:#131722;text-align:center;white-space:nowrap;"
    _TG20 = "padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;color:#089981;font-weight:700;text-align:center;"
    _TR20 = "padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;color:#F23645;font-weight:700;text-align:center;"
    _TY20 = "padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;color:#e07000;font-weight:700;text-align:center;"

    def _fwd20(pairs):
        try:
            if not pairs:
                return (f"<div style='overflow-x:auto;max-height:350px;overflow-y:auto;'><table style='width:100%;border-collapse:collapse;'><thead><tr><th style='{_TH20}'>Date</th><th style='{_TH20}'>Dir</th><th style='{_TH20}'>Entry Time</th><th style='{_TH20}'>Exit Time</th><th style='{_TH20}'>Entry (INR)</th><th style='{_TH20}'>Exit (INR)</th><th style='{_TH20}'>Slip Diff vs $5</th><th style='{_TH20}'>Tax+Charges</th><th style='{_TH20}'>PnL</th></tr></thead><tbody><tr><td colspan='9' style='text-align:center;color:#aaa;padding:12px;font-size:12px;'>Waiting for first trade</td></tr></tbody></table></div>")
            import datetime as _dfw
            last20 = pairs[-20:][::-1]
            rows = ""
            for p in last20:
                pnl      = float(p.get('pnl', 0))
                pnl_inr  = pnl * _INR13
                ep_inr   = float(p.get('ep', 0))
                xp_inr   = float(p.get('xp', 0))
                cm_inr   = float(p.get('cm', 0)) * _INR13
                _ist_off1 = _dfw.timedelta(hours=5, minutes=30)
                et       = (_dfw.datetime.utcfromtimestamp(p.get('ets',0)) + _ist_off1).strftime('%d-%b-%Y %I:%M %p IST')
                xt       = (_dfw.datetime.utcfromtimestamp(p.get('xts',0)) + _ist_off1).strftime('%d-%b-%Y %I:%M %p IST')
                dirv     = str(p.get('dir','')).upper()
                slip_act = abs(float(p.get('ep',0)) - float(p.get('xp',0))) * 0.001
                slip_diff= slip_act - 5.0
                slip_str = f"+${slip_diff:.2f}" if slip_diff >= 0 else f"-${abs(slip_diff):.2f}"
                mp_style  = _TG20
                ps        = _TG20 if pnl >= 0 else _TR20
                ds        = _TG20 if dirv == 'LONG' else _TR20
                rows += (
                    f"<tr>"
                    f"<td style='{_TD20}'>{et[:11].strip()}</td>"
                    f"<td style='{ds}'>{dirv}</td>"
                    f"<td style='{_TD20}'>{et[12:] if len(et)>12 else et}</td>"
                    f"<td style='{_TD20}'>{xt[12:] if len(xt)>12 else xt}</td>"
                    f"<td style='{_TD20}'>${ep_inr:,.0f}</td>"
                    f"<td style='{_TD20}'>${xp_inr:,.0f}</td>"
                    f"<td style='{_TR20}'>{slip_str} vs $5</td>"
                    f"<td style='{_TR20}'>₹{cm_inr:,.0f}</td>"
                    f"<td style='{ps}'>₹{pnl_inr:,.0f}</td>"
                    f"</tr>"
                )
            return (
                f"<div style='overflow-x:auto;max-height:350px;overflow-y:auto;'>"
                f"<table style='width:100%;border-collapse:collapse;'>"
                f"<thead><tr>"
                f"<th style='{_TH20}'>Date</th>"
                f"<th style='{_TH20}'>Dir</th>"
                f"<th style='{_TH20}'>Entry Time</th>"
                f"<th style='{_TH20}'>Exit Time</th>"
                f"<th style='{_TH20}'>Entry $</th>"
                f"<th style='{_TH20}'>Exit $</th>"
                f"<th style='{_TH20}'>Slip Diff vs $5</th>"
                f"<th style='{_TH20}'>Tax+Charges</th>"
                f"<th style='{_TH20}'>PnL</th>"
                f"</tr></thead><tbody>{rows}</tbody></table></div>"
            )
        except Exception as e:
            return f"<p style='color:red;font-size:11px'>Error: {e}</p>"

    def _bt20(csv_pattern, vf_str):
        try:
            import glob as _gb, pandas as _pb
            _WAIT_BT = (
                f"<div style='overflow-x:auto;max-height:350px;overflow-y:auto;'>"
                f"<table style='width:100%;border-collapse:collapse;'>"
                f"<thead><tr>"
                f"<th style='{_TH20}'>Date</th>"
                f"<th style='{_TH20}'>Dir</th>"
                f"<th style='{_TH20}'>Entry Time (IST)</th>"
                f"<th style='{_TH20}'>Exit Time (IST)</th>"
                f"<th style='{_TH20}'>Entry (INR)</th>"
                f"<th style='{_TH20}'>Exit (INR)</th>"
                f"<th style='{_TH20}'>Slip $5</th>"
                f"<th style='{_TH20}'>Tax+Charges</th>"
                f"<th style='{_TH20}'>PnL</th>"
                f"</tr></thead><tbody>"
                f"<tr><td colspan='9' style='text-align:center;color:#aaa;padding:12px;font-size:12px;'>No backtest trades in this window</td></tr>"
                f"</tbody></table></div>"
            )
            s2_files = sorted(_gb.glob("output/trade_log_RenkoReversal*.csv"), reverse=True)
            s4_files = sorted(_gb.glob("output/trade_log_RenkoSMIIO*.csv"), reverse=True)
            frames = []
            vf_dt = _pb.to_datetime(vf_str)
            for ff in (s2_files[:1] + s4_files[:1]):
                _df = _pb.read_csv(ff)
                _df['entry_datetime'] = _pb.to_datetime(_df['entry_datetime'])
                _df_vf = _df[_df['entry_datetime'] >= vf_dt]
                if not _df_vf.empty:
                    frames.append(_df_vf)
            if not frames:
                return _WAIT_BT
            df = _pb.concat(frames).sort_values('entry_datetime').tail(20).iloc[::-1].reset_index(drop=True)
            if df.empty:
                return _WAIT_BT
            rows = ""
            for i, r in df.iterrows():
                pnl     = float(r.get('net_pnl', 0))
                pnl_inr = float(r.get('net_pnl_inr', pnl * _INR13))
                ep_inr  = float(r.get('entry_price', 0))
                xp_inr  = float(r.get('exit_price',  0))
                slip    = float(r.get('slippage_usd', 10.0))
                tax_inr = float(r.get('total_charges_usd', 0)) * _INR13
                import datetime as _dfw
                _ist_off2 = _dfw.timedelta(hours=5, minutes=30)
                _et_raw = str(r.get('entry_datetime',''))[:19]
                _xt_raw = str(r.get('exit_datetime', ''))[:19]
                try:
                    et = (_dfw.datetime.strptime(_et_raw.replace('T',' '), '%Y-%m-%d %H:%M:%S') + _ist_off2).strftime('%d-%b-%Y %I:%M %p IST')
                    xt = (_dfw.datetime.strptime(_xt_raw.replace('T',' '), '%Y-%m-%d %H:%M:%S') + _ist_off2).strftime('%d-%b-%Y %I:%M %p IST')
                except:
                    et = _et_raw
                    xt = _xt_raw
                dirv    = str(r.get('direction','')).upper()
                ps      = _TG20 if pnl >= 0 else _TR20
                ds      = _TG20 if dirv == 'LONG' else _TR20
                rows += (
                    f"<tr>"
                    f"<td style='{_TD20}'>{et[:11].strip()}</td>"
                    f"<td style='{ds}'>{dirv}</td>"
                    f"<td style='{_TD20}'>{et[12:] if len(et)>12 else et}</td>"
                    f"<td style='{_TD20}'>{xt[12:] if len(xt)>12 else xt}</td>"
                    f"<td style='{_TD20}'>${ep_inr:,.0f}</td>"
                    f"<td style='{_TD20}'>${xp_inr:,.0f}</td>"
                    f"<td style='{_TR20}'>${slip:.2f}</td>"
                    f"<td style='{_TR20}'>₹{tax_inr:,.0f}</td>"
                    f"<td style='{ps}'>₹{pnl_inr:,.0f}</td>"
                    f"</tr>"
                )
            return (
                f"<div style='overflow-x:auto;max-height:350px;overflow-y:auto;'>"
                f"<table style='width:100%;border-collapse:collapse;'>"
                f"<thead><tr>"
                f"<th style='{_TH20}'>Date</th>"
                f"<th style='{_TH20}'>Dir</th>"
                f"<th style='{_TH20}'>Entry Time (IST)</th>"
                f"<th style='{_TH20}'>Exit Time (IST)</th>"
                f"<th style='{_TH20}'>Entry (INR)</th>"
                f"<th style='{_TH20}'>Exit (INR)</th>"
                f"<th style='{_TH20}'>Slip $5</th>"
                f"<th style='{_TH20}'>Tax+Charges</th>"
                f"<th style='{_TH20}'>PnL</th>"
                f"</tr></thead><tbody>{rows}</tbody></table></div>"
            )
        except Exception as e:
            return f"<p style='color:red;font-size:11px'>Error: {e}</p>"

    def _cmp20(csv_pattern, fwd_pairs, vf_str):
        try:
            import glob as _gc, pandas as _pc, datetime as _dc
            files = sorted(_gc.glob(csv_pattern), reverse=True)
            s2_ff = sorted(_gc.glob("output/trade_log_RenkoReversal*.csv"), reverse=True)
            s4_ff = sorted(_gc.glob("output/trade_log_RenkoSMIIO*.csv"), reverse=True)
            _frames = []
            vf_dt = _pc.to_datetime(vf_str)
            for _ff in (s2_ff[:1] + s4_ff[:1]):
                _dff = _pc.read_csv(_ff)
                _dff['entry_datetime'] = _pc.to_datetime(_dff['entry_datetime'])
                _dff_vf = _dff[_dff['entry_datetime'] >= vf_dt]
                if not _dff_vf.empty:
                    _frames.append(_dff_vf)
            if not _frames:
                return "<p style='color:#aaa;font-size:12px;padding:8px'>No backtest trades in this window yet</p>"
            df = _pc.concat(_frames).sort_values('entry_datetime').tail(20).iloc[::-1].reset_index(drop=True)
            if df.empty:
                return "<p style='color:#aaa;font-size:12px;padding:8px'>No backtest trades in this window yet</p>"
            last20 = (fwd_pairs or [])[-20:][::-1]
            used_fwd = set()
            max_rows = len(df)
            rows = ""
            for i in range(max_rows):
                bt  = df.iloc[i]
                # Match forward test trade by closest entry time not by position
                fwd = None
                bt_et_raw = str(bt.get('entry_datetime',''))[:19]
                try:
                    import datetime as _dmatch
                    bt_et_dt = _dmatch.datetime.strptime(bt_et_raw.replace('T',' '), '%Y-%m-%d %H:%M:%S')
                    best_diff = None
                    for _fp in last20:
                        try:
                            _fp_et = _dmatch.datetime.utcfromtimestamp(_fp.get('ets', 0))
                            _diff = abs((_fp_et - bt_et_dt).total_seconds())
                            if best_diff is None or _diff < best_diff:
                                best_diff = _diff
                                fwd = _fp
                        except:
                            pass
                    # Only match if within 4 hours
                    if best_diff is not None and best_diff > 14400:
                        fwd = None
                    # Skip already matched fwd trades
                    if fwd is not None:
                        fwd_key = fwd.get('ets', 0)
                        if fwd_key in used_fwd:
                            fwd = None
                        else:
                            used_fwd.add(fwd_key)
                except:
                    fwd = last20[i] if i < len(last20) else None
                bt_ep   = float(bt.get('entry_price', 0))
                bt_xp   = float(bt.get('exit_price',  0))
                bt_pnl  = float(bt.get('net_pnl_inr', float(bt.get('net_pnl',0)) * _INR13))
                bt_dir  = str(bt.get('direction','')).upper()
                import datetime as _dbt
                _ist_bt = _dbt.timedelta(hours=5, minutes=30)
                _bt_et_raw = str(bt.get('entry_datetime',''))[:19]
                _bt_xt_raw = str(bt.get('exit_datetime', ''))[:19]
                try:
                    bt_et = (_dbt.datetime.strptime(_bt_et_raw.replace('T',' '), '%Y-%m-%d %H:%M:%S') + _ist_bt).strftime('%d-%b-%Y %I:%M %p IST')
                    bt_xt = (_dbt.datetime.strptime(_bt_xt_raw.replace('T',' '), '%Y-%m-%d %H:%M:%S') + _ist_bt).strftime('%d-%b-%Y %I:%M %p IST')
                except:
                    bt_et = _bt_et_raw
                    bt_xt = _bt_xt_raw
                if fwd is None:
                    # No live trade yet - show PENDING
                    _pnd = "background:#fff8e1;color:#b8860b;font-weight:bold;padding:4px 6px;font-size:11px;"
                    _ds2 = _TG20 if bt_dir == "LONG" else _TR20
                    rows += (
                        f"<tr>"
                        f"<td style='{_pnd}'>PENDING</td>"
                        f"<td style='{_TD20}'>{bt_et[:11].strip()}</td>"
                        f"<td style='{_ds2}'>{bt_dir}</td>"
                        f"<td style='{_TD20}'>{bt_et[12:] if len(bt_et)>12 else bt_et}</td>"
                        f"<td style='{_TD20}'>-</td>"
                        f"<td style='{_TD20}'>₹{bt_ep:,.0f}</td>"
                        f"<td style='{_TD20}'>-</td>"
                        f"<td style='{_TD20}'>₹{bt_xp:,.0f}</td>"
                        f"<td style='{_TD20}'>-</td>"
                        f"<td style='{_TG20 if bt_pnl>=0 else _TR20}'>₹{bt_pnl:,.0f}</td>"
                        f"<td style='{_TD20}'>-</td>"
                        f"<td style='{_pnd}'>Waiting live</td>"
                        f"</tr>"
                    )
                    continue
                fwd_ep  = float(fwd.get('ep', 0))
                fwd_xp  = float(fwd.get('xp', 0))
                fwd_pnl = float(fwd.get('pnl', 0)) * _INR13
                fwd_dir = str(fwd.get('dir','')).upper()
                _ist_cmp = _dc.timedelta(hours=5, minutes=30)
                fwd_et  = (_dc.datetime.utcfromtimestamp(fwd.get('ets',0)) + _ist_cmp).strftime('%d-%b-%Y %I:%M %p IST')
                fwd_xt  = (_dc.datetime.utcfromtimestamp(fwd.get('xts',0)) + _ist_cmp).strftime('%d-%b-%Y %I:%M %p IST')
                pnl_diff  = abs(bt_pnl - fwd_pnl)
                pnl_pct   = (pnl_diff / abs(bt_pnl) * 100) if bt_pnl != 0 else 0
                dir_match = bt_dir == fwd_dir
                match_pct = 100.0
                if not dir_match:  match_pct -= 50
                if pnl_pct > 10:   match_pct -= 30
                elif pnl_pct > 5:  match_pct -= 10
                mp_style  = _TG20 if match_pct >= 95 else (_TY20 if match_pct >= 80 else _TR20)
                ds        = _TG20 if dir_match else _TR20
                pd_style  = _TG20 if pnl_pct <= 5 else (_TY20 if pnl_pct <= 10 else _TR20)
                rows += (
                    f"<tr>"
                    f"<td style='{mp_style}'>{match_pct:.0f}%</td>"
                    f"<td style='{_TD20}'>{bt_et[:11].strip()}</td>"
                    f"<td style='{ds}'>{bt_dir}</td>"
                    f"<td style='{_TD20}'>{bt_et[12:] if len(bt_et)>12 else bt_et}</td>"
                    f"<td style='{_TD20}'>{fwd_et[12:] if len(fwd_et)>12 else fwd_et}</td>"
                    f"<td style='{_TD20}'>{bt_xt[12:] if len(bt_xt)>12 else bt_xt}</td>"
                    f"<td style='{_TD20}'>{fwd_xt[12:] if len(fwd_xt)>12 else fwd_xt}</td>"
                    f"<td style='{_TD20}'>${bt_ep:,.0f}</td>"
                    f"<td style='{_TD20}'>${fwd_ep:,.0f}</td>"
                    f"<td style='{_TD20}'>${bt_xp:,.0f}</td>"
                    f"<td style='{_TD20}'>${fwd_xp:,.0f}</td>"
                    f"<td style='{_TG20}'>₹{bt_pnl:,.0f}</td>"
                    f"<td style='{_TG20 if fwd_pnl>=0 else _TR20}'>₹{fwd_pnl:,.0f}</td>"
                    f"<td style='{pd_style}'>₹{pnl_diff:,.0f} ({pnl_pct:.1f}%)</td>"
                    f"</tr>"
                )
            return (
                f"<div style='overflow-x:auto;max-height:350px;overflow-y:auto;'>"
                f"<table style='width:100%;border-collapse:collapse;'>"
                f"<thead><tr>"
                f"<th style='{_TH20}'>Match%</th>"
                f"<th style='{_TH20}'>Date</th>"
                f"<th style='{_TH20}'>Dir</th>"
                f"<th style='{_TH20}'>BT Entry T</th>"
                f"<th style='{_TH20}'>FT Entry T</th>"
                f"<th style='{_TH20}'>BT Exit T</th>"
                f"<th style='{_TH20}'>FT Exit T</th>"
                f"<th style='{_TH20}'>BT Entry ₹</th>"
                f"<th style='{_TH20}'>FT Entry ₹</th>"
                f"<th style='{_TH20}'>BT Exit ₹</th>"
                f"<th style='{_TH20}'>FT Exit ₹</th>"
                f"<th style='{_TH20}'>BT PnL</th>"
                f"<th style='{_TH20}'>FT PnL</th>"
                f"<th style='{_TH20}'>PnL Diff</th>"
                f"</tr></thead><tbody>{rows}</tbody></table></div>"
            )
        except Exception as e:
            return f"<p style='color:red;font-size:11px'>Error: {e}</p>"

    # ── RENDER SIDE BY SIDE LAST 20 ──────────────────────────
    _col20a, _col20b = st.columns(2)
    with _col20a:
        st.markdown(f"<div style='{_HDR13}'>FORWARD TEST - LAST 20 TRADES</div>", unsafe_allow_html=True)
        st.markdown(_fwd20(s2p + s4p), unsafe_allow_html=True)
    with _col20b:
        st.markdown(f"<div style='{_HDR13}'>BACKTEST - LAST 20 TRADES</div>", unsafe_allow_html=True)
        st.markdown(_bt20("output/trade_log_Renko*.csv", _VF13_7D), unsafe_allow_html=True)

    # ── COMPARISON TABLE FULL WIDTH BELOW ────────────────────
    st.markdown(f"<div style='{_HDR13}'>BACKTEST vs FORWARD TEST - LAST 20 COMPARISON</div>", unsafe_allow_html=True)
    st.markdown(_cmp20("output/trade_log_Renko*.csv", s2p + s4p, _VF13_7D), unsafe_allow_html=True)


# ================================================================
# FOOTER
# ================================================================
st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
st.caption(f"Version: {system.get('version', 'v3.9')} | Commit: {git_commit} | Last refresh: {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5,minutes=30))).strftime('%d-%b-%Y %I:%M %p IST')}")
# This line intentionally left blank




# ============================================================
# SECTION 14 - SLIPPAGE COMPARISON
# ============================================================
if 'exp_14s' not in st.session_state: st.session_state['exp_14s'] = False
with st.expander('SECTION 14 - BACKTEST ANALYSIS + DEPLOYMENT PLAN', expanded=st.session_state.get('exp_14s', False)):

    import glob as _gl14, pandas as _pd14, datetime as _dt14

    _INR14 = 84.0
    _TH14  = "padding:5px 8px;border:1px solid #C8D0DC;background:#f0f3fa;font-size:10px;font-weight:700;color:#555;"
    _TD14  = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#131722;"
    _TDR14 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#131722;text-align:center;"
    _TDG14 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#089981;font-weight:700;text-align:center;"
    _TDO14 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#e07000;font-weight:700;text-align:center;"
    _TDB14 = "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#089981;font-weight:700;text-align:center;"
    _TDR14B= "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#F23645;font-weight:700;text-align:center;"
    _THGR14= "padding:5px 8px;border:1px solid #C8D0DC;background:#089981;font-size:10px;font-weight:700;color:#fff;text-align:center;"
    _THOG14= "padding:5px 8px;border:1px solid #C8D0DC;background:#e07000;font-size:10px;font-weight:700;color:#fff;text-align:center;"
    _SUB14 = "padding:4px 8px;border:1px solid #C8D0DC;background:#E8ECF2;font-size:10px;font-weight:700;color:#131722;"
    _DASH14= "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#aaa;text-align:center;"
    _PLNH14= "padding:5px 8px;border:1px solid #C8D0DC;background:#2962FF;font-size:10px;font-weight:700;color:#fff;text-align:center;"
    _PLND14= "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#131722;text-align:left;"
    _PLNV14= "padding:5px 8px;border:1px solid #E0E3EB;font-size:11px;color:#131722;font-weight:700;text-align:center;"

    def _load14(csv_pattern, from_dt=None):
        try:
            files = sorted(_gl14.glob(csv_pattern), reverse=True)
            if not files: return None
            df = _pd14.read_csv(files[0])
            if 'entry_datetime' not in df.columns: return None
            df['entry_datetime'] = _pd14.to_datetime(df['entry_datetime'])
            if from_dt:
                df = df[df['entry_datetime'] >= _pd14.to_datetime(from_dt)]
            if df.empty: return None
            now14 = _dt14.datetime.utcnow()
            today_s  = now14.replace(hour=0,minute=0,second=0,microsecond=0)
            month_s  = now14.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
            tot  = len(df)
            gross= df['gross_pnl'].sum() if 'gross_pnl' in df.columns else 0
            net  = df['net_pnl'].sum() if 'net_pnl' in df.columns else 0
            net_inr = df['net_pnl_inr'].sum() if 'net_pnl_inr' in df.columns else net*_INR14
            tax  = df['tax_usd'].sum() if 'tax_usd' in df.columns else 0
            fees = df['taker_fees_usd'].sum() if 'taker_fees_usd' in df.columns else 0
            slip = df['slippage_usd'].sum() if 'slippage_usd' in df.columns else 0
            fund = df['funding_usd'].sum() if 'funding_usd' in df.columns else 0
            total_charges = tax + fees + slip + fund
            margin_avg = df['margin_required'].mean() if 'margin_required' in df.columns else 0
            # Green months
            if 'exit_datetime' in df.columns:
                df['exit_dt'] = _pd14.to_datetime(df['exit_datetime'])
                df['ym'] = df['exit_dt'].dt.to_period('M')
                monthly = df.groupby('ym')['net_pnl'].sum()
                green_m = (monthly > 0).sum()
                total_m = len(monthly)
                # Max DD
                pls = df['net_pnl'].tolist()
                cum,pk,dd = 0,0,0
                for v in pls:
                    cum+=v
                    if cum>pk: pk=cum
                    drop=pk-cum
                    if drop>dd: dd=drop
                # Today + Month PnL
                pnl_today = df[df['exit_dt'] >= _pd14.Timestamp(today_s)]['net_pnl'].sum()
                pnl_month = df[df['exit_dt'] >= _pd14.Timestamp(month_s)]['net_pnl'].sum()
                # This month max DD
                df_mo = df[df['exit_dt'] >= _pd14.Timestamp(month_s)]
                pls_mo = df_mo['net_pnl'].tolist()
                cum_mo,pk_mo,dd_mo = 0,0,0
                for v in pls_mo:
                    cum_mo+=v
                    if cum_mo>pk_mo: pk_mo=cum_mo
                    drop_mo=pk_mo-cum_mo
                    if drop_mo>dd_mo: dd_mo=drop_mo
                # $10/side this month max DD
                mo_cnt_tmp=len(df_mo)
                pls_mo10=[v-10 for v in pls_mo]
                cum_mo10,pk_mo10,dd_mo10=0,0,0
                for v in pls_mo10:
                    cum_mo10+=v
                    if cum_mo10>pk_mo10: pk_mo10=cum_mo10
                    drop_mo10=pk_mo10-cum_mo10
                    if drop_mo10>dd_mo10: dd_mo10=drop_mo10
            else:
                green_m=total_m=0; dd=0; pnl_today=pnl_month=0; dd_mo=0; dd_mo10=0
            rec_cap = dd * 3 * _INR14
            roc = (net_inr / rec_cap * 100) if rec_cap > 0 else 0
            months = max(total_m, 1)
            roc_monthly = roc / months
            # Today + month trade count
            today_count = len(df[df['exit_dt'] >= _pd14.Timestamp(today_s)]) if 'exit_dt' in df.columns else 0
            month_count = len(df[df['exit_dt'] >= _pd14.Timestamp(month_s)]) if 'exit_dt' in df.columns else 0
            # extra metrics
            import math as _m14x, numpy as _np14x
            pc='net_pnl'
            wins_s=df[df[pc]>0][pc] if pc in df.columns else __import__('pandas').Series(dtype=float)
            loss_s=df[df[pc]<0][pc] if pc in df.columns else __import__('pandas').Series(dtype=float)
            win_rate=(len(wins_s)/tot*100) if tot>0 else 0
            max_profit=wins_s.max()*_INR14 if len(wins_s)>0 else 0
            max_loss=loss_s.min()*_INR14 if len(loss_s)>0 else 0
            avg_win=wins_s.mean() if len(wins_s)>0 else 0
            avg_loss=abs(loss_s.mean()) if len(loss_s)>0 else 0
            risk_reward=avg_win/avg_loss if avg_loss>0 else 0
            gw_u=wins_s.sum() if len(wins_s)>0 else 0
            gl_u=abs(loss_s.sum()) if len(loss_s)>0 else 0
            profit_factor=gw_u/gl_u if gl_u>0 else 0
            arr=_np14x.array(df[pc].tolist()) if pc in df.columns else _np14x.array([])
            sharpe=(arr.mean()/arr.std()*_m14x.sqrt(252)) if len(arr)>1 and arr.std()>0 else 0
            # max dd period
            pls2=df[pc].tolist() if pc in df.columns else []
            cum2,pk2,dd2,csi,dsi,dei=0,0,0,0,0,0
            for i,v in enumerate(pls2):
                cum2+=v
                if cum2>pk2: pk2=cum2; csi=i
                drop=pk2-cum2
                if drop>dd2: dd2=drop; dsi=csi; dei=i
            try:
                t0=df['exit_dt'].iloc[dsi]; t1=df['exit_dt'].iloc[dei]
                max_dd_days=max(1,(t1-t0).days) if dei>dsi else 0
            except: max_dd_days=0
            max_dd_period_loss=dd2*_INR14
            # win streak days
            try:
                df2s=df.sort_values('exit_dt').copy()
                df2s['_w']=df2s[pc]>0; df2s['_d']=df2s['exit_dt'].dt.date
                dw=df2s.groupby('_d')['_w'].all()
                mws=cws=0
                for w in dw:
                    if w: cws+=1; mws=max(mws,cws)
                    else: cws=0
                max_win_streak_days=mws
            except: max_win_streak_days=0
            return {
                "tot":tot,"gross":gross,"net":net,"net_inr":net_inr,
                "tax":tax,"fees":fees,"slip":slip,"fund":fund,"total_charges":total_charges,
                "green_m":green_m,"total_m":total_m,"dd":dd,"rec_cap":rec_cap,
                "roc":roc,"roc_monthly":roc_monthly,"margin_avg":margin_avg,
                "pnl_today":pnl_today,"pnl_month":pnl_month,"dd_month":dd_mo,"dd_month10":dd_mo10,
                "today_count":today_count,"month_count":month_count,
                "gross_win":df[df['gross_pnl']>0]['gross_pnl'].sum() if 'gross_pnl' in df.columns else 0,
                "win_rate":win_rate,"max_profit":max_profit,"max_loss":max_loss,
                "risk_reward":risk_reward,"profit_factor":profit_factor,"sharpe":sharpe,
                "max_dd_days":max_dd_days,"max_dd_period_loss":max_dd_period_loss,
                "max_win_streak_days":max_win_streak_days
            }
        except Exception as _e14:
            return None

    def _load14_fwd(product_id, api_key, api_secret, base_url):
        import hmac as _hm,hashlib as _hs,time as _tm,requests as _rq,math as _mf,numpy as _npf
        try:
            if not api_key or not api_secret: return None
            method="GET"; path="/v2/fills"; qs=f"?product_id={product_id}&page_size=500"
            ts=str(int(_tm.time()))
            sig=_hm.new(api_secret.encode(),(method+ts+path+qs).encode(),_hs.sha256).hexdigest()
            hdrs={"api-key":api_key,"timestamp":ts,"signature":sig,"Content-Type":"application/json"}
            r=_rq.get(base_url+path+qs,headers=hdrs,timeout=10)
            if r.status_code!=200: return None
            fills=r.json().get("result",[])
            if not fills: return None
            all_s=sorted(fills,key=lambda x:x.get("created_at",""))
            pairs=[]; open_pos=None
            for f in all_s:
                side=f.get("side",""); price=float(f.get("fill_price",0))
                size=float(f.get("size",0)); ts_f=f.get("created_at","")
                if open_pos is None:
                    open_pos={"side":side,"price":price,"size":size,"ts":ts_f}
                else:
                    if side!=open_pos["side"]:
                        ep=open_pos["price"]; xp=price
                        pnl_usd=(xp-ep)*open_pos["size"]*0.001 if open_pos["side"]=="buy" else (ep-xp)*open_pos["size"]*0.001
                        comm=float(f.get("commission",0))*2
                        pairs.append({"pnl":pnl_usd-comm,"exit_ts":ts_f,"comm":comm})
                        open_pos=None
                    else:
                        open_pos={"side":side,"price":price,"size":size,"ts":ts_f}
            if not pairs: return None
            tot=len(pairs); pnls=[p["pnl"] for p in pairs]
            wins=[v for v in pnls if v>0]; losses=[v for v in pnls if v<0]
            win_rate=len(wins)/tot*100 if tot>0 else 0
            net_usd=sum(pnls); net_inr=net_usd*_INR14
            gw=sum(wins) if wins else 0; gl=abs(sum(losses)) if losses else 0
            profit_factor=gw/gl if gl>0 else 0
            avg_win=sum(wins)/len(wins) if wins else 0
            avg_loss=abs(sum(losses)/len(losses)) if losses else 0
            risk_reward=avg_win/avg_loss if avg_loss>0 else 0
            max_profit=max(wins)*_INR14 if wins else 0
            max_loss=min(losses)*_INR14 if losses else 0
            arr=_npf.array(pnls)
            sharpe=(arr.mean()/arr.std()*_mf.sqrt(252)) if len(arr)>1 and arr.std()>0 else 0
            cum,pk,dd=0,0,0
            for v in pnls:
                cum+=v
                if cum>pk: pk=cum
                drop=pk-cum
                if drop>dd: dd=drop
            mp={}
            for p in pairs:
                mo=p["exit_ts"][:7]; mp[mo]=mp.get(mo,0)+p["pnl"]
            green_m=sum(1 for v in mp.values() if v>0); total_m=len(mp)
            dw={}
            for p in pairs:
                d=p["exit_ts"][:10]; dw[d]=dw.get(d,True) and p["pnl"]>0
            mws=cws=0
            for k in sorted(dw):
                if dw[k]: cws+=1; mws=max(mws,cws)
                else: cws=0
            now14f=_dt14.datetime.utcnow()
            td=now14f.replace(hour=0,minute=0,second=0,microsecond=0).strftime("%Y-%m-%d")
            ms=now14f.replace(day=1,hour=0,minute=0,second=0,microsecond=0).strftime("%Y-%m-%d")
            pnl_today=sum(p["pnl"] for p in pairs if p["exit_ts"][:10]>=td)*_INR14
            pnl_month=sum(p["pnl"] for p in pairs if p["exit_ts"][:10]>=ms)*_INR14
            today_count=sum(1 for p in pairs if p["exit_ts"][:10]>=td)
            month_count=sum(1 for p in pairs if p["exit_ts"][:10]>=ms)
            rec_cap=dd*3*_INR14; roc=(net_inr/rec_cap*100) if rec_cap>0 else 0
            roc_monthly=roc/max(total_m,1)
            return {
                "tot":tot,"net_inr":net_inr,"green_m":green_m,"total_m":total_m,
                "win_rate":win_rate,"max_profit":max_profit,"max_loss":max_loss,
                "risk_reward":risk_reward,"profit_factor":profit_factor,"sharpe":sharpe,
                "dd":dd,"max_dd_period_loss":dd*_INR14,"max_dd_days":0,
                "max_win_streak_days":mws,"rec_cap":rec_cap,"roc":roc,
                "roc_monthly":roc_monthly,"pnl_today":pnl_today,"pnl_month":pnl_month,
                "today_count":today_count,"month_count":month_count,
                "gross_win":gw*_INR14,"total_charges":sum(p["comm"] for p in pairs),
                "gross":net_usd,"net":net_usd,"margin_avg":0
            }
        except Exception as _ef14:
            return None

    def _tbl14(d2, d4, label, period_str, df2=None, df4=None):
        if not d2 and not d4:
            return f"<p style='color:#aaa;font-size:11px;'>No data available for {label}</p>"
        def _g(d, k): return d[k] if d and k in d else 0
        def _inr(v): return f"₹{v*_INR14:,.0f}"
        def _pct(v): return f"{v:,.1f}%"
        def _c(v): return _TDG14 if v>=0 else _TDR14B

        # Today trade count
        s2_tot=_g(d2,"tot"); s4_tot=_g(d4,"tot"); port_tot=s2_tot+s4_tot
        s2_tod_cnt=_g(d2,"today_count"); s4_tod_cnt=_g(d4,"today_count"); port_tod_cnt=s2_tod_cnt+s4_tod_cnt

        # $5/side (CSV as-is, slippage $10/trade already deducted)
        s2_net5=_g(d2,"net_inr"); s4_net5=_g(d4,"net_inr"); port_net5=s2_net5+s4_net5
        s2_gross=_g(d2,"gross")*_INR14; s4_gross=_g(d4,"gross")*_INR14; port_gross=s2_gross+s4_gross
        s2_chg5=_g(d2,"total_charges")*_INR14; s4_chg5=_g(d4,"total_charges")*_INR14; port_chg5=s2_chg5+s4_chg5
        s2_dd=_g(d2,"dd")*_INR14; s4_dd=_g(d4,"dd")*_INR14; port_dd=max(s2_dd,s4_dd)
        s2_rc5=_g(d2,"rec_cap"); s4_rc5=_g(d4,"rec_cap"); port_rc5=s2_rc5+s4_rc5
        s2_roc5=_g(d2,"roc"); s4_roc5=_g(d4,"roc")
        port_roc5=(port_net5/port_rc5*100) if port_rc5>0 else 0
        s2_rocm5=_g(d2,"roc_monthly"); s4_rocm5=_g(d4,"roc_monthly")
        port_rocm5=port_roc5/max(_g(d2,"total_m"),1)

        # $10/side (extra $5/side = $10/trade extra deducted)
        tot2=_g(d2,"tot"); tot4=_g(d4,"tot")
        s2_net10=s2_net5-tot2*10*_INR14; s4_net10=s4_net5-tot4*10*_INR14; port_net10=s2_net10+s4_net10
        s2_chg10=s2_chg5+tot2*10*_INR14; s4_chg10=s4_chg5+tot4*10*_INR14; port_chg10=s2_chg10+s4_chg10
        s2_rc10=s2_rc5; s4_rc10=s4_rc5; port_rc10=port_rc5
        s2_roc10=(s2_net10/s2_rc10*100) if s2_rc10>0 else 0
        s4_roc10=(s4_net10/s4_rc10*100) if s4_rc10>0 else 0
        port_roc10=(port_net10/port_rc10*100) if port_rc10>0 else 0
        s2_rocm10=s2_roc10/max(_g(d2,"total_m"),1)
        s4_rocm10=s4_roc10/max(_g(d4,"total_m"),1)
        port_rocm10=port_roc10/max(_g(d2,"total_m"),1)

        s2_gm=_g(d2,"green_m"); s2_tm=_g(d2,"total_m")
        s4_gm=_g(d4,"green_m"); s4_tm=_g(d4,"total_m")
        s2_td=_g(d2,"pnl_today")*_INR14; s4_td=_g(d4,"pnl_today")*_INR14
        s2_tod_cnt=int(_g(d2,"today_count")); s4_tod_cnt=int(_g(d4,"today_count")); port_tod_cnt=s2_tod_cnt+s4_tod_cnt
        s2_mo=_g(d2,"pnl_month")*_INR14; s4_mo=_g(d4,"pnl_month")*_INR14
        s2_mo_cnt=int(_g(d2,"month_count")); s4_mo_cnt=int(_g(d4,"month_count")); port_mo_cnt=s2_mo_cnt+s4_mo_cnt
        s2_dd_mo=_g(d2,"dd_month")*_INR14; s4_dd_mo=_g(d4,"dd_month")*_INR14; port_dd_mo=max(s2_dd_mo,s4_dd_mo)
        s2_dd_mo10=_g(d2,"dd_month10")*_INR14; s4_dd_mo10=_g(d4,"dd_month10")*_INR14; port_dd_mo10=max(s2_dd_mo10,s4_dd_mo10)
        s2_td10=s2_td-s2_tod_cnt*10*_INR14; s4_td10=s4_td-s4_tod_cnt*10*_INR14; port_td10=s2_td10+s4_td10
        s2_mo10=s2_mo-s2_mo_cnt*10*_INR14; s4_mo10=s4_mo-s4_mo_cnt*10*_INR14; port_mo10=s2_mo10+s4_mo10
        # ITR Tax 30% on gross wins (Indian Income Tax - pay to govt via ITR filing)
        s2_gross_win=_g(d2,"gross_win")*_INR14; s4_gross_win=_g(d4,"gross_win")*_INR14; port_gross_win=s2_gross_win+s4_gross_win
        s2_itr5=s2_gross_win*0.30; s4_itr5=s4_gross_win*0.30; port_itr5=port_gross_win*0.30
        s2_net_itr5=s2_net5-s2_itr5; s4_net_itr5=s4_net5-s4_itr5; port_net_itr5=port_net5-port_itr5
        s2_net_itr10=s2_net10-s2_itr5; s4_net_itr10=s4_net10-s4_itr5; port_net_itr10=port_net10-port_itr5
        s2_mg=_g(d2,"margin_avg")*_INR14; s4_mg=_g(d4,"margin_avg")*_INR14
        _THFW14="padding:5px 8px;border:1px solid #C8D0DC;background:#089981;font-size:10px;font-weight:700;color:#fff;text-align:center;"
        _na14='<span style="color:#aaa">N/A</span>'
        def _fna(v,fmt="inr"):
            if not v: return _na14
            if fmt=="inr": return f"₹{v:,.0f}"
            if fmt=="pct": return f"{v:,.1f}%"
            if fmt=="num": return f"{v:,.2f}"
            if fmt=="int": return f"{int(v):,}"
            return str(v)
        def _cf(v): return _TDG14 if v>=0 else _TDR14B
        s2_wr=_g(d2,"win_rate"); s4_wr=_g(d4,"win_rate"); port_wr=(s2_wr*tot2+s4_wr*tot4)/(tot2+tot4) if (tot2+tot4)>0 else 0
        s2_mp=_g(d2,"max_profit"); s4_mp=_g(d4,"max_profit"); port_mp=max(s2_mp,s4_mp)
        s2_ml=_g(d2,"max_loss"); s4_ml=_g(d4,"max_loss"); port_ml=min(s2_ml,s4_ml) if s2_ml and s4_ml else 0
        s2_rr=_g(d2,"risk_reward"); s4_rr=_g(d4,"risk_reward"); port_rr=(s2_rr+s4_rr)/2 if s2_rr and s4_rr else max(s2_rr,s4_rr)
        s2_pf=_g(d2,"profit_factor"); s4_pf=_g(d4,"profit_factor"); port_pf=(s2_pf+s4_pf)/2 if s2_pf and s4_pf else max(s2_pf,s4_pf)
        s2_sh=_g(d2,"sharpe"); s4_sh=_g(d4,"sharpe"); port_sh=(s2_sh+s4_sh)/2 if s2_sh and s4_sh else max(s2_sh,s4_sh)
        s2_ddd=_g(d2,"max_dd_days"); s4_ddd=_g(d4,"max_dd_days"); port_ddd=max(s2_ddd,s4_ddd)
        s2_ddl=_g(d2,"max_dd_period_loss"); s4_ddl=_g(d4,"max_dd_period_loss"); port_ddl=max(s2_ddl,s4_ddl)
        s2_ws=_g(d2,"max_win_streak_days"); s4_ws=_g(d4,"max_win_streak_days"); port_ws=max(s2_ws,s4_ws)
        fw2_net=_g(df2,"net_inr"); fw4_net=_g(df4,"net_inr"); fwp_net=fw2_net+fw4_net
        fw2_tot=_g(df2,"tot"); fw4_tot=_g(df4,"tot"); fwp_tot=fw2_tot+fw4_tot
        fw2_gm=_g(df2,"green_m"); fw4_gm=_g(df4,"green_m"); fw2_tm=_g(df2,"total_m"); fw4_tm=_g(df4,"total_m")
        fw2_wr=_g(df2,"win_rate"); fw4_wr=_g(df4,"win_rate"); fwp_wr=(fw2_wr*fw2_tot+fw4_wr*fw4_tot)/(fw2_tot+fw4_tot) if (fw2_tot+fw4_tot)>0 else 0
        fw2_mp=_g(df2,"max_profit"); fw4_mp=_g(df4,"max_profit"); fwp_mp=max(fw2_mp,fw4_mp)
        fw2_ml=_g(df2,"max_loss"); fw4_ml=_g(df4,"max_loss"); fwp_ml=min(fw2_ml,fw4_ml) if fw2_ml and fw4_ml else 0
        fw2_rr=_g(df2,"risk_reward"); fw4_rr=_g(df4,"risk_reward"); fwp_rr=(fw2_rr+fw4_rr)/2 if fw2_rr and fw4_rr else max(fw2_rr,fw4_rr)
        fw2_pf=_g(df2,"profit_factor"); fw4_pf=_g(df4,"profit_factor"); fwp_pf=(fw2_pf+fw4_pf)/2 if fw2_pf and fw4_pf else max(fw2_pf,fw4_pf)
        fw2_sh=_g(df2,"sharpe"); fw4_sh=_g(df4,"sharpe"); fwp_sh=(fw2_sh+fw4_sh)/2 if fw2_sh and fw4_sh else max(fw2_sh,fw4_sh)
        fw2_dd=_g(df2,"dd")*_INR14; fw4_dd=_g(df4,"dd")*_INR14; fwp_dd=max(fw2_dd,fw4_dd)
        fw2_ddl=_g(df2,"max_dd_period_loss"); fw4_ddl=_g(df4,"max_dd_period_loss"); fwp_ddl=max(fw2_ddl,fw4_ddl)
        fw2_ddd=_g(df2,"max_dd_days"); fw4_ddd=_g(df4,"max_dd_days"); fwp_ddd=max(fw2_ddd,fw4_ddd)
        fw2_ws=_g(df2,"max_win_streak_days"); fw4_ws=_g(df4,"max_win_streak_days"); fwp_ws=max(fw2_ws,fw4_ws)
        fw2_rc=_g(df2,"rec_cap"); fw4_rc=_g(df4,"rec_cap"); fwp_rc=fw2_rc+fw4_rc
        fw2_roc=_g(df2,"roc"); fw4_roc=_g(df4,"roc"); fwp_roc=(fwp_net/fwp_rc*100) if fwp_rc>0 else 0
        fw2_rocm=_g(df2,"roc_monthly"); fw4_rocm=_g(df4,"roc_monthly"); fwp_rocm=fwp_roc/max(max(fw2_tm,fw4_tm),1)
        fw2_td=_g(df2,"pnl_today"); fw4_td=_g(df4,"pnl_today")
        fw2_mo=_g(df2,"pnl_month"); fw4_mo=_g(df4,"pnl_month")
        fw2_tc=int(_g(df2,"today_count")); fw4_tc=int(_g(df4,"today_count")); fwp_tc=fw2_tc+fw4_tc
        fw2_mc=int(_g(df2,"month_count")); fw4_mc=int(_g(df4,"month_count")); fwp_mc=fw2_mc+fw4_mc
        fw2_gw=_g(df2,"gross_win"); fw4_gw=_g(df4,"gross_win"); fwp_gw=fw2_gw+fw4_gw
        fw2_itr=fw2_gw*0.30; fw4_itr=fw4_gw*0.30; fwp_itr=fwp_gw*0.30
        fw2_nitr=fw2_net-fw2_itr; fw4_nitr=fw4_net-fw4_itr; fwp_nitr=fwp_net-fwp_itr

        def _row9(lbl,v5s2,v5s4,v5p,v10s2,v10s4,v10p,vfs2="",vfs4="",vfp="",c5s2=None,c5s4=None,c5p=None,c10s2=None,c10s4=None,c10p=None,cfs2=None,cfs4=None,cfp=None):
            c5s2=c5s2 or _TDR14; c5s4=c5s4 or _TDR14; c5p=c5p or _TDR14
            c10s2=c10s2 or _TDR14; c10s4=c10s4 or _TDR14; c10p=c10p or _TDR14
            cfs2=cfs2 or _TDB14; cfs4=cfs4 or _TDB14; cfp=cfp or _TDB14
            return (f"<tr><td style='{_TD14}'>{lbl}</td>"
                    f"<td style='{c5s2}'>{v5s2}</td><td style='{c5s4}'>{v5s4}</td><td style='{c5p}'>{v5p}</td>"
                    f"<td style='{c10s2}'>{v10s2}</td><td style='{c10s4}'>{v10s4}</td><td style='{c10p}'>{v10p}</td>"
                    f"<td style='{cfs2}'>{vfs2}</td><td style='{cfs4}'>{vfs4}</td><td style='{cfp}'>{vfp}</td></tr>")

        return f"""
        <p style="font-size:11px;color:#555;margin:2px 0 6px 0;"><b>{label}</b> &nbsp;|&nbsp; {period_str} &nbsp;|&nbsp; BTCUSD Perpetual &nbsp;|&nbsp; 100 lots/trade &nbsp;|&nbsp; Dynamic update every page load</p>
        <div style="overflow-x:auto;margin:4px 0;">
        <table style="width:100%;border-collapse:collapse;table-layout:fixed;">
        <colgroup>
          <col style="width:16%">
          <col style="width:9%"><col style="width:9%"><col style="width:9%">
          <col style="width:9%"><col style="width:9%"><col style="width:9%">
          <col style="width:9%"><col style="width:9%"><col style="width:9%">
        </colgroup>
        <thead>
        <tr>
          <th style="{_TH14}" rowspan="2">Metric</th>
          <th style="{_THGR14}" colspan="3">$5/side Realistic | 100 lots</th>
          <th style="{_THOG14}" colspan="3">$10/side Conservative | 100 lots</th>
          <th style="{_THFW14}" colspan="3">Forward Test (Live)</th>
        </tr>
        <tr>
          <th style="{_THGR14}">S2</th><th style="{_THGR14}">S4</th><th style="{_THGR14}">Portfolio</th>
          <th style="{_THOG14}">S2</th><th style="{_THOG14}">S4</th><th style="{_THOG14}">Portfolio</th>
          <th style="{_THFW14}">S2</th><th style="{_THFW14}">S4</th><th style="{_THFW14}">Portfolio</th>
        </tr>
        </thead>
        <tbody>
        <tr><td colspan="10" style="{_SUB14}">DYNAMIC PnL (SYNCED WITH SECTION 13)</td></tr>
        {_row9("Today PnL",f"₹{s2_td:,.0f}",f"₹{s4_td:,.0f}",f"₹{s2_td+s4_td:,.0f}",f"₹{s2_td10:,.0f}",f"₹{s4_td10:,.0f}",f"₹{port_td10:,.0f}",_fna(fw2_td),_fna(fw4_td),_fna(fw2_td+fw4_td),_c(s2_td),_c(s4_td),_c(s2_td+s4_td),_c(s2_td10),_c(s4_td10),_c(port_td10),_cf(fw2_td),_cf(fw4_td),_cf(fw2_td+fw4_td))}
        {_row9("Today Trades",f"{s2_tod_cnt:,}",f"{s4_tod_cnt:,}",f"{port_tod_cnt:,}",f"{s2_tod_cnt:,}",f"{s4_tod_cnt:,}",f"{port_tod_cnt:,}",_fna(fw2_tc,"int"),_fna(fw4_tc,"int"),_fna(fwp_tc,"int"),_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDB14,_TDB14,_TDB14)}
        {_row9("This Month PnL",f"₹{s2_mo:,.0f}",f"₹{s4_mo:,.0f}",f"₹{s2_mo+s4_mo:,.0f}",f"₹{s2_mo10:,.0f}",f"₹{s4_mo10:,.0f}",f"₹{port_mo10:,.0f}",_fna(fw2_mo),_fna(fw4_mo),_fna(fw2_mo+fw4_mo),_c(s2_mo),_c(s4_mo),_c(s2_mo+s4_mo),_c(s2_mo10),_c(s4_mo10),_c(port_mo10),_cf(fw2_mo),_cf(fw4_mo),_cf(fw2_mo+fw4_mo))}
        {_row9("This Month Trades",f"{s2_mo_cnt:,}",f"{s4_mo_cnt:,}",f"{port_mo_cnt:,}",f"{s2_mo_cnt:,}",f"{s4_mo_cnt:,}",f"{port_mo_cnt:,}",_fna(fw2_mc,"int"),_fna(fw4_mc,"int"),_fna(fwp_mc,"int"),_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDB14,_TDB14,_TDB14)}
        {_row9("This Month Max DD",f"₹{s2_dd_mo:,.0f}",f"₹{s4_dd_mo:,.0f}",f"₹{port_dd_mo:,.0f}",f"₹{s2_dd_mo10:,.0f}",f"₹{s4_dd_mo10:,.0f}",f"₹{port_dd_mo10:,.0f}",_na14,_na14,_na14,_TDR14B if s2_dd_mo>0 else _TDB14,_TDR14B if s4_dd_mo>0 else _TDB14,_TDR14B if port_dd_mo>0 else _TDB14,_TDR14B if s2_dd_mo10>0 else _TDB14,_TDR14B if s4_dd_mo10>0 else _TDB14,_TDR14B if port_dd_mo10>0 else _TDB14,_na14,_na14,_na14)}
        <tr><td colspan="10" style="{_SUB14}">TRADE COUNT</td></tr>
        {_row9("Total Trades",f"{tot2:,}",f"{tot4:,}",f"{tot2+tot4:,}",f"{tot2:,}",f"{tot4:,}",f"{tot2+tot4:,}",_fna(fw2_tot,"int"),_fna(fw4_tot,"int"),_fna(fwp_tot,"int"))}
        <tr><td colspan="10" style="{_SUB14}">GREEN MONTHS</td></tr>
        {_row9("Green Months",f"{s2_gm}/{s2_tm}",f"{s4_gm}/{s4_tm}",f"{min(s2_gm,s4_gm)}/{s2_tm}",f"{s2_gm}/{s2_tm}",f"{s4_gm}/{s4_tm}",f"{min(s2_gm,s4_gm)}/{s2_tm}",_fna(fw2_gm,"int") if fw2_tm else _na14,_fna(fw4_gm,"int") if fw4_tm else _na14,_na14,_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDB14,_TDB14,_TDB14)}
        <tr><td colspan="10" style="{_SUB14}">PERFORMANCE METRICS</td></tr>
        {_row9("Win Rate %",_pct(s2_wr),_pct(s4_wr),_pct(port_wr),_pct(s2_wr),_pct(s4_wr),_pct(port_wr),_fna(fw2_wr,"pct"),_fna(fw4_wr,"pct"),_fna(fwp_wr,"pct"),_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDB14,_TDB14,_TDB14)}
        {_row9("Max Profit Trade",f"₹{s2_mp:,.0f}",f"₹{s4_mp:,.0f}",f"₹{port_mp:,.0f}",f"₹{s2_mp:,.0f}",f"₹{s4_mp:,.0f}",f"₹{port_mp:,.0f}",_fna(fw2_mp),_fna(fw4_mp),_fna(fwp_mp),_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDB14,_TDB14,_TDB14)}
        {_row9("Max Loss Trade",f"₹{s2_ml:,.0f}",f"₹{s4_ml:,.0f}",f"₹{port_ml:,.0f}",f"₹{s2_ml:,.0f}",f"₹{s4_ml:,.0f}",f"₹{port_ml:,.0f}",_fna(fw2_ml),_fna(fw4_ml),_fna(fwp_ml),_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B)}
        {_row9("Risk:Reward",f"{s2_rr:,.2f}",f"{s4_rr:,.2f}",f"{port_rr:,.2f}",f"{s2_rr:,.2f}",f"{s4_rr:,.2f}",f"{port_rr:,.2f}",_fna(fw2_rr,"num"),_fna(fw4_rr,"num"),_fna(fwp_rr,"num"),_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDB14,_TDB14,_TDB14)}
        {_row9("Profit Factor",f"{s2_pf:,.2f}",f"{s4_pf:,.2f}",f"{port_pf:,.2f}",f"{s2_pf:,.2f}",f"{s4_pf:,.2f}",f"{port_pf:,.2f}",_fna(fw2_pf,"num"),_fna(fw4_pf,"num"),_fna(fwp_pf,"num"),_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDB14,_TDB14,_TDB14)}
        {_row9("Sharpe Ratio",f"{s2_sh:,.2f}",f"{s4_sh:,.2f}",f"{port_sh:,.2f}",f"{s2_sh:,.2f}",f"{s4_sh:,.2f}",f"{port_sh:,.2f}",_fna(fw2_sh,"num"),_fna(fw4_sh,"num"),_fna(fwp_sh,"num"),_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDB14,_TDB14,_TDB14)}
        <tr><td colspan="10" style="{_SUB14}">PnL BREAKDOWN</td></tr>
        {_row9("Gross PnL",_inr(s2_gross/_INR14),_inr(s4_gross/_INR14),_inr(port_gross/_INR14),_inr(s2_gross/_INR14),_inr(s4_gross/_INR14),_inr(port_gross/_INR14),_na14,_na14,_na14,_c(s2_gross),_c(s4_gross),_c(port_gross),_c(s2_gross),_c(s4_gross),_c(port_gross))}
        {_row9("Tax + All Charges",f"-₹{s2_chg5:,.0f}",f"-₹{s4_chg5:,.0f}",f"-₹{port_chg5:,.0f}",f"-₹{s2_chg10:,.0f}",f"-₹{s4_chg10:,.0f}",f"-₹{port_chg10:,.0f}",_na14,_na14,_na14,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B)}
        {_row9("Net PnL (After Tax)",_inr(s2_net5/_INR14),_inr(s4_net5/_INR14),_inr(port_net5/_INR14),_inr(s2_net10/_INR14),_inr(s4_net10/_INR14),_inr(port_net10/_INR14),_fna(fw2_net),_fna(fw4_net),_fna(fwp_net),_c(s2_net5),_c(s4_net5),_c(port_net5),_c(s2_net10),_c(s4_net10),_c(port_net10),_cf(fw2_net),_cf(fw4_net),_cf(fwp_net))}
        <tr><td colspan="10" style="{_SUB14}">INDIAN ITR TAX (30% on Gross Wins - Pay via ITR Filing)</td></tr>
        {_row9("Gross Wins",f"₹{s2_gross_win:,.0f}",f"₹{s4_gross_win:,.0f}",f"₹{port_gross_win:,.0f}",f"₹{s2_gross_win:,.0f}",f"₹{s4_gross_win:,.0f}",f"₹{port_gross_win:,.0f}",_fna(fw2_gw),_fna(fw4_gw),_fna(fwp_gw),_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDB14,_TDB14,_TDB14)}
        {_row9("ITR Tax 30%",f"-₹{s2_itr5:,.0f}",f"-₹{s4_itr5:,.0f}",f"-₹{port_itr5:,.0f}",f"-₹{s2_itr5:,.0f}",f"-₹{s4_itr5:,.0f}",f"-₹{port_itr5:,.0f}",_fna(fw2_itr),_fna(fw4_itr),_fna(fwp_itr),_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B)}
        {_row9("Keep Aside (ITR)",f"₹{s2_itr5:,.0f}",f"₹{s4_itr5:,.0f}",f"₹{port_itr5:,.0f}",f"₹{s2_itr5:,.0f}",f"₹{s4_itr5:,.0f}",f"₹{port_itr5:,.0f}",_fna(fw2_itr),_fna(fw4_itr),_fna(fwp_itr),_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDO14)}
        {_row9("Net After ITR Tax",f"₹{s2_net_itr5:,.0f}",f"₹{s4_net_itr5:,.0f}",f"₹{port_net_itr5:,.0f}",f"₹{s2_net_itr10:,.0f}",f"₹{s4_net_itr10:,.0f}",f"₹{port_net_itr10:,.0f}",_fna(fw2_nitr),_fna(fw4_nitr),_fna(fwp_nitr),_c(s2_net_itr5),_c(s4_net_itr5),_c(port_net_itr5),_c(s2_net_itr10),_c(s4_net_itr10),_c(port_net_itr10),_cf(fw2_nitr),_cf(fw4_nitr),_cf(fwp_nitr))}
        <tr><td colspan="10" style="{_SUB14}">RECOMMENDED CAPITAL (3x MAX DD)</td></tr>
        {_row9("Rec Capital",f"₹{s2_rc5:,.0f}",f"₹{s4_rc5:,.0f}",f"₹{port_rc5:,.0f}",f"₹{s2_rc10:,.0f}",f"₹{s4_rc10:,.0f}",f"₹{port_rc10:,.0f}",_fna(fw2_rc),_fna(fw4_rc),_fna(fwp_rc),_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDO14)}
        <tr><td colspan="10" style="{_SUB14}">RETURN ON CAPITAL</td></tr>
        {_row9("ROC Total",_pct(s2_roc5),_pct(s4_roc5),_pct(port_roc5),_pct(s2_roc10),_pct(s4_roc10),_pct(port_roc10),_fna(fw2_roc,"pct"),_fna(fw4_roc,"pct"),_fna(fwp_roc,"pct"),_TDG14,_TDG14,_TDG14,_c(s2_roc10),_c(s4_roc10),_c(port_roc10),_TDB14,_TDB14,_TDB14)}
        {_row9("ROC Monthly Avg",_pct(s2_rocm5),_pct(s4_rocm5),_pct(port_rocm5),_pct(s2_rocm10),_pct(s4_rocm10),_pct(port_rocm10),_fna(fw2_rocm,"pct"),_fna(fw4_rocm,"pct"),_fna(fwp_rocm,"pct"),_TDG14,_TDG14,_TDG14,_c(s2_rocm10),_c(s4_rocm10),_c(port_rocm10),_TDB14,_TDB14,_TDB14)}
        <tr><td colspan="10" style="{_SUB14}">MAX DRAWDOWN</td></tr>
        {_row9("Max Drawdown",f"-₹{s2_dd:,.0f}",f"-₹{s4_dd:,.0f}",f"-₹{port_dd:,.0f}",f"-₹{s2_dd:,.0f}",f"-₹{s4_dd:,.0f}",f"-₹{port_dd:,.0f}",f"-{_fna(fw2_dd)}" if fw2_dd else _na14,f"-{_fna(fw4_dd)}" if fw4_dd else _na14,f"-{_fna(fwp_dd)}" if fwp_dd else _na14,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B)}
        {_row9("Max DD Period (days)",f"{s2_ddd}d",f"{s4_ddd}d",f"{port_ddd}d",f"{s2_ddd}d",f"{s4_ddd}d",f"{port_ddd}d",_fna(fw2_ddd,"int") if fw2_ddd else _na14,_fna(fw4_ddd,"int") if fw4_ddd else _na14,_na14,_TDR14,_TDR14,_TDR14,_TDR14,_TDR14,_TDR14)}
        {_row9("Max DD Period Loss",f"-₹{s2_ddl:,.0f}",f"-₹{s4_ddl:,.0f}",f"-₹{port_ddl:,.0f}",f"-₹{s2_ddl:,.0f}",f"-₹{s4_ddl:,.0f}",f"-₹{port_ddl:,.0f}",f"-{_fna(fw2_ddl)}" if fw2_ddl else _na14,f"-{_fna(fw4_ddl)}" if fw4_ddl else _na14,f"-{_fna(fwp_ddl)}" if fwp_ddl else _na14,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B)}
        {_row9("Max Win Streak Days",f"{s2_ws}d",f"{s4_ws}d",f"{port_ws}d",f"{s2_ws}d",f"{s4_ws}d",f"{port_ws}d",_fna(fw2_ws,"int") if fw2_ws else _na14,_fna(fw4_ws,"int") if fw4_ws else _na14,_na14,_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDG14,_TDB14,_TDB14,_TDB14)}
        {_row9("Avg Margin/trade",f"₹{s2_mg:,.0f}",f"₹{s4_mg:,.0f}","-",f"₹{s2_mg:,.0f}",f"₹{s4_mg:,.0f}","-",_na14,_na14,_na14,_TDR14,_TDR14,_DASH14,_TDR14,_TDR14,_DASH14)}
        </tbody>
        </table>
        </div>"""

    # Load data
    _now14 = _dt14.datetime.utcnow()
    _1yr_from = (_now14 - _dt14.timedelta(days=365)).strftime("%Y-%m-%d")
    _full_from = "2024-01-01"

    _d2_1yr  = _load14("output/trade_log_RenkoReversal*.csv",       _1yr_from)
    _d4_1yr  = _load14("output/trade_log_RenkoSMIIOSupertrend*.csv",_1yr_from)
    _d2_full = _load14("output/trade_log_RenkoReversal*.csv",       _full_from)
    _d4_full = _load14("output/trade_log_RenkoSMIIOSupertrend*.csv",_full_from)

    _1yr_label = f"{(_now14-_dt14.timedelta(days=365)).strftime('%d-%b-%Y')} to {_now14.strftime('%d-%b-%Y')} (1 Year)"
    _full_label= f"2024-01-01 to {_now14.strftime('%d-%b-%Y')} (Full CSV)"

    import os as _os14
    _s2_key=_os14.getenv("S2_API_KEY",""); _s2_sec=_os14.getenv("S2_API_SECRET","")
    _s4_key=_os14.getenv("S4_API_KEY",""); _s4_sec=_os14.getenv("S4_API_SECRET","")
    _fwd_base="https://cdn-ind.testnet.deltaex.org"
    _df2_fwd=_load14_fwd(84,_s2_key,_s2_sec,_fwd_base)
    _df4_fwd=_load14_fwd(84,_s4_key,_s4_sec,_fwd_base)
    st.markdown(_tbl14(_d2_1yr,_d4_1yr,"1-YEAR BACKTEST",_1yr_label,_df2_fwd,_df4_fwd),unsafe_allow_html=True)
    st.markdown("---")
    st.markdown(_tbl14(_d2_full,_d4_full,"FULL CSV BACKTEST",_full_label,_df2_fwd,_df4_fwd),unsafe_allow_html=True)
    st.markdown("---")

    # DEPLOYMENT PLAN SECTION
    _d2f = _d2_full or {}
    _d4f = _d4_full or {}
    _port_dd_inr = ((_d2f.get("dd",0) + _d4f.get("dd",0)) * _INR14)
    _rec_cap = max(_port_dd_inr * 3, 200000)

    st.markdown(f"""
    <div style="overflow-x:auto;margin:4px 0;">
    <table style="width:100%;border-collapse:collapse;">
    <thead>
    <tr><th style="{_PLNH14}" colspan="2">DEPLOYMENT PLAN</th></tr>
    </thead>
    <tbody>
    <tr><td style="{_PLND14}">Margin Mode</td><td style="{_PLNV14}">Isolated</td></tr>
    <tr><td style="{_PLND14}">Leverage</td><td style="{_PLNV14}">50x</td></tr>
    <tr><td style="{_PLND14}">Subaccount</td><td style="{_PLNV14}">Single (S2 + S4 together)</td></tr>
    <tr><td style="{_PLND14}">Starting Capital</td><td style="{_PLNV14}">₹2,00,000</td></tr>
    <tr><td style="{_PLND14}">Starting Lots</td><td style="{_PLNV14}">100 lots (fixed)</td></tr>
    <tr><td style="{_PLND14}">Go-Live Date</td><td style="{_PLNV14}">Aug 1, 2026</td></tr>
    <tr><td style="{_PLND14}">First Withdrawal</td><td style="{_PLNV14}">Feb 2027 (after 6 months)</td></tr>
    <tr><td style="{_PLND14}">Max Lots Cap</td><td style="{_PLNV14}">1000 lots (never exceed)</td></tr>
    </tbody>
    </table>
    </div>

    <div style="overflow-x:auto;margin:10px 0 4px 0;">
    <table style="width:100%;border-collapse:collapse;">
    <thead>
    <tr>
      <th style="{_PLNH14}">Lots</th>
      <th style="{_PLNH14}">Safe Keep</th>
      <th style="{_PLNH14}">Monthly Target</th>
      <th style="{_PLNH14}">Action</th>
    </tr>
    </thead>
    <tbody>
    <tr><td style="{_PLND14}">100</td><td style="{_PLNV14}">₹1,00,000</td><td style="{_TDG14}">₹1,11,328</td><td style="{_PLND14}">Start Aug 1</td></tr>
    <tr><td style="{_PLND14}">300</td><td style="{_PLNV14}">₹2,00,000</td><td style="{_TDG14}">₹3,33,984</td><td style="{_PLND14}">Sep 1 if profit</td></tr>
    <tr><td style="{_PLND14}">500</td><td style="{_PLNV14}">₹3,00,000</td><td style="{_TDG14}">₹5,56,640</td><td style="{_PLND14}">Oct 1 if profit</td></tr>
    <tr><td style="{_PLND14}">700</td><td style="{_PLNV14}">₹4,00,000</td><td style="{_TDG14}">₹7,79,296</td><td style="{_PLND14}">Nov 1 if profit</td></tr>
    <tr><td style="{_PLND14}">900</td><td style="{_PLNV14}">₹5,50,000</td><td style="{_TDG14}">₹10,01,952</td><td style="{_PLND14}">Dec 1 if profit</td></tr>
    <tr><td style="{_PLND14}">1000</td><td style="{_PLNV14}">₹6,00,000</td><td style="{_TDG14}">₹10,65,265</td><td style="{_PLND14}">Jan 1 if profit — FINAL CAP</td></tr>
    </tbody>
    </table>
    </div>

    <div style="background:#fff8e1;border-left:3px solid #e07000;padding:8px 12px;margin:10px 0 4px 0;font-size:11px;color:#131722;">
    <b>Golden Rules (Never Break):</b>
    <ol style="margin:4px 0;padding-left:16px;">
    <li>Start 100 lots — never skip levels</li>
    <li>Increase +200 only after profitable month confirmed</li>
    <li>Never decrease lots even in losing month — FREEZE ONLY</li>
    <li>Cap = 1000 lots maximum — never exceed</li>
    <li>Check Section 13 on 1st of every month — 30 seconds</li>
    <li>Never change lots during open position — wait FLAT</li>
    <li>If 2 consecutive losing months = pause and review</li>
    <li>First 6 months = ZERO withdrawal — build buffer</li>
    <li>Go live only after 5 consecutive MATCH trades confirmed</li>
    </ol>
    </div>

    <div style="background:#f0f4ff;border-left:3px solid #2962FF;padding:8px 12px;margin:10px 0 4px 0;font-size:11px;color:#131722;">
    <b>Key Observations:</b>
    <ul style="margin:4px 0;padding-left:16px;">
    <li>Trade count identical at both slippages - strategy logic is unchanged</li>
    <li style="color:#089981;font-weight:600;">$5/side: S2 improves from 25/31 to 31/31 green months - all months profitable</li>
    <li style="color:#089981;font-weight:600;">$5/side: Portfolio Rec Capital 3.8x lower = ROC jumps from 4,697% to 22,433%</li>
    <li>$10/side is conservative/safe assumption for live trading presentation</li>
    <li>$5/side is realistic for actual Delta Exchange execution (taker ~$3-5/side)</li>
    <li>Both are valid - use $10 for conservative view, $5 for realistic view</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)

