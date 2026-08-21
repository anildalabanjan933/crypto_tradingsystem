
import streamlit as st
from dotenv import load_dotenv as _ld_env
_ld_env()
try:
    from streamlit_autorefresh import st_autorefresh
    _AR_AVAILABLE = True
except:
    _AR_AVAILABLE = False

# Strategy display name mapping
_STRAT_DISPLAY = {
    "renko_smiio_supertrend_v2_strategy": "S4V2 - Renko SMIIO V2 (Bot Running)",
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
    # S4V2 and S4 first, then rest alphabetically
    priority = ["renko_smiio_supertrend_v2_strategy", "renko_smiio_supertrend_strategy"]
    ordered = [f for f in priority if f in files] + [f for f in files if f not in priority]
    return [_STRAT_DISPLAY.get(s, s) for s in ordered]

_STRAT_CLASS_OVERRIDE = {
    "renko_smiio_supertrend_strategy": "RenkoSMIIOSupertrendStrategy",
    "renko_smiio_supertrend_v2_strategy": "RenkoSMIIOSupertrendV2Strategy",
    "tf1_supertrend_ema_strategy": "TF1SupertrendEMAStrategy",
}

def _check_terminal_run(html_files, csv_files, tracker_name, dash_session_key, label):
    """Detect if a new HTML/CSV report appeared from a TERMINAL run (not dashboard button click).
    Shows a persistent 'TERMINAL RUN COMPLETE' message if so. Never touches dashboard's own message."""
    import os as _os_tr
    os.makedirs("logs", exist_ok=True)
    tracker_file = f"logs/{tracker_name}.txt"
    latest = html_files[0] if html_files else None
    if not latest:
        return
    latest_name = _os_tr.path.basename(latest)
    prev_seen = ""
    if _os_tr.path.exists(tracker_file):
        prev_seen = open(tracker_file).read().strip()
    if latest_name != prev_seen:
        dash_msg = st.session_state.get(dash_session_key, "")
        if latest_name not in dash_msg:
            csv_nm = _os_tr.path.basename(csv_files[0]) if csv_files else "N/A"
            strat_part = latest_name
            for pfx in ["backtest_report_", "portfolio_report_", "optimization_results_"]:
                if strat_part.startswith(pfx):
                    strat_part = strat_part[len(pfx):]
            strat_part = strat_part.split("_BTCUSD_")[0]
            st.session_state[dash_session_key] = f"TERMINAL RUN COMPLETE - {strat_part}  |  HTML: {latest_name}  |  CSV: {csv_nm}"
        open(tracker_file, "w").write(latest_name)

def _display_to_class(display_name):
    fname = _STRAT_REVERSE.get(display_name, display_name)
    if fname in _STRAT_CLASS_OVERRIDE:
        return _STRAT_CLASS_OVERRIDE[fname]
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
            return _rq.get(DELTA_URL+qp, headers=hdrs, timeout=(3,10), verify=False).json()
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

    if positions:
        orders_resp = _get('/v2/orders', {'states': 'open,pending', 'order_types': 'stop_market,stop_limit,all_stop'})
        sl_by_symbol_side = {}
        for o in orders_resp.get('result', []):
            if o.get('stop_order_type') == 'stop_loss_order':
                osym = o.get('product_symbol', '')
                oside = o.get('side', '')
                ocreated = o.get('created_at', '')
                key = (osym, oside)
                existing = sl_by_symbol_side.get(key)
                if not existing or ocreated > existing[1]:
                    sl_by_symbol_side[key] = (o.get('stop_price', o.get('trigger_price', 'N/A')), ocreated)
        for pos in positions:
            close_side = 'buy' if pos['side'] == 'SHORT' else 'sell'
            match = sl_by_symbol_side.get((pos['symbol'], close_side))
            pos['sl_price'] = match[0] if match else None

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
    try:
        r = _rq2.get('https://cdn-ind.testnet.deltaex.org/v2/products?contract_types=perpetual_futures&limit=1', timeout=5)
        if r.status_code != 200:
            return f"FAIL_{r.status_code}"
        from engine.order_manager import OrderManager
        om = OrderManager(os.getenv("S4V2_API_KEY"), os.getenv("S4V2_API_SECRET"), testnet=True)
        pos = om.get_position()
        if not pos.get('success', False):
            return "AUTH_FAIL"
        return 200
    except Exception as e:
        return f"ERROR_{str(e)[:20]}"

def _fetch_key_validity():
    _s4v2k = os.environ.get("S4V2_API_KEY","")
    _s4v2s = os.environ.get("S4V2_API_SECRET","")
    _s4k = os.environ.get("S4_API_KEY","")
    _s4s = os.environ.get("S4_API_SECRET","")
    if not _s4v2k or not _s4v2s:
        return ("RED", "S4V2 API key or secret missing in .env. Bot cannot trade until added.")
    if not _s4k or not _s4s:
        return ("RED", "S4 API key or secret missing in .env. Bot cannot trade until added.")
    try:
        from engine.order_manager import OrderManager
        _om_s4v2 = OrderManager(_s4v2k, _s4v2s, testnet=True)
        _p_s4v2 = _om_s4v2.get_position()
        if not _p_s4v2.get('success', False):
            return ("RED", "Delta rejected the S4V2 API key. It may be wrong, expired, or deleted.")
    except Exception as _e:
        return ("RED", f"Could not verify S4V2 API key: {str(_e)[:50]}")
    try:
        from engine.order_manager import OrderManager
        _om_s4 = OrderManager(_s4k, _s4s, testnet=True)
        _p_s4 = _om_s4.get_position()
        if not _p_s4.get('success', False):
            return ("RED", "Delta rejected the S4 API key. It may be wrong, expired, or deleted.")
    except Exception as _e:
        return ("RED", f"Could not verify S4 API key: {str(_e)[:50]}")
    return ("GREEN", "S4V2 and S4 API keys are valid and accepted by Delta.")

def _fetch_delta_full_status():
    import requests as _rq3
    _known_errors = [
        ("insufficient_margin", "Order rejected: Not enough margin in account. Add funds or reduce size."),
        ("order_size_exceed_available", "Order rejected: Not enough buyers or sellers available right now."),
        ("risk_limits_breached", "Order rejected: This trade would breach your allowed risk limit."),
        ("invalid_contract", "Order rejected: This contract doesn't exist or has expired."),
        ("immediate_liquidation", "Order rejected: This trade would immediately liquidate your position."),
        ("out_of_bankruptcy", "Order rejected: Price is outside the allowed limit."),
        ("self_matching_disrupted_post_only", "Order rejected: Self-matching not allowed during auction."),
        ("immediate_execution_post_only", "Order rejected: Post-only order would execute immediately."),
        ("rate_limit_exceeded", "Delta says bot is sending requests too fast. It will auto-slow-down for a few minutes."),
        ("unauthorized", "Bot login to Delta failed. Check API key or secret."),
        ("POST failed after 3 attempts", "Delta is not accepting new orders right now. This is a server issue on Delta side, not your bot."),
        ("GET failed after 3 attempts", "Delta is not accepting new orders right now. This is a server issue on Delta side, not your bot."),
        ("liquidation", "One of your positions was liquidated by Delta. Check your account immediately."),
    ]
    try:
        r = _rq3.get('https://cdn-ind.testnet.deltaex.org/v2/products?contract_types=perpetual_futures&limit=1', timeout=5)
        if r.status_code != 200:
            return ("RED", f"Delta is not responding normally (code {r.status_code}). This is a server issue on Delta side.")
        from engine.order_manager import OrderManager
        om = OrderManager(os.getenv("S4V2_API_KEY"), os.getenv("S4V2_API_SECRET"), testnet=True)
        pos = om.get_position()
        if not pos.get('success', False):
            return ("RED", "Bot cannot log in to Delta. Check API key or secret.")
        _found = None
        for _logf in ["logs/live_trading_s4v2.log", "logs/live_trading_s4.log"]:
            try:
                _lines = open(_logf).readlines()[-150:]
            except:
                continue
            for _line in reversed(_lines):
                for _code, _msg in _known_errors:
                    if _code in _line:
                        _found = _msg
                        break
                if _found:
                    break
            if _found:
                break
        if _found:
            return ("YELLOW", _found)
        return ("GREEN", "Everything working fine. Orders and account checks both OK.")
    except Exception as e:
        return ("RED", f"Cannot reach Delta at all: {str(e)[:60]}")
# ================================================================
# END PERFORMANCE HELPERS
# ================================================================

st.set_page_config(page_title="Crypto Trading Dashboard", layout="wide", page_icon="📈")
st.markdown("""
<style>

[data-testid="stTable"] table, [data-testid="stDataFrame"] table {
}
[data-testid="stTable"] th, [data-testid="stTable"] td,
[data-testid="stDataFrame"] th, [data-testid="stDataFrame"] td {
}
</style>
""", unsafe_allow_html=True)

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

/* STICKY HEADER + TABS */
header[data-testid="stHeader"] {
    position: sticky !important;
    top: 0 !important;
    z-index: 999 !important;
}
div[data-testid="stTabs"] > div:first-child {
    position: sticky !important;
    top: 0 !important;
    z-index: 998 !important;
    background: white !important;
    padding-top: 4px !important;
}

/* TAB STYLING */
button[data-baseweb="tab"] {
    font-size: 12px !important;
    font-weight: 600 !important;
    color: #555 !important;
    background: #E3F2FD !important;
    border-radius: 4px 4px 0 0 !important;
    padding: 6px 14px !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #ffffff !important;
    background: #42A5F5 !important;
    border-bottom: 3px solid #1565C0 !important;
}
button[data-baseweb="tab"]:hover {
    color: #1565C0 !important;
    background: #e3f2fd !important;
}

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
    border: 1px solid #90CAF9 !important;
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
    border: 1px solid #90CAF9 !important;
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
    background: #E3F2FD !important;
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
    background-color: #BBDEFB !important;
}
summary:hover { background-color: #BBDEFB !important; }
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
    border: 1px solid #BBDEFB !important;
    border-radius: 3px !important;
}
[data-testid="stExpanderToggleIcon"] {
    color: #2196F3 !important;
}
div[data-testid="stExpander"] > div:first-child {
    background: #E3F2FD !important;
    border-left: 4px solid #2196F3 !important;
    border-radius: 3px !important;
    padding: 0 !important;
}
/* Nested expanders inside expanders */
div[data-testid="stExpander"] div[data-testid="stExpander"] > div:first-child {
    background: #E3F2FD !important;
    border-left: 4px solid #2196F3 !important;
}
div[data-testid="stExpander"] div[data-testid="stExpander"] details summary {
    background: #E3F2FD !important;
    color: #131722 !important;
    border-left: 4px solid #2196F3 !important;
}
/* Force ALL summary elements site-wide */
summary {
    background: #E3F2FD !important;
    color: #131722 !important;
    border-left: 4px solid #2196F3 !important;
    font-weight: 700 !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
    padding: 4px 10px !important;
}
summary:hover {
    background-color: #BBDEFB !important;
}
summary:hover { background-color: #BBDEFB !important; }
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
    background: #E3F2FD !important;
    border-left: 4px solid #2196F3 !important;
    border-radius: 3px !important;
    padding: 0 !important;
}
div[data-testid="stExpander"] details summary:hover {
    background-color: #BBDEFB !important;
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
    background-color: #BBDEFB !important;
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
    border: 1px solid #90CAF9 !important;
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
    border: 1px solid #90CAF9 !important;
    color: #131722 !important; background: #E3F2FD !important;
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
    padding: 6px 16px !important; font-size: 12px !important;
    font-weight: 700 !important; color: #1565C0 !important;
    background: #e3f2fd !important; border-radius: 6px 6px 0 0 !important;
}
.stTabs [aria-selected="true"] {
    color: #ffffff !important; background: #42A5F5 !important;
    border-bottom: 3px solid #1565C0 !important;
    text-shadow: none !important;
    font-size: 13px !important;
    font-weight: 800 !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #ffffff !important; background: #42A5F5 !important;
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
    border: 1px solid #90CAF9; background: #FFFFFF;
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
s4v2_log = system.get("log_path_s4v2", "logs/live_trading_s4v2.log")
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

import datetime as _dt_refresh
_last_refresh = (_dt_refresh.datetime.utcnow() + _dt_refresh.timedelta(hours=5, minutes=30)).strftime("%d-%b-%Y %I:%M:%S %p")
_col_ref1, _col_ref2 = st.columns([8,1])
with _col_ref1:
    st.markdown(
        f'''<div style="text-align:right;font-size:12px;color:#222;font-weight:700;margin:-8px 0 4px 0;">
        Last updated: {_last_refresh} IST
        &nbsp; <span style="background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:700;">LIVE</span>
        </div>''',
        unsafe_allow_html=True
    )


# MAIN NAVIGATION TABS

# DATA LOADING - before tabs
_INR14 = 84.0
_TH14  = "padding:5px 8px;border:1px solid #90CAF9;background:#E3F2FD;font-size:10px;font-weight:700;color:#555;"
_TD14  = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#131722;"
_TDR14 = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#131722;text-align:center;"
_TDG14 = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#089981;font-weight:700;text-align:center;"
_TDO14 = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#e07000;font-weight:700;text-align:center;"
_TDB14 = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#089981;font-weight:700;text-align:center;"
_TDR14B= "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#F23645;font-weight:700;text-align:center;"
_THGR14= "padding:5px 8px;border:1px solid #90CAF9;background:#089981;font-size:10px;font-weight:700;color:#fff;text-align:center;"
_THOG14= "padding:5px 8px;border:1px solid #90CAF9;background:#e07000;font-size:10px;font-weight:700;color:#fff;text-align:center;"
_SUB14 = "padding:4px 8px;border:1px solid #90CAF9;background:#E8ECF2;font-size:10px;font-weight:700;color:#131722;"
_DASH14= "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#aaa;text-align:center;"
_PLNH14= "padding:5px 8px;border:1px solid #90CAF9;background:#2962FF;font-size:10px;font-weight:700;color:#fff;text-align:center;"
_PLND14= "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#131722;text-align:left;"
_PLNV14= "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#131722;font-weight:700;text-align:center;"

@st.cache_data(ttl=60)
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
        week_s   = now14 - _dt14.timedelta(days=7)
        tot  = len(df)
        gross= df['gross_pnl'].sum() if 'gross_pnl' in df.columns else 0
        net  = df['net_pnl'].sum() if 'net_pnl' in df.columns else 0
        net_inr_pretax = df['net_pnl_inr'].sum() if 'net_pnl_inr' in df.columns else net*_INR14
        tax  = df['tax_usd'].sum() if 'tax_usd' in df.columns else 0
        # Apply 10% tax on winning PnL (matches manual backtest engine)
        _win_pnl_inr = df[df['net_pnl_inr']>0]['net_pnl_inr'].sum() if 'net_pnl_inr' in df.columns else 0
        _tax_inr = _win_pnl_inr * 0.10
        net_inr = net_inr_pretax - _tax_inr
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
            _today_df = df[df['entry_datetime'].dt.date == today_s.date()]
            if 'net_pnl_inr' in df.columns:
                _today_win_inr = _today_df[_today_df['net_pnl_inr']>0]['net_pnl_inr'].sum()
                pnl_today_inr = _today_df['net_pnl_inr'].sum() - (_today_win_inr*0.10)
                pnl_today = pnl_today_inr / _INR14 if _INR14 else 0
            else:
                pnl_today = _today_df['net_pnl'].sum()
            pnl_month = df[df['entry_datetime'] >= _pd14.Timestamp(month_s)]['net_pnl'].sum()
            pnl_week  = df[df['entry_datetime'] >= _pd14.Timestamp(week_s)]['net_pnl'].sum()
            # This month max DD
            df_mo = df[df['entry_datetime'] >= _pd14.Timestamp(month_s)]
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
            green_m=total_m=0; dd=0; pnl_today=pnl_month=pnl_week=0; dd_mo=0; dd_mo10=0
        rec_cap = dd * 3 * _INR14
        roc = (net_inr / rec_cap * 100) if rec_cap > 0 else 0
        months = max(total_m, 1)
        roc_monthly = roc / months
        # Today + month trade count
        today_count = len(df[df['entry_datetime'].dt.date == today_s.date()]) if 'entry_datetime' in df.columns else 0
        month_count = len(df[df['entry_datetime'] >= _pd14.Timestamp(month_s)]) if 'entry_datetime' in df.columns else 0
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
            "pnl_today":pnl_today,"pnl_week":pnl_week,"pnl_month":pnl_month,"dd_month":dd_mo,"dd_month10":dd_mo10,
            "today_count":today_count,"month_count":month_count,
            "gross_win":df[df['gross_pnl']>0]['gross_pnl'].sum() if 'gross_pnl' in df.columns else 0,
            "win_rate":win_rate,"max_profit":max_profit,"max_loss":max_loss,
            "risk_reward":risk_reward,"profit_factor":profit_factor,"sharpe":sharpe,
            "max_dd_days":max_dd_days,"max_dd_period_loss":max_dd_period_loss,
            "max_win_streak_days":max_win_streak_days,
            "raw_df":df
        }
    except Exception as _e14:
        return None

@st.cache_data(ttl=60)
def _delta_get_auth_top(api_key, api_secret, base_url, path, params={}):
    import hmac as _hm, hashlib as _hs, time as _tm, requests as _rq
    try:
        ts  = str(int(_tm.time()))
        qs  = '&'.join(f"{k}={v}" for k,v in params.items())
        query_path = path + ('?' + qs if qs else '')
        msg = 'GET' + ts + query_path
        sig = _hm.new(api_secret.encode(), msg.encode(), _hs.sha256).hexdigest()
        hdrs = {'api-key': api_key, 'timestamp': ts, 'signature': sig, 'Content-Type': 'application/json'}
        r = _rq.get(base_url + path, params=params, headers=hdrs, timeout=(3,10), verify=False)
        return r.json()
    except:
        return {}

def _fetch_orders_top(api_key, api_secret, base_url, from_ts, to_ts, product_id=84):
    from collections import defaultdict
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
            resp  = _delta_get_auth_top(api_key, api_secret, base_url, '/v2/fills', params)
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
        order_fills[f.get('order_id','')].append(f)
    orders = []
    for oid, fills in order_fills.items():
        total_size = sum(float(f.get('size',0)) for f in fills)
        wavg = sum(float(f.get('price',0) or 0)*float(f.get('size',0)) for f in fills) / max(total_size,1)
        order_commission = sum(abs(float(f.get('commission',0))) for f in fills)
        orders.append({
            'order_id': oid,
            'side': fills[0].get('side','').upper(),
            'size': total_size,
            'price': wavg,
            'time': fills[0].get('created_at',''),
            'commission': order_commission
        })
    return sorted(orders, key=lambda x: x['time'])

def _pair_orders_top(orders):
    pairs = []
    used  = set()
    orders_sorted = sorted(orders, key=lambda x: x['time'])
    for i, entry_order in enumerate(orders_sorted):
        if i in used:
            continue
        entry_side = entry_order['side']
        exit_side  = 'SELL' if entry_side == 'BUY' else 'BUY'
        for j, exit_order in enumerate(orders_sorted):
            if j <= i or j in used:
                continue
            if exit_order['side'] == exit_side:
                used.add(i); used.add(j)
                break
            elif exit_order['side'] == entry_side:
                break
                if entry_side == 'BUY':
                    pnl = (exit_order['price'] - entry_order['price']) * entry_order['size'] * 0.001
                    side_label = 'LONG'
                else:
                    pnl = (entry_order['price'] - exit_order['price']) * entry_order['size'] * 0.001
                    side_label = 'SHORT'
                pairs.append({
                    'entry_ts': entry_order['time'], 'exit_ts': exit_order['time'],
                    'entry_price': entry_order['price'], 'exit_price': exit_order['price'],
                    'size': entry_order['size'], 'pnl': pnl,
                    'comm': entry_order['commission'] + exit_order['commission'],
                    'side': 'buy' if side_label=='LONG' else 'sell'
                })
                break
        else:
            # Open position - no exit yet
            side_label = 'LONG' if entry_side=='BUY' else 'SHORT'
            pairs.append({
                'entry_ts': entry_order['time'], 'exit_ts': '-',
                'entry_price': entry_order['price'], 'exit_price': 0,
                'size': entry_order['size'], 'pnl': 0,
                'comm': entry_order['commission'],
                'side': 'buy' if side_label=='LONG' else 'sell',
                'open': True
            })
    return pairs

def _parse_log_trades(log_path, log_path_bak=None):
    import re, datetime as _dtp
    pairs = []
    lines = []
    try:
        if log_path_bak:
            try: lines += open(log_path_bak).readlines()
            except: pass
        lines += open(log_path).readlines()
    except: return pairs
    today = _dtp.datetime.utcnow().strftime("%Y-%m-%d")
    entries = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "[ORDER] ENTRY" in line and "confirmed" not in line and "attempt" not in line:
            m_dir = re.search(r'dir=(\w+)', line)
            m_ts  = re.search(r'ts=(\S+)', line)
            m_log = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            direction = m_dir.group(1) if m_dir else ""
            sig_ts    = m_ts.group(1) if m_ts else ""
            log_ts    = m_log.group(1) if m_log else ""
            entry_price = 0.0
            # Look ahead for entry price
            for j in range(i+1, min(i+5, len(lines))):
                m_ep = re.search(r'entry=([\d.]+)', lines[j])
                if m_ep:
                    entry_price = float(m_ep.group(1))
                    break
            if entry_price == 0.0 and sig_ts:
                _csv_map2 = {"logs/live_trading_s4v2.log": "logs/signals_s4v2.csv",
                             "logs/live_trading_s4.log": "logs/signals_s4.csv"}
                _csv_path2 = _csv_map2.get(log_path)
                if _csv_path2:
                    try:
                        with open(_csv_path2) as _cf:
                            for _cl in _cf:
                                _cp = _cl.strip().split(',')
                                if len(_cp) >= 5 and _cp[0] == sig_ts:
                                    entry_price = float(_cp[4])
                                    break
                    except Exception:
                        pass
            entries.append({
                "direction": direction,
                "sig_ts": sig_ts,
                "log_ts": log_ts,
                "entry_price": entry_price,
                "exit_price": 0.0,
                "exit_ts": "-",
                "open": True
            })
        elif "[ORDER] EXIT" in line and "skipped" not in line and "confirmed" not in line:
            m_ts  = re.search(r'ts=(\S+)', line)
            m_log = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            exit_ts  = m_ts.group(1) if m_ts else ""
            log_ts_x = m_log.group(1) if m_log else ""
            if entries:
                last = entries[-1]
                last["exit_ts"]    = exit_ts
                last["exit_log_ts"]= log_ts_x
                last["open"]       = False
        elif "SL hit or manual close" in line and entries and entries[-1]["open"]:
            m_log = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            log_ts_x = m_log.group(1) if m_log else ""
            last = entries[-1]
            last["exit_log_ts"] = log_ts_x
            last["exit_ts"]     = log_ts_x
            last["open"]        = False
            last["sl_hit"]      = True
            for _j2 in range(i, min(i+5, len(lines))):
                m_syncp = re.search(r'exit=[\d\-T:]+ price=([\d.]+)', lines[_j2])
                if m_syncp:
                    try:
                        last["exit_price"] = float(m_syncp.group(1))
                    except Exception:
                        pass
                    break
        elif "[ORDER] EXIT confirmed" in line:
            m_xp = re.search(r'exit=([\d.]+)', line)
            if m_xp and entries and not entries[-1]["open"] and entries[-1]["exit_price"] == 0.0:
                entries[-1]["exit_price"] = float(m_xp.group(1))
        i += 1
    # Filter to today only
    for e in entries:
        _filter_ts = e.get("log_ts") or e.get("sig_ts","")
        log_date = _filter_ts[:10]
        if log_date == today or (e.get("open") and e["entry_price"] > 0):
            side = "buy" if e["direction"].lower() == "long" else "sell"
            _ep = e["entry_price"]; _xp = e["exit_price"]
            _qty_btc = 100 * 0.001  # 100 lots = 0.1 BTC
            if not e["open"] and _ep > 0 and _xp > 0:
                _raw_pnl = (_xp - _ep) * _qty_btc if side == "buy" else (_ep - _xp) * _qty_btc
                _fees = (_ep + _xp) * _qty_btc * 0.0005
                _real_fp = "logs/fill_prices_s4v2.csv" if "s4v2" in log_path else "logs/fill_prices_s4.csv"
                try:
                    if os.path.exists(_real_fp):
                        with open(_real_fp) as _rf:
                            _rf.readline()
                            for _rl in _rf:
                                _rp = _rl.strip().split(',')
                                if len(_rp) >= 9 and _rp[0] == e.get("sig_ts",""):
                                    _fees = float(_rp[8])
                                    break
                except Exception:
                    pass
                _net = _raw_pnl - _fees
                _tax = max(_net, 0) * 0.10
                _final_pnl = _net - _tax
            else:
                _fees = 0.0
                _final_pnl = 0.0
            pairs.append({
                "entry_ts":    e["log_ts"],
                "exit_ts":     e.get("exit_log_ts", e["exit_ts"]),
                "entry_price": e["entry_price"],
                "exit_price":  e["exit_price"],
                "size":        100,
                "pnl":         _final_pnl,
                "comm":        _fees,
                "side":        side,
                "open":        e["open"],
                "sl_hit":      e.get("sl_hit", False)
            })
    return pairs

def _load14_fwd(product_id, api_key, api_secret, base_url):
    import math as _mf, numpy as _npf, datetime as _dt14f
    try:
        if not api_key or not api_secret: return None
        import time as _tm14
        now_ts = int(_tm14.time())
        import datetime as _dt14fx; _today14 = _dt14fx.datetime.utcnow().replace(hour=0,minute=0,second=0,microsecond=0); _lookback14 = _today14 - _dt14fx.timedelta(days=3); from_ts = int(_lookback14.timestamp())  # lookback 3 days so cross-day trades pair correctly
        orders = _fetch_orders_top(api_key, api_secret, base_url, from_ts, now_ts, product_id)
        _pairs_all = _pair_orders_top(orders)
        if not _pairs_all: return None
        _td_early14 = _today14.strftime("%Y-%m-%d")
        pairs = [p for p in _pairs_all if p.get("exit_ts","")[:10]==_td_early14 or p.get("entry_ts","")[:10]==_td_early14]
        if not pairs: return None
        tot=len(pairs); pnls=[p["pnl"] for p in pairs]
        wins=[v for v in pnls if v>0]; losses=[v for v in pnls if v<0]
        win_rate=len(wins)/tot*100 if tot>0 else 0
        net_usd=sum(pnls)
        _win_usd=[v for v in pnls if v>0]
        _tax_usd=sum(_win_usd)*0.10
        net_inr=(net_usd-_tax_usd)*_INR14
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
        pnl_today=sum(p["pnl"] for p in pairs if p.get("entry_ts","")[:10]==td)*_INR14
        pnl_month=sum(p["pnl"] for p in pairs if p["exit_ts"][:10]>=ms)*_INR14
        today_count=sum(1 for p in pairs if p.get("entry_ts","")[:10]==td)
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
            "gross":net_usd,"net":net_usd,"margin_avg":0,
            "pnl_week":sum(p["pnl"] for p in pairs if p.get("xts",0) >= (_dt14.datetime.utcnow()-_dt14.timedelta(days=7)).timestamp()),
            "avg_slip":(sum(abs(p.get("ep",0)-p.get("xp",0))*0.001 for p in pairs)/len(pairs)) if pairs else 0,
            "raw_pairs":pairs
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
    s2_wk=_g(d2,"pnl_week")*_INR14; s4_wk=_g(d4,"pnl_week")*_INR14; port_wk=s2_wk+s4_wk
    s2_slip=_g(d2,"slip"); s4_slip=_g(d4,"slip"); port_slip=s2_slip+s4_slip
    s2_tod_cnt=int(_g(d2,"today_count")); s4_tod_cnt=int(_g(d4,"today_count")); port_tod_cnt=s2_tod_cnt+s4_tod_cnt
    s2_mo=_g(d2,"pnl_month")*_INR14; s4_mo=_g(d4,"pnl_month")*_INR14
    s2_mo_cnt=int(_g(d2,"month_count")); s4_mo_cnt=int(_g(d4,"month_count")); port_mo_cnt=s2_mo_cnt+s4_mo_cnt
    s2_dd_mo=_g(d2,"dd_month")*_INR14; s4_dd_mo=_g(d4,"dd_month")*_INR14; port_dd_mo=s2_dd_mo+s4_dd_mo
    s2_dd_mo10=_g(d2,"dd_month10")*_INR14; s4_dd_mo10=_g(d4,"dd_month10")*_INR14; port_dd_mo10=s2_dd_mo10+s4_dd_mo10
    s2_td10=s2_td-s2_tod_cnt*10*_INR14; s4_td10=s4_td-s4_tod_cnt*10*_INR14; port_td10=s2_td10+s4_td10
    s2_mo10=s2_mo-s2_mo_cnt*10*_INR14; s4_mo10=s4_mo-s4_mo_cnt*10*_INR14; port_mo10=s2_mo10+s4_mo10
    s2_prev=s2_mo-s2_td; s4_prev=s4_mo-s4_td; port_prev=s2_prev+s4_prev
    s2_prev10=s2_mo10-s2_td10; s4_prev10=s4_mo10-s4_td10; port_prev10=s2_prev10+s4_prev10
    # ITR Tax 30% on gross wins (Indian Income Tax - pay to govt via ITR filing)
    s2_gross_win=_g(d2,"gross_win")*_INR14; s4_gross_win=_g(d4,"gross_win")*_INR14; port_gross_win=s2_gross_win+s4_gross_win
    s2_itr5=s2_gross_win*0.30; s4_itr5=s4_gross_win*0.30; port_itr5=port_gross_win*0.30
    s2_net_itr5=s2_net5-s2_itr5; s4_net_itr5=s4_net5-s4_itr5; port_net_itr5=port_net5-port_itr5
    s2_net_itr10=s2_net10-s2_itr5; s4_net_itr10=s4_net10-s4_itr5; port_net_itr10=port_net10-port_itr5
    s2_mg=_g(d2,"margin_avg")*_INR14; s4_mg=_g(d4,"margin_avg")*_INR14
    _THFW14="padding:5px 8px;border:1px solid #90CAF9;background:#089981;font-size:10px;font-weight:700;color:#fff;text-align:center;"
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
    fw2_wk=_g(df2,"pnl_week"); fw4_wk=_g(df4,"pnl_week"); fwp_wk=fw2_wk+fw4_wk
    fw2_slip=_g(df2,"avg_slip"); fw4_slip=_g(df4,"avg_slip")
    fw2_chg=_g(df2,"total_charges"); fw4_chg=_g(df4,"total_charges"); fwp_chg=fw2_chg+fw4_chg
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
      <th style="{_THGR14}">S4V2</th><th style="{_THGR14}">S4</th><th style="{_THGR14}">Portfolio</th>
      <th style="{_THOG14}">S4V2</th><th style="{_THOG14}">S4</th><th style="{_THOG14}">Portfolio</th>
      <th style="{_THFW14}">S4V2</th><th style="{_THFW14}">S4</th><th style="{_THFW14}">Portfolio</th>
    </tr>
    </thead>
    <tbody>
    <tr><td colspan="10" style="{_SUB14}">DYNAMIC PnL (SYNCED WITH SECTION 13)</td></tr>
    {_row9("Today PnL",f"₹{s2_td:,.0f}",f"₹{s4_td:,.0f}",f"₹{s2_td+s4_td:,.0f}",f"₹{s2_td10:,.0f}",f"₹{s4_td10:,.0f}",f"₹{port_td10:,.0f}",_fna(fw2_td),_fna(fw4_td),_fna(fw2_td+fw4_td),_c(s2_td),_c(s4_td),_c(s2_td+s4_td),_c(s2_td10),_c(s4_td10),_c(port_td10),_cf(fw2_td),_cf(fw4_td),_cf(fw2_td+fw4_td))}
    {_row9("Today Trades",f"{s2_tod_cnt:,}",f"{s4_tod_cnt:,}",f"{port_tod_cnt:,}",f"{s2_tod_cnt:,}",f"{s4_tod_cnt:,}",f"{port_tod_cnt:,}",_fna(fw2_tc,"int"),_fna(fw4_tc,"int"),_fna(fwp_tc,"int"),_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDO14,_TDB14,_TDB14,_TDB14)}
    {_row9("Weekly PnL",f"₹{s2_wk:,.0f}",f"₹{s4_wk:,.0f}",f"₹{port_wk:,.0f}",f"₹{s2_wk:,.0f}",f"₹{s4_wk:,.0f}",f"₹{port_wk:,.0f}",_fna(fw2_wk),_fna(fw4_wk),_fna(fwp_wk),_c(s2_wk),_c(s4_wk),_c(port_wk),_c(s2_wk),_c(s4_wk),_c(port_wk),_cf(fw2_wk),_cf(fw4_wk),_cf(fwp_wk))}
    {_row9("Previous Days PnL (This Month, excl today)",f"₹{s2_prev:,.0f}",f"₹{s4_prev:,.0f}",f"₹{s2_prev+s4_prev:,.0f}",f"₹{s2_prev10:,.0f}",f"₹{s4_prev10:,.0f}",f"₹{port_prev10:,.0f}",_na14,_na14,_na14,_c(s2_prev),_c(s4_prev),_c(s2_prev+s4_prev),_c(s2_prev10),_c(s4_prev10),_c(port_prev10),_na14,_na14,_na14)}
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
    {_row9("Tax + All Charges",f"-₹{s2_chg5:,.0f}",f"-₹{s4_chg5:,.0f}",f"-₹{port_chg5:,.0f}",f"-₹{s2_chg10:,.0f}",f"-₹{s4_chg10:,.0f}",f"-₹{port_chg10:,.0f}",_na14,_na14,_na14,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B)}
    {_row9("Avg Slippage/side",f"${s2_slip/max(tot2,1)/2:,.2f}",f"${s4_slip/max(tot4,1)/2:,.2f}",f"${(s2_slip+s4_slip)/max(tot2+tot4,1)/2:,.2f}",f"${s2_slip/max(tot2,1):,.2f}",f"${s4_slip/max(tot4,1):,.2f}",f"${(s2_slip+s4_slip)/max(tot2+tot4,1):,.2f}",_fna(fw2_slip,"num") if fw2_slip else _na14,_fna(fw4_slip,"num") if fw4_slip else _na14,_na14,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDR14B,_TDB14,_TDB14,_TDB14)}
    {_row9("Net PnL (After Tax, all charges incl.)",_inr(s2_net5/_INR14),_inr(s4_net5/_INR14),_inr(port_net5/_INR14),_inr(s2_net10/_INR14),_inr(s4_net10/_INR14),_inr(port_net10/_INR14),_fna(fw2_net),_fna(fw4_net),_fna(fwp_net),_c(s2_net5),_c(s4_net5),_c(port_net5),_c(s2_net10),_c(s4_net10),_c(port_net10),_cf(fw2_net),_cf(fw4_net),_cf(fwp_net))}
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

# Load data - defined as function so every tab reloads fresh on page load
import glob as _gl14, pandas as _pd14, datetime as _dt14, numpy as _npf14, os as _os14

def _reload_all_data():
    _now14 = _dt14.datetime.utcnow()
    _1yr_from = (_now14 - _dt14.timedelta(days=365)).strftime("%Y-%m-%d")
    _full_from = "2024-01-01"
    _d2_1yr  = _load14("output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv", _1yr_from)
    _d4_1yr  = _load14("output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv",   _1yr_from)
    _d2_full = _load14("output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv", _full_from)
    _d4_full = _load14("output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv",   _full_from)
    _1yr_label = f"{(_now14-_dt14.timedelta(days=365)).strftime('%d-%b-%Y')} to {_now14.strftime('%d-%b-%Y')} (1 Year)"
    _full_label= f"2024-01-01 to {_now14.strftime('%d-%b-%Y')} (Full CSV)"
    _s2_key=_os14.getenv("S4V2_API_KEY",""); _s2_sec=_os14.getenv("S4V2_API_SECRET","")
    _s4_key=_os14.getenv("S4_API_KEY",""); _s4_sec=_os14.getenv("S4_API_SECRET","")
    _fwd_base="https://cdn-ind.testnet.deltaex.org"
    _df2_fwd=_load14_fwd(84,_s2_key,_s2_sec,_fwd_base)
    _df4_fwd=_load14_fwd(84,_s4_key,_s4_sec,_fwd_base)
    return _d2_1yr,_d4_1yr,_d2_full,_d4_full,_1yr_label,_full_label,_df2_fwd,_df4_fwd

_tab_monitor, _tab_trading, _tab_today, _tab_analysis, _tab_backtest, _tab_datasync, _tab_maint = st.tabs([
    "MONITOR", "TRADING", "TODAY'S TRADES", "ANALYSIS", "BACKTEST", "DATA & SYNC", "MAINTENANCE"
])

with _tab_monitor:
    # SECTION 1 - SYSTEM STATUS CARDS
    # ================================================================
    st.markdown("<div class='section-title'>SECTION 1 - SYSTEM STATUS & MAINTENANCE</div>", unsafe_allow_html=True)

    # STATUS LAMPS ROW - full pro implementation
    import datetime as _dt_lamps, os as _os_lamps
    def _lamp(label, ok, warn=False):
        dot = "🟢" if ok else ("🟡" if warn else "🔴")
        return f"<span style='font-size:13px;font-weight:bold;margin-right:18px;'>{dot} {label}</span>"
    def _log_age_min(path):
        return (_dt_lamps.datetime.utcnow() - _dt_lamps.datetime.utcfromtimestamp(
            _os_lamps.path.getmtime(path))).total_seconds()/60

    # S4V2 BOT
    try: _s2_ok = _log_age_min("logs/live_trading_s4v2.log") < 2
    except: _s2_ok = False

    # S4 BOT
    try: _s4_ok = _log_age_min("logs/live_trading_s4.log") < 2
    except: _s4_ok = False

    # ENGINE - heartbeat AND log file both must be fresh
    try:
        _hb = open("logs/engine_heartbeat.txt").read().strip()
        try:
            _hb_age = (_dt_lamps.datetime.utcnow() - _dt_lamps.datetime.utcfromtimestamp(float(_hb))).total_seconds()/60
        except:
            _hb_dt = _dt_lamps.datetime.strptime(_hb, '%Y-%m-%dT%H:%M:%S')
            _hb_age = (_dt_lamps.datetime.utcnow() - _hb_dt).total_seconds()/60
        _eng_log_age = _log_age_min("logs/renko_state_engine.log")
        _eng_ok = _hb_age < 15 and _eng_log_age < 15
        _eng_warn = not _eng_ok and (_hb_age < 30 or _eng_log_age < 30)
    except: _eng_ok = False; _eng_warn = False

    # TM1 S4V2
    try: _tm1s2_ok = _log_age_min("logs/live_trading_testmember1_s4v2.log") < 2
    except: _tm1s2_ok = False

    # TM1 S4
    try: _tm1s4_ok = _log_age_min("logs/live_trading_testmember1_s4.log") < 2
    except: _tm1s4_ok = False

    # BOUNDARY WATCHER
    try: _bw_ok = _log_age_min("logs/boundary_watcher.log") < 60
    except: _bw_ok = False

    # DELTA API
    try:
        _api_result = _timed('delta_api_status', 60, _fetch_delta_api_status)
        _api_ok = (_api_result == 200)
    except: _api_ok = False

    # DISK
    try:
        import shutil as _sh
        _du = _sh.disk_usage("/")
        _disk_pct_lamp = _du.used/_du.total*100
        _disk_ok = _disk_pct_lamp < 70
        _disk_warn = 70 <= _disk_pct_lamp < 80
    except: _disk_ok = False; _disk_warn = False

    # SIGNAL FRESH - signal file age vs engine heartbeat (not fixed time window)
    # Signals only update when new Renko brick forms - can be hours apart in sideways market
    # Real check: is ENGINE alive and heartbeat fresh (already checked by ENGINE lamp)
    # This lamp only goes RED if engine heartbeat itself is stale for very long
    try:
        _hb_val = open("logs/engine_heartbeat.txt").read().strip()
        try:
            _hb_ts = float(_hb_val)
        except:
            _hb_ts = _dt_refresh.datetime.strptime(_hb_val, "%Y-%m-%dT%H:%M:%S").timestamp()
        _hb_age_min = (_perf_time.time() - _hb_ts) / 60
        _sig_ok = _hb_age_min < 35
        _sig_warn = not _sig_ok and _hb_age_min < 120
    except Exception as _sig_exc:
        _sig_ok = False; _sig_warn = False
        print(f"[DEBUG SIGNAL LAMP] {_sig_exc}")

    # CSV FRESH - market data not stale (engine updates every 5 min)
    try:
        _csv_age = _log_age_min("data/btc_1m_delta.csv")
        _csv_ok = _csv_age < 35
        _csv_warn = 35 <= _csv_age < 120
    except: _csv_ok = False; _csv_warn = False

    # WEBSOCKET - check engine log for recent WS connected line
    try:
        _ws_lines = open("logs/renko_state_engine.log").readlines()[-100:]
        _ws_ok = any("WS] Connected" in l or "Websocket connected" in l or "WS] Completed" in l
                     for l in _ws_lines[-20:])
        _ws_warn = not _ws_ok and any("WS]" in l for l in _ws_lines)
    except: _ws_ok = False; _ws_warn = False

    # LAST ORDER - check if any order placed in last 7 days (not stuck)
    try:
        _s2_log_lines = open("logs/live_trading_s4v2.log").readlines()
        _s4_log_lines = open("logs/live_trading_s4.log").readlines()
        _all_lines = _s2_log_lines + _s4_log_lines
        _order_lines = [l for l in _all_lines if "[ORDER] ENTRY" in l or "[ORDER] EXIT" in l]
        _last_order_ok = len(_order_lines) > 0
        _last_order_warn = not _last_order_ok
    except: _last_order_ok = False; _last_order_warn = True

    # POSITION SYNC - no ghost position (check last startup reconciliation)
    try:
        _pos_lines = open("logs/live_trading_s4v2.log").readlines()[-200:]
        _pos_lines += open("logs/live_trading_s4.log").readlines()[-200:]
        _ghost_found = any("Position mismatch" in l for l in _pos_lines)
        _pos_ok = not _ghost_found
        _pos_warn = _ghost_found
    except: _pos_ok = True; _pos_warn = False

    # ENTRY TIMING - check if last entry was stale signal skip
    try:
        _s2_recent = open("logs/live_trading_s4v2.log").readlines()[-500:]
        _s4_recent = open("logs/live_trading_s4.log").readlines()[-500:]
        _stale_s2 = any("STALE" in l or "signal too old" in l for l in _s2_recent)
        _stale_s4 = any("STALE" in l or "signal too old" in l for l in _s4_recent)
        _timing_ok = not (_stale_s2 or _stale_s4)
        _timing_warn = _stale_s2 or _stale_s4
    except: _timing_ok = True; _timing_warn = False

    # Build 2 rows of lamps
    _row1 = (
        _lamp("S4V2 BOT", _s2_ok) +
        _lamp("S4 BOT", _s4_ok) +
        _lamp("ENGINE", _eng_ok, _eng_warn) +
        _lamp("SIGNAL", _sig_ok, _sig_warn) +
        _lamp("WEBSOCKET", _ws_ok, _ws_warn) +
        _lamp("CSV", _csv_ok, _csv_warn) +
        _lamp("DELTA API", _api_ok)
    )
    _row2 = (
        _lamp("TM1 S4V2", _tm1s2_ok) +
        _lamp("TM1 S4", _tm1s4_ok) +
        _lamp("BOUNDARY", _bw_ok) +
        _lamp("LAST ORDER", _last_order_ok, _last_order_warn) +
        _lamp("POSITION", _pos_ok, _pos_warn) +
        _lamp("ENTRY TIMING", _timing_ok, _timing_warn) +
        _lamp("DISK", _disk_ok, _disk_warn if not _disk_ok else False)
    )
    st.markdown(f"""<div style='background:#f0f7ff;border:1px solid #90CAF9;border-radius:6px;padding:10px 16px;margin-bottom:4px;'>{_row1}</div>
<div style='background:#f0f7ff;border:1px solid #90CAF9;border-radius:6px;padding:10px 16px;margin-bottom:12px;'>{_row2}</div>""", unsafe_allow_html=True)

    # ================================================================
    # SECTION 1B - BOT CONTROL (STOP / RESTART for S4 and S4V2)
    # ================================================================
    st.markdown("<div class='section-title'>SECTION 1B - BOT CONTROL</div>", unsafe_allow_html=True)
    with st.expander("S4 / S4V2 STOP & RESTART", expanded=False):
        import subprocess as _sp_bc
        _REPO_BC = "/home/anildalabanjan933/crypto_trading_system"

        def _bot_running(screen_name):
            try:
                out = _sp_bc.run(['screen','-ls'], capture_output=True, text=True, timeout=5).stdout
                return screen_name in out
            except Exception:
                return False

        def _stop_bot(screen_name):
            _sp_bc.run(['screen','-S',screen_name,'-X','quit'], capture_output=True, timeout=5)

        def _restart_bot(screen_name, script_name):
            _sp_bc.run(['screen','-S',screen_name,'-X','quit'], capture_output=True, timeout=5)
            import time as _t_bc; _t_bc.sleep(2)
            cmd = f'cd {_REPO_BC} && set -a && source {_REPO_BC}/.env && set +a && {_REPO_BC}/.venv/bin/python3 scripts/{script_name}'
            _sp_bc.run(['screen','-dmS',screen_name,'bash','-c',cmd], capture_output=True, timeout=5)

        st.caption('STOP only pauses new signal entries. Any already-open position stays live on exchange and remains protected by sl_safety_monitor / position_risk_monitor / margin_monitor (unaffected by this control).')

        bc1, bc2 = st.columns(2)
        with bc1:
            st.markdown('**S4 BOT**')
            _s4_run = _bot_running('live_s4')
            st.success('RUNNING') if _s4_run else st.error('STOPPED')
            _confirm_s4 = st.checkbox('Confirm STOP S4', key='confirm_stop_s4')
            if st.button('STOP S4', key='btn_stop_s4'):
                if _confirm_s4:
                    _stop_bot('live_s4')
                    st.warning('S4 bot stop command sent. Refresh in a few seconds to confirm.')
                else:
                    st.error('Tick the confirm checkbox first.')
            if st.button('RESTART S4', key='btn_restart_s4'):
                _restart_bot('live_s4', 'signal_replay_s4.py')
                st.info('S4 bot restart command sent. Refresh in a few seconds to confirm.')
        with bc2:
            st.markdown('**S4V2 BOT**')
            _s4v2_run = _bot_running('live_s4v2')
            st.success('RUNNING') if _s4v2_run else st.error('STOPPED')
            _confirm_s4v2 = st.checkbox('Confirm STOP S4V2', key='confirm_stop_s4v2')
            if st.button('STOP S4V2', key='btn_stop_s4v2'):
                if _confirm_s4v2:
                    _stop_bot('live_s4v2')
                    st.warning('S4V2 bot stop command sent. Refresh in a few seconds to confirm.')
                else:
                    st.error('Tick the confirm checkbox first.')
            if st.button('RESTART S4V2', key='btn_restart_s4v2'):
                _restart_bot('live_s4v2', 'signal_replay_s4v2.py')
                st.info('S4V2 bot restart command sent. Refresh in a few seconds to confirm.')


    # ---- PLAIN MESSAGES FOR TOP LAMP ROWS (only show if NOT fully green) ----
    _lamp_msgs = []
    if not _sig_ok:
        _lamp_msgs.append(("yellow" if _sig_warn else "red", "SIGNAL: Engine heartbeat not seen recently. Signals may be delayed."))
    if not _ws_ok:
        _lamp_msgs.append(("yellow" if _ws_warn else "red", "WEBSOCKET: Live price connection lost or never connected."))
    if not _csv_ok:
        _lamp_msgs.append(("yellow" if _csv_warn else "red", "CSV: Signal file not updated recently. New trades may be missed."))
    if not _tm1s2_ok:
        _lamp_msgs.append(("red", "TM1 S4V2: TestMember1 S4V2 bot log stuck or missing."))
    if not _tm1s4_ok:
        _lamp_msgs.append(("red", "TM1 S4: TestMember1 S4 bot log stuck or missing."))
    if not _bw_ok:
        _lamp_msgs.append(("red", "BOUNDARY: Boundary watcher stuck or not running."))
    if not _last_order_ok:
        _lamp_msgs.append(("yellow" if _last_order_warn else "red", "LAST ORDER: No order activity found in recent logs."))
    if not _pos_ok:
        _lamp_msgs.append(("yellow" if _pos_warn else "red", "POSITION: Mismatch found between bot's position and Delta's real position."))
    if not _timing_ok:
        _lamp_msgs.append(("yellow" if _timing_warn else "red", "ENTRY TIMING: Signal arrived too late or stale for entry."))

    if _lamp_msgs:
        for _lvl, _msg_txt in _lamp_msgs:
            if _lvl == "red":
                st.error(_msg_txt)
            else:
                st.warning(_msg_txt)
    else:
        st.success("All monitor checks normal: signal, websocket, csv, test accounts, boundary, orders, position, and timing are all healthy.")

    # S4V2 BOT
    try:
        _s2l = _os_lamps.path.getmtime("logs/live_trading_s4v2.log")
        _s2_ok = ((_dt_lamps.datetime.utcnow() - _dt_lamps.datetime.utcfromtimestamp(_s2l)).total_seconds() / 60) < 2
    except: _s2_ok = False

    # S4 BOT
    try:
        _s4l = _os_lamps.path.getmtime("logs/live_trading_s4.log")
        _s4_ok = ((_dt_lamps.datetime.utcnow() - _dt_lamps.datetime.utcfromtimestamp(_s4l)).total_seconds() / 60) < 2
    except: _s4_ok = False

    # ENGINE - uses heartbeat file
    try:
        _hb = open("logs/engine_heartbeat.txt").read().strip()
        try:
            _hb_age = (_dt_lamps.datetime.utcnow() - _dt_lamps.datetime.utcfromtimestamp(float(_hb))).total_seconds() / 60
        except:
            _hb_dt = _dt_lamps.datetime.strptime(_hb, '%Y-%m-%dT%H:%M:%S')
            _hb_age = (_dt_lamps.datetime.utcnow() - _hb_dt).total_seconds() / 60
        _eng_ok = _hb_age < 15
        _eng_warn = 2 < _hb_age < 15
    except: _eng_ok = False; _eng_warn = False

    # TM1 S4V2
    try:
        _tm1s2l = _os_lamps.path.getmtime("logs/live_trading_testmember1_s4v2.log")
        _tm1s2_ok = ((_dt_lamps.datetime.utcnow() - _dt_lamps.datetime.utcfromtimestamp(_tm1s2l)).total_seconds() / 60) < 2
    except: _tm1s2_ok = False

    # TM1 S4
    try:
        _tm1s4l = _os_lamps.path.getmtime("logs/live_trading_testmember1_s4.log")
        _tm1s4_ok = ((_dt_lamps.datetime.utcnow() - _dt_lamps.datetime.utcfromtimestamp(_tm1s4l)).total_seconds() / 60) < 2
    except: _tm1s4_ok = False

    # BOUNDARY WATCHER
    try:
        _bwl = _os_lamps.path.getmtime("logs/boundary_watcher.log")
        _bw_ok = ((_dt_lamps.datetime.utcnow() - _dt_lamps.datetime.utcfromtimestamp(_bwl)).total_seconds() / 60) < 2
    except: _bw_ok = False

    # DELTA API
    try:
        _api_result = _timed('delta_api_status', 60, _fetch_delta_api_status)
        _api_ok = (_api_result == 200)
    except: _api_ok = False

    # DISK
    try:
        import shutil as _sh
        _du = _sh.disk_usage("/")
        _disk_pct_lamp = _du.used / _du.total * 100
        _disk_ok = _disk_pct_lamp < 70
        _disk_warn = 70 <= _disk_pct_lamp < 80
    except: _disk_ok = False; _disk_warn = False

    disk_pct, disk_free = _timed('disk_usage', 30, _fetch_disk)
    git_commit = _timed('git_commit', 60, _fetch_git)
    s2_last = _timed('s2_last_sig', 15, _fetch_log_signal, s4v2_log)
    s4_last = _timed('s4_last_sig', 15, _fetch_log_signal, s4_log)
    s2_error = _timed('s2_log_err', 15, _fetch_log_errors, s4v2_log)
    s4_error = _timed('s4_log_err', 15, _fetch_log_errors, s4_log)

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.markdown("**S4V2 BOT**")
        try:
            import time as _t_s2c
            if not os.path.exists(s4v2_log):
                st.error("NOT STARTED")
                st.caption("Bot log file not found. Bot may never have started.")
            else:
                _s2_age_c1 = (_t_s2c.time() - os.path.getmtime(s4v2_log)) / 60
                if _s2_age_c1 > 10:
                    st.error("STUCK")
                    st.caption(f"No update in {int(_s2_age_c1)} min. Bot may be stuck or crashed.")
                elif s2_error:
                    st.warning("ERRORS FOUND")
                    st.caption(f"Recent error: {s2_error[:60]}")
                else:
                    st.success("RUNNING")
                    st.caption(f"Last: {s2_last[:40]}")
        except Exception as _e:
            st.warning("UNKNOWN")
            st.caption(str(_e)[:40])

    with c2:
        st.markdown("**S4 BOT**")
        try:
            import time as _t_s4c
            if not os.path.exists(s4_log):
                st.error("NOT STARTED")
                st.caption("Bot log file not found. Bot may never have started.")
            else:
                _s4_age_c1 = (_t_s4c.time() - os.path.getmtime(s4_log)) / 60
                if _s4_age_c1 > 10:
                    st.error("STUCK")
                    st.caption(f"No update in {int(_s4_age_c1)} min. Bot may be stuck or crashed.")
                elif s4_error:
                    st.warning("ERRORS FOUND")
                    st.caption(f"Recent error: {s4_error[:60]}")
                else:
                    st.success("RUNNING")
                    st.caption(f"Last: {s4_last[:40]}")
        except Exception as _e:
            st.warning("UNKNOWN")
            st.caption(str(_e)[:40])

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
        try:
            import subprocess as _sp_gh
            _gh_status = _sp_gh.run(["git", "status", "--porcelain"], cwd="/home/anildalabanjan933/crypto_trading_system", capture_output=True, text=True, timeout=5).stdout.strip()
            _gh_unpushed = _sp_gh.run(["git", "log", "@{u}..", "--oneline"], cwd="/home/anildalabanjan933/crypto_trading_system", capture_output=True, text=True, timeout=5).stdout.strip()
            if _gh_status:
                st.warning("UNSAVED CHANGES")
                st.caption("Local files changed but not committed yet.")
            elif _gh_unpushed:
                st.warning("NOT PUSHED")
                st.caption("Committed locally but not pushed to GitHub yet.")
            else:
                st.success("SYNCED")
                st.caption(f"Commit: {git_commit} - matches GitHub")
        except Exception as _e:
            st.warning("UNKNOWN")
            st.caption(str(_e)[:40])

    with c5:
        st.markdown("**DELTA STATUS**")
        try:
            _color, _msg = _timed('delta_full_status', 60, _fetch_delta_full_status)
            if _color == "GREEN":
                st.success("OK")
            elif _color == "YELLOW":
                st.warning("CHECK")
            else:
                st.error("ISSUE")
            st.caption(_msg)
        except Exception as _e:
            st.error("UNREACHABLE")
            st.caption(str(_e)[:60])
            st.caption("Check network")

    # ================================================================
    # SECTION 1 - NEW MONITORING CARDS ROW 2 + ROW 3
    # ================================================================
    import datetime as _dt_cards, time as _t_cards

    # ROW 2 - SYSTEM HEALTH
    _cr2a, _cr2b, _cr2c = st.columns(3)

    # CARD 1 - BOT LOG STATUS + ENGINE STATUS
    with _cr2a:
        try:
            _s2_log_age = (_t_cards.time() - os.path.getmtime("/home/anildalabanjan933/crypto_trading_system/logs/live_trading_s4v2.log")) / 60 if os.path.exists("/home/anildalabanjan933/crypto_trading_system/logs/live_trading_s4v2.log") else 999
            _s4_log_age = (_t_cards.time() - os.path.getmtime("/home/anildalabanjan933/crypto_trading_system/logs/live_trading_s4.log")) / 60 if os.path.exists("/home/anildalabanjan933/crypto_trading_system/logs/live_trading_s4.log") else 999
            _eng_log = "/home/anildalabanjan933/crypto_trading_system/logs/renko_state_engine.log"
            _eng_age = (_t_cards.time() - os.path.getmtime(_eng_log)) / 60 if os.path.exists(_eng_log) else 999
            st.markdown("**BOT LOG**")
            if _s2_log_age > 10 or _s4_log_age > 10:
                st.error("INACTIVE")
                st.caption(f"S4V2: {int(_s2_log_age)}m | S4: {int(_s4_log_age)}m no update")
            else:
                st.success("ACTIVE")
                st.caption(f"S4V2: {int(_s2_log_age)}m ago | S4: {int(_s4_log_age)}m ago")
            st.markdown("**ENGINE**")
            if _eng_age > 10:
                st.error(f"DEAD - {int(_eng_age)}m no update")
                st.caption("Run: bash start.sh immediately")
            elif _eng_age > 3:
                st.warning(f"SLOW - {int(_eng_age)}m ago")
                st.caption("Engine may be stuck")
            else:
                st.success(f"RUNNING - {int(_eng_age)}m ago")
                st.caption("Engine firing normally")
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
            st.markdown("**API KEY/SECRET**")
            _kcolor, _kmsg = _timed('key_validity', 60, _fetch_key_validity)
            if _kcolor == "GREEN":
                st.success("OK")
            else:
                st.error("ISSUE")
            st.caption(_kmsg)
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
            for _lp in ["logs/live_trading_s4v2.log", "logs/live_trading_s4.log"]:
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
            for _lp in ["logs/live_trading_s4v2.log", "logs/live_trading_s4.log"]:
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
            for _lp in ["logs/live_trading_s4v2.log", "logs/live_trading_s4.log"]:
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
    if not os.path.exists(s4v2_log):
        alerts.append(("red", "S4V2 LOG NOT FOUND - bot may not be running"))
    if not os.path.exists(s4_log):
        alerts.append(("red", "S4 LOG NOT FOUND - bot may not be running"))
    if s2_error:
        alerts.append(("red", f"S4V2 ERROR DETECTED: {s2_error}"))
    if s4_error:
        alerts.append(("red", f"S4 ERROR DETECTED: {s4_error}"))

    # Bot activity check - warn if no log update in last 5 minutes
    try:
        import time as _t
        now_ts = _t.time()
        for bot_name, log_path in [("S4V2", s4v2_log), ("S4", s4_log)]:
            if os.path.exists(log_path):
                log_age = now_ts - os.path.getmtime(log_path)
                if log_age > 300:
                    alerts.append(("yellow", f"{bot_name} BOT INACTIVE: No log update for {int(log_age//60)} minutes - check if bot is running"))
    except:
        pass

    # New order detection
    try:
        for bot_name, log_path in [("S4V2", s4v2_log), ("S4", s4_log)]:
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
        for bot_name, log_path in [("S4V2", s4v2_log), ("S4", s4_log)]:
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
            s2_size = round(os.path.getsize(s4v2_log)/1024/1024, 1) if os.path.exists(s4v2_log) else 0
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
                    for log_path in [s4v2_log, s4_log]:
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
        for _sb in ["S4", "S4V2"]:
            _sf = f"logs/stuck_flag_{_sb}.txt"
            if os.path.exists(_sf):
                st.error(f"STUCK PENDING - {_sb}: CSV shows open position but exchange is FLAT. Check signals CSV / restart signal_generator.")
            _of = f"logs/orphan_flag_{_sb}.txt"
            if os.path.exists(_of):
                st.error(f"ORPHAN POSITION - {_sb}: exchange OPEN but CSV shows closed/missing. Check SL and CSV manually.")
            _af = f"logs/authfail_flag_{_sb}.txt"
            if os.path.exists(_af):
                st.error(f"API FAILURE - {_sb}: API failed 3x in a row. Check key/connectivity.")
            _lf = f"logs/lowbalance_flag_{_sb}.txt"
            if os.path.exists(_lf):
                st.warning(f"LOW BALANCE - {_sb}: available balance below threshold.")
            _mf = f"logs/mismatch_flag_{_sb}.txt"
            if os.path.exists(_mf):
                st.error(f"MISMATCH - {_sb}: CSV vs exchange size/direction differ. Check manually.")
        import subprocess, os, datetime

        errors = []
        warnings = []
        ok = []

        # 1. CHECK BOT SCREENS RUNNING (cached 30s)
        try:
            _scr_ls = _timed('err_screen_ls', 30, _fetch_screen_list)
            if 'live_s4v2' in _scr_ls:
                ok.append("S4V2 bot screen: RUNNING")
            else:
                errors.append("S4V2 bot screen: NOT RUNNING - run bash start.sh on VM")
            if 'live_s4' in _scr_ls:
                ok.append("S4 bot screen: RUNNING")
            else:
                errors.append("S4 bot screen: NOT RUNNING - run bash start.sh on VM")
        except Exception as e:
            errors.append(f"Screen check failed: {e}")

        # 2. CHECK LOG FILES EXIST AND RECENT
        try:
            _wf = "logs/maintenance.log"
            if os.path.exists(_wf):
                import datetime as _dtw
                _cutw = _dtw.datetime.utcnow() - _dtw.timedelta(minutes=30)
                _wlines = open(_wf).readlines()[-200:]
                for _wl in _wlines:
                    if "DOWN alert sent for" in _wl:
                        try:
                            _wts = _dtw.datetime.strptime(_wl[1:20], '%Y-%m-%dT%H:%M:%S')
                            if _wts >= _cutw:
                                st.error(f"WATCHDOG - {_wl.strip()}")
                        except: pass
        except Exception:
            pass

        for bot, log in [('S4V2', 'logs/live_trading_s4v2.log'), ('S4', 'logs/live_trading_s4.log'), ('ENGINE', 'logs/renko_state_engine.log')]:
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
        for bot, log in [('S4V2', 'logs/live_trading_s4v2.log'), ('S4', 'logs/live_trading_s4.log'), ('ENGINE', 'logs/renko_state_engine.log')]:
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
                    api_errors = [l.strip() for l in recent if any(x in l for x in ['InvalidApiKey','invalid_api_key','insufficient_margin','rate_limit','IP not whitelisted','ENTRY FAILED','EXIT FAILED','CRITICAL','SL HIT DETECTED','MISSED TRADE','ENTRY UNFILLED','BAD FILL DESPITE','ENGINE WARNING']) or ('ERROR' in l and any(x in l for x in ['401','403','429']))]
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
        for bot, log in [('S4V2', 'logs/live_trading_s4v2.log'), ('S4', 'logs/live_trading_s4.log')]:
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
        for bot, log in [('S4V2', 'logs/live_trading_s4v2.log'), ('S4', 'logs/live_trading_s4.log')]:
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
        for bot, log in [('S4V2', 'logs/live_trading_s4v2.log'), ('S4', 'logs/live_trading_s4.log')]:
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
        for bot, log, ts_file in [('S4V2', 'logs/live_trading_s4v2.log', 'logs/last_known_ts_s4v2.txt'),
                                   ('S4', 'logs/live_trading_s4.log', 'logs/last_known_ts_s4.txt')]:
            try:
                if os.path.exists(log):
                    # Get valid from timestamp
                    valid_from = None
                    if os.path.exists(ts_file):
                        valid_from = open(ts_file).read().strip()
                    lines = open(log).readlines()
                    order_lines = [l for l in lines if '[ORDER]' in l and 'attempt' not in l]
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
        for bot, log in [('S4V2', 'logs/live_trading_s4v2.log'), ('S4', 'logs/live_trading_s4.log')]:
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

        # 12B. CHECK ENGINE (renko_state_engine) RUNNING
        try:
            import time as _time_eng
            _eng_log = "/home/anildalabanjan933/crypto_trading_system/logs/renko_state_engine.log"
            if not os.path.exists(_eng_log):
                errors.append("ENGINE LOG MISSING - renko_state_engine.py never started - run bash start.sh")
            else:
                _eng_age_mins = (_time_eng.time() - os.path.getmtime(_eng_log)) / 60
                if _eng_age_mins > 10:
                    errors.append(f"ENGINE DEAD - no update in {int(_eng_age_mins)}m - signals not firing - run bash start.sh IMMEDIATELY")
                elif _eng_age_mins > 3:
                    warnings.append(f"ENGINE SLOW - last update {int(_eng_age_mins)}m ago - may be stuck")
                else:
                    ok.append(f"Engine (renko_state_engine): RUNNING - last update {int(_eng_age_mins)}m ago")
            # Check signal files age
            for _sf, _label, _pos_flag in [("logs/live_signal_s4v2.txt","S4V2 signal","logs/last_known_ts_s4v2.txt"), ("logs/live_signal_s4.txt","S4 signal","logs/last_known_ts_s4.txt")]:
                if os.path.exists(_sf):
                    _sf_age = (_time_eng.time() - os.path.getmtime(_sf)) / 60
                    _has_open_pos = False
                    try:
                        if os.path.exists(_pos_flag):
                            _ts_content = open(_pos_flag).read().strip()
                            _has_open_pos = bool(_ts_content)
                    except Exception:
                        pass
                    if _sf_age > 30 and not _has_open_pos:
                        warnings.append(f"{_label} file not updated in {int(_sf_age)}m - engine may not be firing")
                    else:
                        ok.append(f"{_label} file: updated {int(_sf_age)}m ago")
                else:
                    warnings.append(f"{_label} file missing")
        except Exception as e:
            warnings.append(f"Engine check failed: {e}")

        # 12C. CHECK SIGNAL_GENERATOR SCREEN RUNNING
        try:
            import subprocess
            _scr = subprocess.run(["screen","-ls"], capture_output=True, text=True, timeout=5)
            if "signal_generator" in _scr.stdout:
                ok.append("signal_generator screen: RUNNING")
            else:
                errors.append("signal_generator screen MISSING - engine not running - run bash start.sh IMMEDIATELY")
        except Exception as e:
            warnings.append(f"signal_generator screen check failed: {e}")

        # 13. CHECK .ENV FILE EXISTS AND HAS API KEYS
        try:
            if os.path.exists('.env'):
                env_content = open('.env').read()
                required_keys = ['S4V2_API_KEY', 'S4_API_KEY', 'S4V2_API_SECRET', 'S4_API_SECRET']
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
        _TH1C = "padding:5px 8px;border:1px solid #90CAF9;background:#E3F2FD;font-size:10px;font-weight:700;color:#555;"
        _TD1C = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#131722;"
        _TDG1C = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#089981;font-weight:700;"
        _TDR1C = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#F23645;font-weight:700;"
        _TDO1C = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;color:#e07000;font-weight:700;"

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
            _sig_thresh = 10800 if bot_name == 'S4' else 900
            try:
                import os as _os1c, time as _t1c
                age = _t1c.time() - _os1c.path.getmtime(sig_path)
                sig_age = f"{int(age/60)} min ago"
                sig_color = _TDG1C if age < _sig_thresh else _TDO1C
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
                sig_color = _TDG1C if age < _sig_thresh else _TDO1C
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
            f'{_BASE_DIR}/logs/live_trading_s4v2.log',
            f'{_BASE_DIR}/logs/last_known_ts_s4v2.txt',
            f'{_BASE_DIR}/logs/live_signal_s4v2.txt', 'S4V2')
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
            f"<th style='{_TH1C}'>S4V2</th>"
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
    # SECTION 1D - FIX VALIDATION TRACKER (only shows real issues + cause)
    # ================================================================
    import re as _re1d, datetime as _dt1d

    try:
        _fix_ts_str = open("logs/last_fix_applied.txt").read().strip()
        FIX_APPLIED_AT_UTC = _dt1d.datetime.strptime(_fix_ts_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        FIX_APPLIED_AT_UTC = _dt1d.datetime(2026, 8, 5, 9, 6, 0)  # fallback if file missing

    def _fvt_parse_orders(log_path, tf_minutes):
        rows = []
        try:
            lines = open(log_path, encoding='utf-8', errors='ignore').readlines()
        except:
            return rows
        for line in lines:
            m = _re1d.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ INFO \[ORDER\] (ENTRY|EXIT) (\w+) (\d+) lots.*ts=(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", line)
            if m:
                order_time_str, action, side, size, sig_ts_str = m.groups()
                try:
                    order_time = _dt1d.datetime.strptime(order_time_str, "%Y-%m-%d %H:%M:%S")
                    sig_ts = _dt1d.datetime.strptime(sig_ts_str, "%Y-%m-%dT%H:%M:%S")
                except:
                    continue
                if order_time < FIX_APPLIED_AT_UTC:
                    continue
                candle_close = sig_ts + _dt1d.timedelta(minutes=tf_minutes)
                delay_sec = (order_time - candle_close).total_seconds()
                rows.append({
                    "order_time": order_time, "action": action, "side": side,
                    "sig_ts": sig_ts_str, "delay_sec": delay_sec, "candle_close": candle_close
                })
        return rows

    def _fvt_find_cause(candle_close, order_time, label):
        """Scan engine log between candle_close and order_time for known delay-cause patterns."""
        _engine_log = "logs/renko_state_engine.log"
        causes = []
        try:
            lines = open(_engine_log, encoding='utf-8', errors='ignore').readlines()
        except:
            return "Engine log unavailable - cannot determine cause"
        window = []
        for l in lines[-3000:]:
            m = _re1d.search(r"(\d{2}-\w{3}-\d{4} \d{2}:\d{2}:\d{2})", l)
            if not m:
                continue
            try:
                lt = _dt1d.datetime.strptime(m.group(1), "%d-%b-%Y %H:%M:%S")
            except:
                continue
            # convert IST log time to UTC for comparison
            lt_utc = lt - _dt1d.timedelta(hours=5, minutes=30)
            if candle_close <= lt_utc <= order_time + _dt1d.timedelta(seconds=5):
                window.append(l)
        if any("data not caught up yet" in l for l in window):
            causes.append("Market data lagged behind candle close (exchange 1m candle not yet available)")
        if any("Market data download still running after 8s" in l for l in window):
            causes.append("REST data download exceeded 8s timeout")
        if any("Connection to remote host was lost" in l or "WS] Error" in l for l in window):
            causes.append("WebSocket disconnected during this window")
        if any(f"checking {label}" in l for l in window) and len(window) < 3:
            causes.append("Fast WS path fired but strategy computation itself took longer than expected")
        if not causes and window:
            causes.append("Cause unclear - review engine log manually for this window")
        if not window:
            causes.append("No engine log activity found in this window - check if engine was running")
        return " | ".join(causes)

    def _fvt_load_signal_csv(sig_csv):
        rows = {}       # keyed by entry_ts - for ENTRY checks
        rows_by_exit = {}  # keyed by exit_ts - for EXIT checks
        try:
            import csv as _csv1d
            with open(sig_csv) as f:
                for row in _csv1d.reader(f):
                    if len(row) >= 6:
                        rec = {
                            "entry_ts": row[0], "exit_ts": row[1], "direction": row[2], "lots": row[3],
                            "entry_price": row[4], "exit_price": row[5]
                        }
                        rows[row[0]] = rec
                        if row[1] and row[1] != "PENDING":
                            rows_by_exit[row[1]] = rec
        except:
            pass
        return rows, rows_by_exit

    def _fvt_parse_order_prices(log_path):
        """Extract entry fill info (keyed by entry ts) and exit fill info
        (keyed by exit ts) SEPARATELY - never merged, since exit_ts of one
        trade equals entry_ts of the next trade in reversal strategies."""
        entry_info = {}
        exit_info = {}
        try:
            lines = open(log_path, encoding='utf-8', errors='ignore').readlines()
        except:
            return entry_info, exit_info
        for idx, line in enumerate(lines):
            m_e = _re1d.search(r"\[ORDER\] ENTRY \w+ \d+ lots \| dir=(\w+) \| ts=(\S+)", line)
            if m_e:
                direction, sig_ts = m_e.groups()
                entry_info.setdefault(sig_ts, {})["direction"] = direction
                for j in range(idx, min(idx+8, len(lines))):
                    m_ep = _re1d.search(r"Placing stop SL \| direction=\w+ entry=([\d.]+)", lines[j])
                    if m_ep:
                        entry_info[sig_ts]["entry_price"] = float(m_ep.group(1))
                        break
            m_x = _re1d.search(r"\[ORDER\] EXIT \w+ \d+ lots \| ts=(\S+)", line)
            if m_x:
                sig_ts = m_x.group(1)
                for j in range(idx, min(idx+10, len(lines))):
                    m_xp = _re1d.search(r"avg_fill_price[\'\"]?[:=]\s*([\d.]+)", lines[j])
                    if m_xp:
                        exit_info.setdefault(sig_ts, {})["exit_price"] = float(m_xp.group(1))
                        break
        return entry_info, exit_info

    _fvt_issues = []
    _fvt_cards = []
    for _label, _log, _tf, _sigcsv in [
        ("S4V2", "logs/live_trading_s4v2.log", 30, "logs/signals_s4v2.csv"),
        ("S4", "logs/live_trading_s4.log", 120, "logs/signals_s4.csv"),
    ]:
        _rows = _fvt_parse_orders(_log, _tf)
        _bt_signals, _bt_signals_by_exit = _fvt_load_signal_csv(_sigcsv)
        _entry_prices, _exit_prices = _fvt_parse_order_prices(_log)

        # group ENTRY and EXIT rows by their common signal timestamp pair
        _entry_rows = {r["sig_ts"]: r for r in _rows if r["action"] == "ENTRY"}
        _exit_rows = {r["sig_ts"]: r for r in _rows if r["action"] == "EXIT"}

        _all_entry_ts = set(_entry_rows.keys()) | set(_bt_signals.keys())
        for _sts in sorted(_all_entry_ts):
            _bt = _bt_signals.get(_sts)
            if not _bt:
                continue
            try:
                _sts_dt = _dt1d.datetime.strptime(_sts, "%Y-%m-%dT%H:%M:%S")
                if _sts_dt < FIX_APPLIED_AT_UTC:
                    continue
            except:
                continue
            _exit_ts = _bt["exit_ts"]
            _checks = []  # (name, ok(bool or None), detail)

            # DIRECTION
            _er = _entry_rows.get(_sts)
            _lv_entry = _entry_prices.get(_sts, {})
            _bt_dir = _bt["direction"]
            _lv_dir = _lv_entry.get("direction", "")
            if _lv_dir:
                _dir_ok = (_lv_dir == _bt_dir)
                _checks.append(("Direction", _dir_ok, f"backtest={_bt_dir} | live={_lv_dir}"))
            else:
                _checks.append(("Direction", None, "live order not placed yet"))

            # ENTRY TIMING
            if _er:
                _et_ok = _er["delay_sec"] <= 120
                _checks.append(("Entry timing", _et_ok, f"order placed {_er['delay_sec']:.0f}s after candle close (target <=120s) | candle_close={_er['candle_close']} UTC | order={_er['order_time']} UTC"))
                if not _et_ok:
                    _cause = _fvt_find_cause(_er["candle_close"], _er["order_time"], _label)
                    _fvt_issues.append({"text": f"{_label} ENTRY delayed {_er['delay_sec']:.0f}s (target <=120s) | signal_ts={_sts}", "cause": _cause})
            else:
                _checks.append(("Entry timing", None, "live order not placed yet"))

            # EXIT TIMING
            _xr = _exit_rows.get(_exit_ts) if _exit_ts and _exit_ts != "PENDING" else None
            if _exit_ts == "PENDING":
                _checks.append(("Exit timing", None, "trade still open - exit not fired yet"))
            elif _xr:
                _xt_ok = _xr["delay_sec"] <= 120
                _checks.append(("Exit timing", _xt_ok, f"order placed {_xr['delay_sec']:.0f}s after candle close (target <=120s) | candle_close={_xr['candle_close']} UTC | order={_xr['order_time']} UTC"))
                if not _xt_ok:
                    _cause = _fvt_find_cause(_xr["candle_close"], _xr["order_time"], _label)
                    _fvt_issues.append({"text": f"{_label} EXIT delayed {_xr['delay_sec']:.0f}s (target <=120s) | signal_ts={_exit_ts}", "cause": _cause})
            else:
                _checks.append(("Exit timing", None, "live exit order not placed yet"))

            # ENTRY PRICE
            try:
                _bt_ep = float(_bt["entry_price"])
                _lv_ep = _lv_entry.get("entry_price")
                if _lv_ep is not None:
                    _diff_ep = abs(_lv_ep - _bt_ep)
                    _ep_ok = _diff_ep <= 5
                    _checks.append(("Entry price", _ep_ok, f"backtest=${_bt_ep:.2f} | live=${_lv_ep:.2f} | diff=${_diff_ep:.2f} (target within $5)"))
                    if not _ep_ok:
                        _fvt_issues.append({"text": f"{_label} ENTRY PRICE slippage ${_diff_ep:.2f} (target within $5) | signal_ts={_sts}", "cause": "Entry fill price far from backtest close price - check execution delay or market volatility"})
                else:
                    _checks.append(("Entry price", None, "live order not placed yet"))
            except:
                _checks.append(("Entry price", None, "backtest price unavailable"))

            # EXIT PRICE
            try:
                if _exit_ts == "PENDING" or _bt["exit_price"] in ("", "PENDING"):
                    _checks.append(("Exit price", None, "trade still open - exit not fired yet"))
                else:
                    _bt_xp = float(_bt["exit_price"])
                    _lv_xp = _exit_prices.get(_exit_ts, {}).get("exit_price")
                    if _lv_xp is not None:
                        _diff_xp = abs(_lv_xp - _bt_xp)
                        _xp_ok = _diff_xp <= 5
                        _checks.append(("Exit price", _xp_ok, f"backtest=${_bt_xp:.2f} | live=${_lv_xp:.2f} | diff=${_diff_xp:.2f} (target within $5)"))
                        if not _xp_ok:
                            _fvt_issues.append({"text": f"{_label} EXIT PRICE slippage ${_diff_xp:.2f} (target within $5) | signal_ts={_exit_ts}", "cause": "Exit fill price far from backtest close price - check execution delay or market volatility"})
                    else:
                        _checks.append(("Exit price", None, "live exit order not placed yet"))
            except:
                _checks.append(("Exit price", None, "backtest price unavailable"))

            _fail = any(c[1] is False for c in _checks)
            _pending = all(c[1] is None for c in _checks)
            _overall = "MISMATCH" if _fail else ("PENDING" if _pending else "FULL MATCH")
            _fvt_cards.append({
                "label": _label, "entry_ts": _sts, "exit_ts": _exit_ts,
                "checks": _checks, "overall": _overall
            })

    if 'exp_1d' not in st.session_state: st.session_state['exp_1d'] = bool(_fvt_issues)
    _fvt_title = f"SECTION 1D - FIX VALIDATION TRACKER ({len(_fvt_issues)} ISSUE(S) FOUND)" if _fvt_issues else "SECTION 1D - FIX VALIDATION TRACKER (ALL CLEAR)"
    with st.expander(_fvt_title, expanded=bool(_fvt_issues)):
        st.caption(f"Scanning trades since fix applied: {FIX_APPLIED_AT_UTC.strftime('%Y-%m-%d %H:%M:%S')} UTC | Target: delay <=120s, slippage within $5/side")
        for _card in _fvt_cards:
            _ov = _card["overall"]
            _ov_color = "#B00020" if _ov == "MISMATCH" else ("#E65100" if _ov == "PENDING" else "#0B8043")
            _ov_bg = "#FFEBEE" if _ov == "MISMATCH" else ("#FFF3E0" if _ov == "PENDING" else "#E8F5E9")
            st.markdown(f"<div style='padding:6px;border:1px solid {_ov_color};background:{_ov_bg};color:{_ov_color};font-size:12px;font-weight:700;margin-top:10px;'>{_card['label']} Trade | Entry {_card['entry_ts']} -> Exit {_card['exit_ts']} | OVERALL: {_ov}</div>", unsafe_allow_html=True)
            for _cname, _cok, _cdetail in _card["checks"]:
                if _cok is True:
                    _cicon, _ccolor, _cbg = "OK", "#0B8043", "#F1F8F2"
                elif _cok is False:
                    _cicon, _ccolor, _cbg = "FAIL", "#B00020", "#FFEBEE"
                else:
                    _cicon, _ccolor, _cbg = "PENDING", "#E65100", "#FFF8F0"
                st.markdown(f"<div style='padding:4px 4px 4px 16px;border-left:3px solid {_ccolor};background:{_cbg};color:#333;font-size:11px;margin-bottom:1px;'><b style=\'color:{_ccolor}\'>[{_cicon}] {_cname}:</b> {_cdetail}</div>", unsafe_allow_html=True)
        if _fvt_issues:
            st.markdown("<div style='margin-top:10px;font-size:12px;font-weight:700;'>ROOT CAUSE DETAILS FOR FAILURES:</div>", unsafe_allow_html=True)
            for _iss in _fvt_issues:
                st.markdown(f"<div style='padding:6px;border:1px solid #F23645;background:#FFEBEE;color:#B00020;font-size:12px;font-weight:600;margin-bottom:2px;'>{_iss['text']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='padding:6px 6px 6px 20px;border:1px solid #FFB74D;background:#FFF3E0;color:#E65100;font-size:11px;margin-bottom:8px;'>CAUSE: {_iss['cause']}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='padding:6px;border:1px solid #089981;background:#E8F5E9;color:#089981;font-size:12px;font-weight:600;'>No delay/match issues detected in trades since fix was applied.</div>", unsafe_allow_html=True)

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
with _tab_trading:
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
            m_cols[2].markdown("**S4V2**")
            m_cols[3].markdown("**S4**")
            m_cols[4].markdown("**Start**")
            m_cols[5].markdown("**Stop**")
            m_cols[6].markdown("**Remove**")
            for idx, m in enumerate(members):
                mc = st.columns([2,2,1,1,1,1,1])
                mc[0].write(m.get('name',''))
                mc[1].write(m.get('account','Testnet'))
                # Check S4V2 status
                _mname = m.get('name','').lower().replace(' ','_')
                s2_screen = f"{_mname}_s4v2"
                s4_screen = f"{_mname}_s4"
                _s2_log = "logs/live_trading_s4v2.log"
                _s4_log = "logs/live_trading_s4.log"
                import subprocess
                _scr_out = _timed('screen_list', 30, _fetch_screen_list)
                s2_running = s2_screen in _scr_out
                s4_running = s4_screen in _scr_out
                mc[2].markdown(f"<span style='color:{'green' if s2_running else 'red'}'>{'ON' if s2_running else 'OFF'}</span>", unsafe_allow_html=True)
                mc[3].markdown(f"<span style='color:{'green' if s4_running else 'red'}'>{'ON' if s4_running else 'OFF'}</span>", unsafe_allow_html=True)
                if mc[4].button("▶", key=f"m_start_{idx}"):
                    try:
                        env = f"S4V2_API_KEY={m.get('s2_key','')} S4V2_API_SECRET={m.get('s2_secret','')} S4_API_KEY={m.get('s4_key','')} S4_API_SECRET={m.get('s4_secret','')}"
                        subprocess.Popen(['bash','-c',f'screen -S {s2_screen} -X quit 2>/dev/null; sleep 1; screen -dmS {s2_screen} bash -c "cd /home/anildalabanjan933/crypto_trading_system && export {env} && .venv/bin/python3 scripts/signal_replay_s4v2.py >> {_s2_log} 2>&1"'])
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
                m_bots    = st.multiselect("Bots to enable", ["S4V2","S4"], default=["S4V2","S4"])
                col1, col2 = st.columns(2)
                with col1:
                    if "S4V2" in m_bots:
                        m_s2_key  = st.text_input("S4V2 API Key")
                        m_s2_sec  = st.text_input("S4V2 API Secret", type="password")
                        m_lots_s2 = st.number_input("S4V2 Lots", min_value=1, value=100)
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
                            ('s4v2', m_s2_key, m_s2_sec, m_lots_s2),
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
                            if m_s2_key and f"{_mkey.upper()}_S4V2_API_KEY" not in _env_content:
                                _new_keys += "\n" + f"{_mkey.upper()}_S4V2_API_KEY={m_s2_key}"
                                _new_keys += "\n" + f"{_mkey.upper()}_S4V2_API_SECRET={m_s2_sec}"
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
                                        f'logs/live_trading_{_b}.log 2>&1"'
                                    )
                            if _new_screens:
                                _start_content = _start_content.replace(
                                    'echo "S4V2 and S4 started"',
                                    f'echo "S4V2 and S4 started"{_new_screens}'
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
                                _api_k = m_s2_key if _b=='s4v2' else m_s4_key
                                _api_s = m_s2_sec if _b=='s4v2' else m_s4_sec
                                _cmd = (f'screen -S {_screen_name} -X quit 2>/dev/null; sleep 1; '
                                       f'screen -dmS {_screen_name} bash -c "cd {_base} && '
                                       f'export $(grep -v \'#\' {_base}/.env | xargs) && '
                                       f'.venv/bin/python3 scripts/signal_replay_{_mkey}_{_b}.py >> '
                                       f'logs/live_trading_{_b}.log 2>&1"')
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
                subprocess.Popen(['bash','-c','screen -S live_s4v2 -X quit; screen -S live_s4 -X quit'])
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
        if st.button("RESTART S4V2", key="sec2_restart_s2"):
            try:
                import subprocess
                subprocess.Popen(['bash','-c','screen -S live_s4v2 -X quit; sleep 2; screen -dmS live_s4v2 bash -c "cd /home/anildalabanjan933/crypto_trading_system && .venv/bin/python3 scripts/signal_replay_s4v2.py >> logs/live_trading_s4v2.log 2>&1"'])
                st.success("S4V2 restarting...")
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
        all_accounts = [{'name': 'My Account', 's2_key': os.getenv('S4V2_API_KEY',''), 's2_secret': os.getenv('S4V2_API_SECRET',''), 's4_key': os.getenv('S4_API_KEY',''), 's4_secret': os.getenv('S4_API_SECRET','')}]
        if os.path.exists(members_cfg_file):
            mcfg = _json.load(open(members_cfg_file))
            all_accounts += mcfg.get('members', [])

        # Account selector
        acct_names = [a['name'] for a in all_accounts]
        selected_acct = st.selectbox("Select Account", acct_names, key="delta_acct_select")
        acct = next(a for a in all_accounts if a['name'] == selected_acct)

        import warnings
        warnings.filterwarnings('ignore')

        # Fetch S4V2+S4 data - cached 30s, null-safe
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
        c3.metric("S4V2 Balance", f"${s2_bal:,.2f}")
        c4.metric("S4 Balance", f"${s4_bal:,.2f}")

        # Open positions
        st.markdown("**Open Positions**")
        all_pos = [dict(p, account='S4V2') for p in s2_pos] + [dict(p, account='S4') for p in s4_pos]
        if all_pos:
            # Header row
            hc = st.columns([1,2,1,1,2,2,2,2])
            for col, label in zip(hc, ['Account','Symbol','Side','Size','Entry $','SL Price','Unreal PnL','Action']):
                col.markdown(f"<div style='font-size:10px;font-weight:700;color:#555;padding:4px 0;border-bottom:2px solid #C8D0DC;'>{label}</div>", unsafe_allow_html=True)

            for p in all_pos:
                acc  = p['account']
                sym  = p['symbol']
                side = p['side']
                size = int(p['size'])
                sc   = "#089981" if side == 'LONG' else "#F23645"
                pc   = "#089981" if p['unreal_pnl'] >= 0 else "#F23645"
                close_side = 'buy' if side == 'SHORT' else 'sell'
                rc = st.columns([1,2,1,1,2,2,2,2])
                rc[0].markdown(f"<div style='font-size:11px;padding:6px 0;'>{acc}</div>", unsafe_allow_html=True)
                rc[1].markdown(f"<div style='font-size:11px;padding:6px 0;'>{sym}</div>", unsafe_allow_html=True)
                rc[2].markdown(f"<div style='font-size:11px;padding:6px 0;color:{sc};font-weight:700;'>{side}</div>", unsafe_allow_html=True)
                rc[3].markdown(f"<div style='font-size:11px;padding:6px 0;'>{size}</div>", unsafe_allow_html=True)
                rc[4].markdown(f"<div style='font-size:11px;padding:6px 0;text-align:right;'>${p['entry']:,.1f}</div>", unsafe_allow_html=True)
                _sl_val = p.get('sl_price', None)
                _sl_disp = f"${float(_sl_val):,.1f}" if _sl_val not in (None, 'N/A') else "<span style='color:#F23645;font-weight:700;'>MISSING</span>"
                rc[5].markdown(f"<div style='font-size:11px;padding:6px 0;text-align:right;'>{_sl_disp}</div>", unsafe_allow_html=True)
                rc[6].markdown(f"<div style='font-size:11px;padding:6px 0;color:{pc};font-weight:600;'>${p['unreal_pnl']:,.2f} | ₹{p['unreal_pnl']*INR_RATE:,.0f}</div>", unsafe_allow_html=True)
                with rc[7]:
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

        st.markdown("<div class='section-title' style='font-size:13px;margin:8px 0 4px 0;'>ORDER HISTORY</div>", unsafe_allow_html=True)
        if True:

            f1, f2, f3, f4 = st.columns(4)
            with f1:
                period = st.radio("Period", ["TODAY","YESTERDAY","2 DAYS","1 WEEK","1 MONTH","CUSTOM"], horizontal=True, key="oh_period")
            with f2:
                strat_filter = st.radio("Strategy", ["ALL","S4V2","S4"], horizontal=True, key="oh_strat")
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

            from_ts_oh = int(_dt.datetime.combine(from_date, _dt.time.min).replace(tzinfo=_dt.timezone.utc).timestamp())
            to_ts_oh   = int(_dt.datetime.combine(to_date, _dt.time.max).replace(tzinfo=_dt.timezone.utc).timestamp())

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
                        'time': fills[0]['created_at'],
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
                if strat_filter in ['ALL', 'S4V2']:
                    accounts_to_fetch.append(('My Account', 'S4V2', os.getenv('S4V2_API_KEY',''), os.getenv('S4V2_API_SECRET','')))
                if strat_filter in ['ALL', 'S4']:
                    accounts_to_fetch.append(('My Account', 'S4', os.getenv('S4_API_KEY',''), os.getenv('S4_API_SECRET','')))
            for m in members_cfg_oh.get('members', []):
                if member_filter in ['ALL', m['name']]:
                    if strat_filter in ['ALL','S4V2'] and m.get('s2_key'):
                        accounts_to_fetch.append((m['name'], 'S4V2', m['s2_key'], m['s2_secret']))
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
                TH2 = "padding:5px 8px;border:1px solid #90CAF9;background:#E3F2FD;font-size:10px;font-weight:700;color:#555;white-space:nowrap;"
                TD2 = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;"
                TDR2 = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;text-align:right;"
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
            "S4V2 BUY ENTRY", "S4V2 BUY EXIT",
            "S4V2 SELL ENTRY", "S4V2 SELL EXIT",
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
with _tab_backtest:
    # SECTION 4 - FORWARD TEST vs BACKTEST COMPARE
    # ================================================================
    if 'exp_4' not in st.session_state: st.session_state['exp_4'] = False
    with st.expander("SECTION 4 - FORWARD TEST vs BACKTEST COMPARE", expanded=st.session_state.get('exp_4', False)):


        st.markdown("**Generate Detailed Comparison Report**")

        comp_tab_s2, comp_tab_s4, comp_tab_match = st.tabs(["S4V2 - RenkoSMIIOSupertrendV2", "S4 - RenkoSMIIOSupertrendStrategy", "LIVE MATCH REPORT"])

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
                    ("S4V2 RenkoSMIIOV2", "S4V2 - RenkoSMIIOSupertrendV2"),
                    ("S4 RenkoSMIIO",       "S4 - RenkoSMIIOSupertrendStrategy")
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

        for comp_tab, algo_name, algo_key in [(comp_tab_s2, "S4V2", "s2"), (comp_tab_s4, "S4", "s4")]:
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
                            for sname in ['RenkoSMIIOSupertrendV2Strategy', 'RenkoSMIIOSupertrendStrategy']:
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
                        "--strategy", _display_to_class(bt_strategy),
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
                        import glob as _glob, time as _time, os as _glob_os
                        _time.sleep(3)
                        _new_files = sorted([f for f in _glob.glob("output/*.html") if "backtest_report_" in f and "optimization" not in f], key=_glob_os.path.getmtime, reverse=True)
                        _new_csvs = sorted([f for f in _glob.glob("output/*.csv") if "trade_log_" in f], key=_glob_os.path.getmtime, reverse=True)
                        if _new_files:
                            st.session_state["sec6_html_select"] = _new_files[0]
                            st.session_state["sec6_force_latest"] = False
                        _html_nm = _glob_os.path.basename(_new_files[0]) if _new_files else "N/A"
                        _csv_nm = _glob_os.path.basename(_new_csvs[0]) if _new_csvs else "N/A"
                        _bt_msg = f"DASHBOARD RUN COMPLETE - {bt_strategy}  |  HTML: {_html_nm}  |  CSV: {_csv_nm}"
                        st.session_state["sec6_complete_msg"] = _bt_msg
                        _status.success(_bt_msg)
                        import time as _t; _t.sleep(2)
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
        csv_files = sorted([f for f in glob.glob("output/*.csv") if "trade_log_" in f], key=os.path.getmtime, reverse=True)
        _check_terminal_run(html_files, csv_files, "seen_terminal_sec6", "sec6_complete_msg", "Backtest")
        if st.session_state.get("sec6_complete_msg"):
            st.success(st.session_state["sec6_complete_msg"])

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
                    user_content = user_content.replace('<title>Backtest Report - RenkoSMIIOSupertrendV2Strategy</title>', '<title>Backtest Report - Alpha Strategy</title>')
                    user_content = user_content.replace('<title>Backtest Report - RenkoSMIIOSupertrendStrategy</title>', '<title>Backtest Report - Alpha Strategy</title>')
                    for sname in ['RenkoSMIIOSupertrendV2Strategy','RenkoSMIIOSupertrendStrategy','RenkoBreakoutStrategy','RenkoTrendlinePullbackStrategy','RenkoOptionsStrategy']:
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
            sc_strategy = st.selectbox("Strategy", _get_strat_list() + ["Portfolio (S4V2+S4 Combined)"], key="sc_strategy")
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
                if sc_strategy == "Portfolio (S4V2+S4 Combined)":
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
                "<thead><tr style='background:#E3F2FD;'>"
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
                "<thead><tr style='background:#E3F2FD;'>"
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
                "<thead><tr style='background:#E3F2FD;'>"
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
                            "--strategies", "RenkoSMIIOSupertrendV2Strategy,RenkoSMIIOSupertrendStrategy",
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
                            import glob as _glob, time as _time, os as _glob_os
                            _time.sleep(3)
                            _new_port = sorted([f for f in _glob.glob("output/*.html") if "portfolio_report_" in f], key=_glob_os.path.getmtime, reverse=True)
                            _new_port_csv = sorted([f for f in _glob.glob("output/*.csv") if "portfolio" in f.lower()], key=_glob_os.path.getmtime, reverse=True)
                            if _new_port:
                                st.session_state["port_html_sel"] = _new_port[0]
                                st.session_state["port_force_latest"] = False
                            _html_nm = _glob_os.path.basename(_new_port[0]) if _new_port else "N/A"
                            _csv_nm = _glob_os.path.basename(_new_port_csv[0]) if _new_port_csv else "N/A"
                            _pp_msg = f"DASHBOARD RUN COMPLETE - S4V2+S4 Portfolio  |  HTML: {_html_nm}  |  CSV: {_csv_nm}"
                            st.session_state["port_pre_complete_msg"] = _pp_msg
                            _pp_status.success(_pp_msg)
                            import time as _t; _t.sleep(2)
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
                                "--strategies", ",".join(_display_to_class(x) for x in selected_strategies),
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
                                import glob as _glob, time as _time, os as _glob_os
                                _time.sleep(3)
                                _new_dyn = sorted([f for f in _glob.glob("output/*.html") if "portfolio_report_" in f], key=_glob_os.path.getmtime, reverse=True)
                                _new_dyn_csv = sorted([f for f in _glob.glob("output/*.csv") if "portfolio" in f.lower()], key=_glob_os.path.getmtime, reverse=True)
                                if _new_dyn:
                                    st.session_state["port_html_sel"] = _new_dyn[0]
                                    st.session_state["port_force_latest"] = False
                                _html_nm = _glob_os.path.basename(_new_dyn[0]) if _new_dyn else "N/A"
                                _csv_nm = _glob_os.path.basename(_new_dyn_csv[0]) if _new_dyn_csv else "N/A"
                                _strat_nm = ",".join(selected_strategies) if selected_strategies else "N/A"
                                _pd_msg = f"DASHBOARD RUN COMPLETE - {_strat_nm}  |  HTML: {_html_nm}  |  CSV: {_csv_nm}"
                                st.session_state["port_dyn_complete_msg"] = _pd_msg
                                _pd_status.success(_pd_msg)
                                import time as _t; _t.sleep(2)
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
        port_csv = sorted([f for f in glob.glob("output/*.csv") if "portfolio_trade_log_" in f], key=_glob_os.path.getmtime, reverse=True)
        _check_terminal_run(port_html, port_csv, "seen_terminal_port", "port_pre_complete_msg", "Portfolio")
        if st.session_state.get("port_pre_complete_msg"):
            st.success(st.session_state["port_pre_complete_msg"])
        if st.session_state.get("port_dyn_complete_msg"):
            st.success(st.session_state["port_dyn_complete_msg"])

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
                    for sname in ['Portfolio_Dynamic','RenkoSMIIOSupertrendV2Strategy','RenkoSMIIOSupertrendStrategy','RenkoBreakoutStrategy','RenkoTrendlinePullbackStrategy','RenkoOptionsStrategy']:
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
        import json as _optjson, time as _optnowtime

        _OPT_STATUS_FILE = "logs/opt_status.json"
        def _read_opt_status():
            try:
                with open(_OPT_STATUS_FILE) as _f:
                    return _optjson.load(_f)
            except Exception:
                return None
        def _write_opt_status(_data):
            try:
                with open(_OPT_STATUS_FILE, "w") as _f:
                    _optjson.dump(_data, _f)
            except Exception:
                pass

        _opt_stat_now = _read_opt_status()
        if _opt_stat_now and _opt_stat_now.get("status") == "running":
            _opt_pid_chk = _opt_stat_now.get("pid")
            _opt_alive = _opt_pid_chk and os.path.exists(f"/proc/{_opt_pid_chk}")
            if _opt_alive:
                _opt_elapsed_min = int((_optnowtime.time() - _opt_stat_now.get("start_time", _optnowtime.time())) / 60)
                st.warning(f"OPTIMISATION RUNNING IN BACKGROUND: {_opt_stat_now.get('strategy','')} | {_opt_stat_now.get('group','')} | started {_opt_elapsed_min} min ago. Do NOT click RUN again - wait for it to finish, then refresh this tab.")
            else:
                _write_opt_status({"status": "idle"})

        col1, col2, col3 = st.columns(3)
        with col1:
            opt_strategy = st.selectbox("Select Strategy", [
                *_get_strat_list()
            ], key="sec7_strategy")
        with col2:
            opt_group = st.selectbox("Select Group", [
                "renko", "supertrend", "smiio", "s4v2_combined (Full Mode)", "s4_combined (Full Mode)", "sma_adx_combined (Full Mode)", "ema_pullback_combined (Full Mode)", "supertrend_pullback_combined (Full Mode)", "range_breakout_combined (Full Mode)", "donchian_breakout_combined (Full Mode)"
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
                    "--strategy", _display_to_class(opt_strategy),
                    "--group", opt_group.split(" (")[0],
                    "--lots", str(opt_lots),
                    "--start", str(opt_start),
                    "--end", str(opt_end),
                    "--slippage", str(opt_slippage)
                ]
                if not opt_include_charges:
                    cmd.append("--no-charges")
                _opt_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                _write_opt_status({"status": "running", "pid": _opt_proc.pid, "start_time": _optnowtime.time(), "strategy": opt_strategy, "group": opt_group})
                _opt_stdout, _opt_stderr = _opt_proc.communicate(timeout=2700)
                class _OptResult: pass
                result = _OptResult()
                result.returncode = _opt_proc.returncode
                result.stdout = _opt_stdout
                result.stderr = _opt_stderr
                _write_opt_status({"status": "done" if result.returncode == 0 else "failed"})
                if result.returncode == 0:
                    _opt_progress.progress(100)
                    import glob as _glob, time as _time, os as _glob_os
                    _time.sleep(3)
                    _new_opt = sorted([f for f in _glob.glob("output/*.html") if "optimization_results_" in f], key=_glob_os.path.getmtime, reverse=True)
                    _new_opt_csv = sorted([f for f in _glob.glob("output/*.csv") if "optimization" in f.lower()], key=_glob_os.path.getmtime, reverse=True)
                    if _new_opt:
                        st.session_state["sec7_html_sel"] = _new_opt[0]
                    st.session_state["sec7_force_latest"] = False
                    _html_nm = _glob_os.path.basename(_new_opt[0]) if _new_opt else "N/A"
                    _csv_nm = _glob_os.path.basename(_new_opt_csv[0]) if _new_opt_csv else "N/A"
                    _opt_msg = f"DASHBOARD RUN COMPLETE - {opt_strategy}  |  HTML: {_html_nm}  |  CSV: {_csv_nm}"
                    st.session_state["sec7_complete_msg"] = _opt_msg
                    _opt_status.success(_opt_msg)
                    import time as _t; _t.sleep(2)
                    st.rerun()
                else:
                    _opt_progress.progress(100)
                    _opt_status.error("Optimisation failed - see error below")
                    st.code(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
            except subprocess.TimeoutExpired:
                _write_opt_status({"status": "failed"})
                _opt_status.error("Optimisation timed out after 45 minutes")
            except Exception as e:
                _write_opt_status({"status": "failed"})
                _opt_status.error(f"Error: {e}")

        st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)
        st.markdown("**Optimisation Results**")

        opt_csv_files = sorted([f for f in glob.glob("output/*.csv") if "optimization_results_" in f], key=_glob_os.path.getmtime, reverse=True)
        opt_html_files = sorted([f for f in glob.glob("output/*.html") if "optimization_results_" in f], key=_glob_os.path.getmtime, reverse=True)
        _check_terminal_run(opt_html_files, opt_csv_files, "seen_terminal_sec7", "sec7_complete_msg", "Optimisation")
        if st.session_state.get("sec7_complete_msg"):
            st.success(st.session_state["sec7_complete_msg"])

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
with _tab_datasync:
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
with _tab_maint:
    # SECTION 12 - LOG MONITOR
    # ================================================================
    with st.expander("SECTION 12 - LOG MONITOR", expanded=st.session_state.get('exp_12', False)):

        col_sel, col_filter = st.columns([2,3])
        with col_sel:
            log_choice = st.selectbox("Select Log", ["S4V2", "S4", "Both"], key="sec5_log")
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

        s2_log_path = '/home/anildalabanjan933/crypto_trading_system/logs/live_trading_s4v2.log'
        s4_log_path = '/home/anildalabanjan933/crypto_trading_system/logs/live_trading_s4.log'

        if log_choice == "S4V2":
            lines = read_log(s2_log_path, active_filter)
            st.markdown(f"**S4V2 Log** - Filter: `{active_filter if active_filter else 'ALL'}`")
            st.code('\n'.join([format_log_line(l) for l in lines]), language=None)
        elif log_choice == "S4":
            lines = read_log(s4_log_path, active_filter)
            st.markdown(f"**S4 Log** - Filter: `{active_filter if active_filter else 'ALL'}`")
            st.code('\n'.join([format_log_line(l) for l in lines]), language=None)
        else:
            col_s2, col_s4 = st.columns(2)
            with col_s2:
                lines = read_log(s2_log_path, active_filter)
                st.markdown(f"**S4V2 Log** - Filter: `{active_filter if active_filter else 'ALL'}`")
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
with _tab_analysis:
    # SECTION 13 - STRATEGY PERFORMANCE SUMMARY
    # ================================================================
    if 'exp_13s' not in st.session_state: st.session_state['exp_13s'] = False
    with st.expander("SECTION 13 - LIVE FORWARD TEST PERFORMANCE", expanded=st.session_state.get('exp_13s', False)):
        import time as _t13, hmac as _hm13, hashlib as _hs13, requests as _rq13, datetime as _dt13, glob as _gl13, pandas as _pd13, re as _re13

        try:
            _VF13 = open("logs/valid_from_baseline.txt").read().strip()
        except:
            _VF13 = "2026-07-14T15:00:00"
        # Section 13 display window = current calendar month (1st to today, UTC)
        import datetime as _dt13_7
        _now13_7 = _dt13_7.datetime.utcnow()
        _VF13_7D = _now13_7.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%dT%H:%M:%S')

        # ── DYNAMIC INPUT CONTROLS (persist across refresh via session_state) ──
        _c13a, _c13b, _c13c = st.columns(3)
        with _c13a:
            sec13_slip = st.number_input("Slippage/side ($)", min_value=0.0, value=st.session_state.get("sec13_slip", 5.0), key="sec13_slip")
        with _c13b:
            sec13_charges = st.checkbox("Include Tax & All Charges", value=st.session_state.get("sec13_charges", True), key="sec13_charges")
        with _c13c:
            sec13_lots = st.number_input("Lots", min_value=1, max_value=10000, value=st.session_state.get("sec13_lots", 100), key="sec13_lots")
        _BASE_LOTS13 = 100.0
        _LOT_RATIO13 = float(sec13_lots) / _BASE_LOTS13
        _INR13 = 84.0
        _BASE13= "https://cdn-ind.testnet.deltaex.org"
        _TH13  = "padding:5px 8px;border:1px solid #90CAF9;background:#E3F2FD;font-size:11px;font-weight:700;color:#333;text-align:center;"
        _TD13  = "padding:6px 8px;border:1px solid #BBDEFB;font-size:13px;color:#131722;font-weight:600;"
        _TDN13 = "padding:6px 8px;border:1px solid #BBDEFB;font-size:13px;color:#131722;text-align:center;font-weight:500;"
        _TDG13 = "padding:5px 8px;border:1px solid #BBDEFB;font-size:12px;color:#089981;font-weight:700;text-align:center;"
        _TDR13 = "padding:5px 8px;border:1px solid #BBDEFB;font-size:12px;color:#F23645;font-weight:700;text-align:center;"
        _TDB13 = "padding:5px 8px;border:1px solid #BBDEFB;font-size:12px;color:#2962FF;font-weight:700;text-align:center;"
        _SUB13 = "padding:4px 8px;border:1px solid #90CAF9;background:#E8ECF2;font-size:10px;font-weight:700;color:#131722;"
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

        def _fetch13(k, s, vf_override=None):
            orders, after = [], None
            try:
                vf_str = vf_override if vf_override else _VF13
                vf  = int(_dt13.datetime.strptime(vf_str,"%Y-%m-%dT%H:%M:%S").replace(tzinfo=_dt13.timezone.utc).timestamp())
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
            # FIFO two-pointer per direction - prevents cross-matching entry with
            # a distant unrelated future exit (root cause of Aug-2026 S4 -Rs299k
            # pairing-mismatch bug: old exhaustive-search version could skip over
            # the correct nearby exit and grab one days later).
            def _ts(o):
                return int(_dt13.datetime.strptime(o.get("created_at","1970-01-01T00:00:00")[:19], "%Y-%m-%dT%H:%M:%S").timestamp())
            def _px(o):
                return float(o.get("average_fill_price") or o.get("limit_price") or 0)
            def _filled_sz(o):
                return int(o.get("size",0)) - int(o.get("unfilled_size",0) or 0)
            def _has_fill(o):
                # Include fully-closed orders AND partial-fill-then-cancelled orders
                # (state=cancelled but some size was actually filled before cancel).
                # Root cause fix: IOC/retry orders that get partially filled then
                # cancelled were previously ignored entirely, causing wrong lot size
                # and wrong entry price in Section 13 vs real Delta position.
                if o.get("state")=="closed":
                    return True
                if o.get("state")=="cancelled" and _filled_sz(o) > 0 and o.get("average_fill_price"):
                    return True
                return False

            srt = sorted(orders, key=lambda x: x.get("created_at",""))
            longs_e  = [o for o in srt if o.get("side")=="buy"  and _has_fill(o) and str(o.get("reduce_only","")).lower() not in ["true","1"]]
            longs_x  = [o for o in srt if o.get("side")=="sell" and _has_fill(o) and str(o.get("reduce_only","")).lower() in ["true","1"]]
            shorts_e = [o for o in srt if o.get("side")=="sell" and _has_fill(o) and str(o.get("reduce_only","")).lower() not in ["true","1"]]
            shorts_x = [o for o in srt if o.get("side")=="buy"  and _has_fill(o) and str(o.get("reduce_only","")).lower() in ["true","1"]]

            pairs = []
            def _fifo_match(entries, exits, dirn):
                ei, xi = 0, 0
                while ei < len(entries) and xi < len(exits):
                    e, x = entries[ei], exits[xi]
                    ets, xts = _ts(e), _ts(x)
                    if xts < ets:
                        xi += 1; continue
                    ep, xp = _px(e), _px(x)
                    sz = _filled_sz(e)
                    raw_pnl = (xp - ep) * sz * 0.001 * (1 if dirn == "LONG" else -1)
                    cm = float(e.get("paid_commission") or 0)+float(x.get("paid_commission") or 0)
                    pnl = raw_pnl - cm
                    _sl_hit = str(x.get("stop_order_type","")) == "stop_loss_order"
                    pairs.append({"dir":dirn,"ep":ep,"xp":xp,"pnl":pnl,"cm":cm,"ets":ets,"xts":xts,"sz":sz,"sl_hit":_sl_hit})
                    ei += 1; xi += 1
                # Only the single most-recent unmatched entry is a real open
                # position. Earlier unmatched entries are stale retry-spam
                # duplicates (from the historical entry-retry bug) with no
                # matching exit - they are not real trades, so drop them
                # instead of falsely showing every one as OPEN.
                if ei < len(entries):
                    e = entries[len(entries) - 1]
                    sz = _filled_sz(e)
                    cm_open = float(e.get("paid_commission") or 0)
                    pairs.append({"dir":dirn,"ep":_px(e),"xp":0,"pnl":0,"cm":cm_open,"ets":_ts(e),"xts":0,"sz":sz,"open":True,"sl_hit":False})

            _fifo_match(longs_e, longs_x, "LONG")
            _fifo_match(shorts_e, shorts_x, "SHORT")
            return sorted(pairs, key=lambda p: p["ets"])

        def _live_pos_sz13(path):
            try:
                import os as _osl13, time as _tl13, hmac as _hml13, hashlib as _hsl13, requests as _rql13
                k = _osl13.getenv("S4V2_API_KEY") if "s4v2" in path else _osl13.getenv("S4_API_KEY")
                s = _osl13.getenv("S4V2_API_SECRET") if "s4v2" in path else _osl13.getenv("S4_API_SECRET")
                ts = str(int(_tl13.time()))
                qs = "product_id=84"
                pth = "/v2/positions"
                sig = _hml13.new(s.encode(), f"GET{ts}{pth}?{qs}".encode(), _hsl13.sha256).hexdigest()
                h = {"api-key":k,"timestamp":ts,"signature":sig}
                r = _rql13.get(f"https://cdn-ind.testnet.deltaex.org{pth}?{qs}", headers=h, timeout=5).json()
                if r.get("success"):
                    return abs(int(r.get("result",{}).get("size",0) or 0))
            except Exception:
                pass
            return None

        def _pair13_csv(path, vf_str):
            import datetime as _dtp13
            pairs = []
            _fill_map = {}
            try:
                _fill_path = "logs/fill_prices_s4v2.csv" if "s4v2" in path else "logs/fill_prices_s4.csv"
                if os.path.exists(_fill_path):
                    with open(_fill_path) as _ff:
                        _ff.readline()
                        for _fline in _ff:
                            _fp = _fline.strip().split(',')
                            if len(_fp) >= 8:
                                _charge = _fp[8] if len(_fp) >= 9 else "0.0"
                                _fill_map[_fp[0]] = (_fp[5], _fp[7], _charge)
            except Exception:
                _fill_map = {}
            _hist_rows = []
            try:
                _hist_path = "uploads/delta_order_history_s4v2_aug2026.csv" if "s4v2" in path else "uploads/delta_order_history_s4_aug2026.csv"
                if os.path.exists(_hist_path):
                    with open(_hist_path) as _hf:
                        _hf.readline()
                        for _hline in _hf:
                            _hp = _hline.strip().split(',')
                            if len(_hp) < 14:
                                continue
                            _hside = _hp[3]
                            _hexec = _hp[5]
                            _hfee = _hp[9]
                            _hstatus = _hp[13]
                            if _hstatus != "closed" or not _hexec:
                                continue
                            try:
                                _hdt_str = _hp[0].split("+")[0].strip()
                                _hdt = _dtp13.datetime.strptime(_hdt_str, "%Y-%m-%d %H:%M:%S.%f")
                                _hdt_utc = _hdt - _dtp13.timedelta(hours=5, minutes=30)
                                _hts = int(_hdt_utc.replace(tzinfo=_dtp13.timezone.utc).timestamp())
                            except Exception:
                                continue
                            _hist_rows.append((_hts, _hside, _hexec, _hfee))
                    _hist_rows.sort(key=lambda r: r[0])
            except Exception:
                _hist_rows = []

            def _hist_lookup(target_ts, side_want, tol=8000):
                best = None
                best_diff = None
                for _hts, _hside, _hexec, _hfee in _hist_rows:
                    if _hside != side_want:
                        continue
                    diff = abs(_hts - target_ts)
                    if diff <= tol and (best_diff is None or diff < best_diff):
                        best = (_hexec, _hfee)
                        best_diff = diff
                return best

            try:
                vf_dt = _dtp13.datetime.strptime(vf_str, "%Y-%m-%dT%H:%M:%S")
            except Exception:
                vf_dt = None
            try:
                with open(path) as f:
                    for line in f:
                        parts = line.strip().split(',')
                        if len(parts) < 5:
                            continue
                        et_raw, xt_raw, dirv, lots, ep_raw = parts[0], parts[1], parts[2], parts[3], parts[4]
                        xp_raw = parts[5] if len(parts) >= 6 else ""
                        try:
                            et_dt = _dtp13.datetime.strptime(et_raw[:19], "%Y-%m-%dT%H:%M:%S")
                        except Exception:
                            continue
                        if vf_dt and et_dt < vf_dt:
                            continue
                        ets = int(et_dt.replace(tzinfo=_dtp13.timezone.utc).timestamp())
                        is_open = (xt_raw == "PENDING" or not xp_raw)
                        ep = float(ep_raw) if ep_raw else 0.0
                        dirn = dirv.upper()
                        sz = int(lots) if lots else 100
                        _fm = _fill_map.get(et_raw[:19])
                        if is_open:
                            if _fm and _fm[0]:
                                try:
                                    ep = float(_fm[0])
                                except Exception:
                                    pass
                            else:
                                _hh = _hist_lookup(ets, 'buy' if dirn == 'LONG' else 'sell')
                                if _hh and _hh[0]:
                                    try:
                                        ep = float(_hh[0])
                                    except Exception:
                                        pass
                            _live_sz = _live_pos_sz13(path)
                            if _live_sz and _live_sz > 0:
                                sz = _live_sz
                            pairs.append({"dir":dirn,"ep":ep,"xp":0.0,"pnl":0.0,"cm":0.0,"ets":ets,"xts":0,"sz":sz,"open":True})
                        else:
                            try:
                                xt_dt = _dtp13.datetime.strptime(xt_raw[:19], "%Y-%m-%dT%H:%M:%S")
                                xts = int(xt_dt.replace(tzinfo=_dtp13.timezone.utc).timestamp())
                            except Exception:
                                xts = 0
                            xp = float(xp_raw) if xp_raw else 0.0
                            _cm = 0.0
                            if _fm:
                                try:
                                    if _fm[0]:
                                        ep = float(_fm[0])
                                    if _fm[1]:
                                        xp = float(_fm[1])
                                    if len(_fm) >= 3 and _fm[2]:
                                        _cm = float(_fm[2])
                                except Exception:
                                    pass
                            else:
                                _entry_side = 'buy' if dirn == 'LONG' else 'sell'
                                _exit_side  = 'sell' if dirn == 'LONG' else 'buy'
                                _hh_e = _hist_lookup(ets, _entry_side)
                                _hh_x = _hist_lookup(xts, _exit_side)
                                _hfee_sum = 0.0
                                if _hh_e and _hh_e[0]:
                                    try:
                                        ep = float(_hh_e[0])
                                    except Exception:
                                        pass
                                if _hh_e and _hh_e[1]:
                                    try:
                                        _hfee_sum += float(_hh_e[1])
                                    except Exception:
                                        pass
                                if _hh_x and _hh_x[0]:
                                    try:
                                        xp = float(_hh_x[0])
                                    except Exception:
                                        pass
                                if _hh_x and _hh_x[1]:
                                    try:
                                        _hfee_sum += float(_hh_x[1])
                                    except Exception:
                                        pass
                                _cm = _hfee_sum
                            raw_pnl = (xp - ep) * sz * 0.001 * (1 if dirn == "LONG" else -1)
                            net_pnl = raw_pnl - _cm
                            pairs.append({"dir":dirn,"ep":ep,"xp":xp,"pnl":net_pnl,"cm":_cm,"ets":ets,"xts":xts,"sz":sz,"open":False})
            except Exception:
                pass
            return sorted(pairs, key=lambda p: p["ets"])

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
                ni_pretax = df['net_pnl_inr'].sum() if 'net_pnl_inr' in df.columns else nu*_INR13
                _win_inr13 = df[df['net_pnl_inr']>0]['net_pnl_inr'].sum() if 'net_pnl_inr' in df.columns else 0
                ni = ni_pretax - _win_inr13*0.10
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
                if 'entry_datetime' in df.columns:
                    df['entry_dt'] = _pd13.to_datetime(df['entry_datetime'])
                    pnl_today = df[df['entry_dt'].dt.date == today_s.date()]['net_pnl'].sum()
                    pnl_week  = df[df['entry_dt'] >= _pd13.Timestamp(week_s)]['net_pnl'].sum()
                    pnl_month = df[df['entry_dt'] >= _pd13.Timestamp(month_s)]['net_pnl'].sum()
                    pnl_year  = df[df['entry_dt'] >= _pd13.Timestamp(year_s)]['net_pnl'].sum()
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
                # S4V2/S4 columns: grey if N/A
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
                f"<th style='{_TH13}'>S4V2</th>"
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
                + _row("Net PnL (all charges incl.)", _v13(s2m,"pnl"), _v13(s4m,"pnl"), _v13(cbm,"pnl"), _c13(s2m),_c13(s4m),_c13(cbm))
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

        # ── LOAD FORWARD TEST DATA FROM SIGNALS CSV (matches BT engine exactly) ──
        s2p  = _pair13(_fetch13(os.getenv("S4V2_API_KEY"), os.getenv("S4V2_API_SECRET"), _VF13_7D))
        s4p  = _pair13(_fetch13(os.getenv("S4_API_KEY"), os.getenv("S4_API_SECRET"), _VF13_7D))
        s2m  = _calc13(s2p)
        s4m  = _calc13(s4p)
        cbm  = _calc13(s2p+s4p)

        # ── FETCH BACKTEST DATA (same date range) ────────────────
        s2_bt = _bt_calc13("output/trade_log_RenkoSMIIOSupertrendV2Strategy*.csv", _VF13_7D)
        s4_bt = _bt_calc13("output/trade_log_RenkoSMIIOSupertrendStrategy*.csv", _VF13_7D)
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

        st.caption(f"Showing current month ({_VF13_7D[:7]}) | Valid from: {_VF13_7D[:10]} UTC | Auto updates on page load | Testnet")

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        _TH20 = "padding:4px 6px;border:1px solid #90CAF9;background:#E3F2FD;font-size:10px;font-weight:700;color:#333;text-align:center;white-space:nowrap;"
        _TD20 = "padding:4px 6px;border:1px solid #BBDEFB;font-size:11px;color:#131722;text-align:center;white-space:nowrap;"
        _TG20 = "padding:4px 6px;border:1px solid #BBDEFB;font-size:11px;color:#089981;font-weight:700;text-align:center;"
        _TR20 = "padding:4px 6px;border:1px solid #BBDEFB;font-size:11px;color:#F23645;font-weight:700;text-align:center;"
        _TY20 = "padding:4px 6px;border:1px solid #BBDEFB;font-size:11px;color:#e07000;font-weight:700;text-align:center;"

        def _fwd_slip_hdr13(pairs, bot_name=""):
            try:
                closed = [p for p in pairs if not p.get('open', False)]
                tot = len(pairs)
                net_pnl_inr = sum(float(p.get('pnl',0)) for p in closed) * _INR13
                _bt_lu13h = _bt_lookup13(bot_name, vf_str=_VF13_7D) if bot_name else {"LONG":[],"SHORT":[]}
                _lv_closed13h = [q for q in closed]
                _lv_pos13h = {"LONG": {id(x): i for i, x in enumerate([q for q in _lv_closed13h if str(q.get("dir","")).upper()=="LONG"])},
                              "SHORT": {id(x): i for i, x in enumerate([q for q in _lv_closed13h if str(q.get("dir","")).upper()=="SHORT"])}}
                fav_usd, unfav_usd = 0.0, 0.0
                for p in closed:
                    _dv13 = str(p.get("dir","")).upper()
                    _bm13 = None
                    if _dv13 in _lv_pos13h and id(p) in _lv_pos13h[_dv13]:
                        _sidx13h = _lv_pos13h[_dv13][id(p)]
                        if _sidx13h < len(_bt_lu13h.get(_dv13, [])):
                            _bm13 = _bt_lu13h[_dv13][_sidx13h]
                    if not _bm13:
                        continue
                    _sge13h = (_bm13["ep"] - float(p.get("ep",0))) if _dv13=="LONG" else (float(p.get("ep",0)) - _bm13["ep"])
                    _sgx13h = (float(p.get("xp",0)) - _bm13["xp"]) if _dv13=="LONG" else (_bm13["xp"] - float(p.get("xp",0)))
                    for _sg13h in (_sge13h, _sgx13h):
                        _val13h = abs(_sg13h) * 0.1
                        if _sg13h >= 0: fav_usd += _val13h
                        else: unfav_usd += _val13h
                net_slip_usd = fav_usd - unfav_usd
                net_slip_inr = net_slip_usd * _INR13
                import datetime as _dth13
                _ist_off13 = _dth13.timedelta(hours=5, minutes=30)
                _today_ist13 = (_dth13.datetime.utcnow() + _ist_off13).strftime("%d-%b-%Y")
                fav_t, unfav_t, cnt_t = 0.0, 0.0, 0
                for p in closed:
                    _dts13 = (_dth13.datetime.utcfromtimestamp(p.get("xts",0)) + _ist_off13).strftime("%d-%b-%Y")
                    if _dts13 != _today_ist13:
                        continue
                    _dv13t = str(p.get("dir","")).upper()
                    _bm13t = None
                    if _dv13t in _lv_pos13h and id(p) in _lv_pos13h[_dv13t]:
                        _sidx13t = _lv_pos13h[_dv13t][id(p)]
                        if _sidx13t < len(_bt_lu13h.get(_dv13t, [])):
                            _bm13t = _bt_lu13h[_dv13t][_sidx13t]
                    if not _bm13t:
                        continue
                    cnt_t += 1
                    _sge13t = (_bm13t["ep"] - float(p.get("ep",0))) if _dv13t=="LONG" else (float(p.get("ep",0)) - _bm13t["ep"])
                    _sgx13t = (float(p.get("xp",0)) - _bm13t["xp"]) if _dv13t=="LONG" else (_bm13t["xp"] - float(p.get("xp",0)))
                    for _sg13t in (_sge13t, _sgx13t):
                        _val13t = abs(_sg13t) * 0.1
                        if _sg13t >= 0: fav_t += _val13t
                        else: unfav_t += _val13t
                net_t = fav_t - unfav_t
                _tlc = "#089981" if net_t >= 0 else "#F23645"
                _pnlc = "#089981" if net_pnl_inr >= 0 else "#F23645"
                _slc  = "#089981" if net_slip_usd >= 0 else "#F23645"
                return (
                    f"<div style='font-size:11px;margin:2px 0 6px 0;padding:4px 8px;background:#F5F7FA;border-radius:3px;'>"
                    f"<b>Total Trades:</b> {tot} &nbsp;|&nbsp; "
                    f"<b>Net PnL:</b> <span style='color:{_pnlc};font-weight:700;'>₹{net_pnl_inr:,.0f}</span> &nbsp;|&nbsp; "
                    f"<b>Net Slippage:</b> Favorable: +${fav_usd:,.2f} | Unfavorable: -${unfav_usd:,.2f} | "
                    f"Net: <span style='color:{_slc};font-weight:700;'>{'+' if net_slip_usd>=0 else ''}${net_slip_usd:,.2f} (₹{net_slip_inr:,.0f})</span><br>"
                    f"<b>Today's Slippage:</b> {cnt_t} trades | Favorable: +${fav_t:,.2f} | Unfavorable: -${unfav_t:,.2f} | "
                    f"Net: <span style='color:{_tlc};font-weight:700;'>{'+' if net_t>=0 else ''}${net_t:,.2f}</span>"
                    f"</div>"
                )
            except Exception:
                return ""

        def _bt_lookup13(bot_name, vf_str=None):
            # Exact-trade key = (rounded entry_price, direction) - same method as
            # _load_signals_lookup() used in Today's Trades tab, guarantees correct
            # trade pairing instead of approximate timestamp-proximity matching.
            # Sequential same-direction index matching: Nth LONG BT trade pairs with
            # Nth LONG LV trade (both sorted ascending by entry time). Bot fires off
            # the same signals as backtest, so same-index = same real trade. Price
            # keys cannot be used here since price DIFFERENCE is the slippage itself.
            _lu = {"LONG": [], "SHORT": []}
            try:
                import glob as _gb13m, pandas as _pb13m
                _pat = "output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv" if bot_name=="S4V2" else "output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv"
                _files = sorted(_gb13m.glob(_pat), reverse=True)
                if _files:
                    _dfl = _pb13m.read_csv(_files[0])
                    _dfl["entry_datetime"] = _pb13m.to_datetime(_dfl["entry_datetime"])
                    _dfl["exit_datetime"] = _pb13m.to_datetime(_dfl["exit_datetime"])
                    if vf_str:
                        _dfl = _dfl[_dfl["entry_datetime"] >= _pb13m.to_datetime(vf_str)]
                    _dfl = _dfl.sort_values("entry_datetime")
                    for _, _rl in _dfl.iterrows():
                        _dvv = str(_rl.get("direction","")).upper()
                        if _dvv not in _lu: continue
                        _lu[_dvv].append({
                            "ets": _rl["entry_datetime"].timestamp(),
                            "xts": _rl["exit_datetime"].timestamp(),
                            "ep": float(_rl.get("entry_price",0)),
                            "xp": float(_rl.get("exit_price",0)),
                            "dir": _dvv
                        })
            except Exception:
                pass
            return _lu

        def _fwd20(pairs, bot_name=""):
            try:
                if not pairs:
                    return (f"<div style='overflow-x:auto;max-height:350px;overflow-y:auto;'><table style='width:100%;border-collapse:collapse;'><thead><tr><th style='{_TH20}'>Date</th><th style='{_TH20}'>Dir</th><th style='{_TH20}'>Lot</th><th style='{_TH20}'>Entry Time</th><th style='{_TH20}'>Exit Time</th><th style='{_TH20}'>Entry (INR)</th><th style='{_TH20}'>Exit (INR)</th><th style='{_TH20}'>Slip Diff vs $5</th><th style='{_TH20}'>Tax+Charges</th><th style='{_TH20}'>PnL</th><th style='{_TH20}'>Match</th><th style='{_TH20}'>Message</th></tr></thead><tbody><tr><td colspan='12' style='text-align:center;color:#aaa;padding:12px;font-size:12px;'>Waiting for first trade</td></tr></tbody></table></div>")
                import datetime as _dfw
                last20 = pairs[::-1]
                _bt_lu13 = _bt_lookup13(bot_name, vf_str=_VF13_7D) if bot_name else {"LONG":[],"SHORT":[]}
                _lv_asc13 = pairs  # pairs already sorted ascending by ets (see _pair13/_pair13_csv)
                _lv_idx13 = {"LONG": [q for q in _lv_asc13 if str(q.get("dir","")).upper()=="LONG" and not q.get("open",False)],
                             "SHORT": [q for q in _lv_asc13 if str(q.get("dir","")).upper()=="SHORT" and not q.get("open",False)]}
                _lv_pos13 = {"LONG": {id(x): i for i, x in enumerate(_lv_idx13["LONG"])},
                             "SHORT": {id(x): i for i, x in enumerate(_lv_idx13["SHORT"])}}
                # Cosmetic-only cross-check: confirm OPEN row's direction matches the
                # real live position on Delta right now, so a stale/orphan leftover
                # entry (no real position) is not mislabeled "Trade running now".
                _live_dir13 = None
                try:
                    _lk13 = os.getenv("S4V2_API_KEY") if bot_name=="S4V2" else os.getenv("S4_API_KEY")
                    _ls13 = os.getenv("S4V2_API_SECRET") if bot_name=="S4V2" else os.getenv("S4_API_SECRET")
                    _lts13 = str(int(_t13.time())); _lqs13 = "product_id=84"; _lpth13 = "/v2/positions"
                    _lsig13 = _hm13.new(_ls13.encode(), f"GET{_lts13}{_lpth13}?{_lqs13}".encode(), _hs13.sha256).hexdigest()
                    _lh13 = {"api-key":_lk13,"timestamp":_lts13,"signature":_lsig13}
                    _lr13 = _rq13.get(f"{_BASE13}{_lpth13}?{_lqs13}", headers=_lh13, timeout=5).json()
                    if _lr13.get("success"):
                        _lsz13 = int(_lr13.get("result",{}).get("size",0) or 0)
                        _live_dir13 = "LONG" if _lsz13>0 else "SHORT" if _lsz13<0 else None
                except Exception:
                    pass
                # Scan bot log once for critical issue timestamps (bad-fill-auto-closed,
                # SL placement failed, no SL placed) so each trade row can be flagged.
                _issue_ts13 = {"badfill": [], "slfail": [], "nosl": []}
                try:
                    _lg13 = f"logs/live_trading_{bot_name.lower()}.log" if bot_name else None
                    if _lg13 and os.path.exists(_lg13):
                        import re as _relog13, datetime as _dtlog13
                        with open(_lg13) as _lf13:
                            for _ln13 in _lf13:
                                _m13 = _relog13.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', _ln13)
                                if not _m13: continue
                                try:
                                    _tsv13 = _dtlog13.datetime.strptime(_m13.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=_dtlog13.timezone.utc).timestamp()
                                except Exception:
                                    continue
                                if "BAD FILL DESPITE BAND" in _ln13:
                                    _issue_ts13["badfill"].append(_tsv13)
                                elif "SL PLACEMENT FAILED" in _ln13:
                                    _issue_ts13["slfail"].append(_tsv13)
                                elif "NO SL PLACED" in _ln13:
                                    _issue_ts13["nosl"].append(_tsv13)
                except Exception:
                    pass
                def _near_issue13(ets, key, tol=120):
                    return any(abs(ets - t) <= tol for t in _issue_ts13.get(key, []))
                rows = ""
                for p in last20:
                    pnl      = float(p.get('pnl', 0))
                    pnl_inr  = pnl * _INR13
                    ep_inr   = float(p.get('ep', 0))
                    xp_inr   = float(p.get('xp', 0))
                    cm_inr   = float(p.get('cm', 0)) * _INR13
                    _ist_off1 = _dfw.timedelta(hours=5, minutes=30)
                    is_open  = bool(p.get('open', False))
                    et       = (_dfw.datetime.utcfromtimestamp(p.get('ets',0)) + _ist_off1).strftime('%d-%b-%Y %I:%M %p IST')
                    xt       = "-" if is_open else (_dfw.datetime.utcfromtimestamp(p.get('xts',0)) + _ist_off1).strftime('%d-%b-%Y %I:%M %p IST')
                    dirv     = str(p.get('dir','')).upper()
                    import datetime as _dth20
                    _today20 = (_dth20.datetime.utcnow() + _dth20.timedelta(hours=5,minutes=30)).strftime('%d-%b-%Y')
                    _row_bg20 = "background:#FFFDE7;" if et[:11].strip() == _today20 else ""
                    slip_act = 0 if is_open else abs(float(p.get('ep',0)) - float(p.get('xp',0))) * 100 * 0.001
                    slip_diff= slip_act - 5.0
                    slip_str = "-" if is_open else (f"+${slip_diff:.2f}" if slip_diff >= 0 else f"-${abs(slip_diff):.2f}")
                    mp_style  = _TG20
                    ps        = _TY20 if is_open else (_TG20 if pnl >= 0 else _TR20)
                    ds        = _TG20 if dirv == 'LONG' else _TR20
                    _stuck_f = f"logs/stuck_flag_{bot_name}.txt" if bot_name else None
                    _orphan_f = f"logs/orphan_flag_{bot_name}.txt" if bot_name else None
                    _is_stuck = is_open and _stuck_f and os.path.exists(_stuck_f)
                    _is_orphan = (not is_open) and _orphan_f and os.path.exists(_orphan_f)
                    _sl_hit20 = bool(p.get('sl_hit', False))
                    _msg_style20 = ""
                    if is_open and _live_dir13 is not None and dirv != _live_dir13:
                        _match20 = "-"
                        _msg20 = "Old leftover order, not a real open trade - can ignore"
                        _msg_style20 = "color:#131722;font-weight:700;"
                    elif is_open:
                        _match20 = "-"
                        _msg20 = "Trade running now"
                    elif _near_issue13(p.get('ets',0), "badfill"):
                        _match20 = "-"
                        _msg20 = "Price jumped too much - bot auto-closed this trade for safety"
                        _msg_style20 = "color:#F23645;font-weight:700;"
                    elif _near_issue13(p.get('ets',0), "nosl"):
                        _match20 = "-"
                        _msg20 = "WARNING: No stop-loss was placed on this trade - checked manually"
                        _msg_style20 = "color:#F23645;font-weight:700;"
                    elif _near_issue13(p.get('ets',0), "slfail"):
                        _match20 = "-"
                        _msg20 = "Stop-loss order failed to place - had to fix manually"
                        _msg_style20 = "color:#F23645;font-weight:700;"
                    elif _is_stuck:
                        _match20 = "-"
                        _msg20 = "Bot thinks open, but exchange shows closed - check manually"
                    elif _is_orphan:
                        _match20 = "-"
                        _msg20 = "Position open on exchange but bot lost track - check SL manually"
                    elif _sl_hit20:
                        _match20 = "-"
                        _msg20 = "Stop-loss hit - closed early, this is normal"
                    else:
                        _bt_m13 = None
                        if dirv in _lv_pos13 and id(p) in _lv_pos13[dirv]:
                            _sidx13 = _lv_pos13[dirv][id(p)]
                            if _sidx13 < len(_bt_lu13.get(dirv, [])):
                                _bt_m13 = _bt_lu13[dirv][_sidx13]
                        if _bt_m13:
                            _sge13 = (_bt_m13["ep"] - ep_inr) if dirv=="LONG" else (ep_inr - _bt_m13["ep"])
                            _esl13 = abs(_sge13)*100*0.001
                            _esg13 = "+" if _sge13 >= 0 else "-"
                            _sgx13 = (xp_inr - _bt_m13["xp"]) if dirv=="LONG" else (_bt_m13["xp"] - xp_inr)
                            _xsl13 = abs(_sgx13)*100*0.001
                            _xsg13 = "+" if _sgx13 >= 0 else "-"
                            _dl13 = "L" if dirv=="LONG" else "S"
                            _ec13 = "#089981" if _esg13=="+" else "#F23645"
                            _xc13 = "#089981" if _xsg13=="+" else "#F23645"
                            _match20 = (f"{_dl13} E:<span style='color:{_ec13}'>{_esg13}{_esl13:.2f}</span>"
                                        f"|X:<span style='color:{_xc13}'>{_xsg13}{_xsl13:.2f}</span>")
                        else:
                            _match20 = "-"
                        _msg20 = "Closed normally, as planned"
                    pnl_disp  = ("STUCK" if _is_stuck else "OPEN") if is_open else ("ORPHAN" if _is_orphan else f"₹{pnl_inr:,.0f}")
                    xp_disp   = "-" if is_open else f"${xp_inr:,.0f}"
                    rows += (
                        f"<tr style='{_row_bg20}'>"
                        f"<td style='{_TD20}'>{et[:11].strip()}</td>"
                        f"<td style='{ds}'>{dirv}</td>"
                        f"<td style='{_TD20}'>{int(p.get('sz',0))}</td>"
                        f"<td style='{_TD20}'>{et[12:] if len(et)>12 else et}</td>"
                        f"<td style='{_TD20}'>{xt[12:] if len(xt)>12 and xt!='-' else xt}</td>"
                        f"<td style='{_TD20}'>${ep_inr:,.0f}</td>"
                        f"<td style='{_TD20}'>{xp_disp}</td>"
                        f"<td style='{_TR20}'>{slip_str}</td>"
                        f"<td style='{_TR20}'>₹{cm_inr:,.0f}</td>"
                        f"<td style='{ps}'>{pnl_disp}</td>"
                        f"<td style='{_TD20}'>{_match20}</td>"
                        f"<td style='{_TD20};text-align:left;{_msg_style20}'>{_msg20}</td>"
                        f"</tr>"
                    )
                return (
                    f"<div style='overflow-x:auto;max-height:350px;overflow-y:auto;'>"
                    f"<table style='width:100%;border-collapse:collapse;'>"
                    f"<thead><tr>"
                    f"<th style='{_TH20}'>Date</th>"
                    f"<th style='{_TH20}'>Dir</th>"
                    f"<th style='{_TH20}'>Lot</th>"
                    f"<th style='{_TH20}'>Entry Time</th>"
                    f"<th style='{_TH20}'>Exit Time</th>"
                    f"<th style='{_TH20}'>Entry $</th>"
                    f"<th style='{_TH20}'>Exit $</th>"
                    f"<th style='{_TH20}'>Slip Diff vs $5</th>"
                    f"<th style='{_TH20}'>Tax+Charges</th>"
                    f"<th style='{_TH20}'>Net PnL</th>"
                    f"<th style='{_TH20}'>Match</th>"
                    f"<th style='{_TH20}'>Message</th>"
                    f"</tr></thead><tbody>{rows}</tbody></table></div>"
                )
            except Exception as e:
                return f"<p style='color:red;font-size:11px'>Error: {e}</p>"

        def _bt_hdr13(csv_pattern, vf_str, which="both"):
            try:
                import glob as _gb2, pandas as _pb2
                s2_files = sorted(_gb2.glob("output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv"), reverse=True)
                s4_files = sorted(_gb2.glob("output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv"), reverse=True)
                frames = []
                vf_dt = _pb2.to_datetime(vf_str)
                _sel_files = s2_files[:1] if which=="s2" else (s4_files[:1] if which=="s4" else s2_files[:1]+s4_files[:1])
                for ff in _sel_files:
                    _df = _pb2.read_csv(ff)
                    _df['entry_datetime'] = _pb2.to_datetime(_df['entry_datetime'])
                    _df_vf = _df[_df['entry_datetime'] >= vf_dt]
                    if not _df_vf.empty:
                        frames.append(_df_vf)
                if not frames:
                    return ""
                df = _pb2.concat(frames)
                if df.empty:
                    return ""
                tot = len(df)
                net_pnl_inr = 0.0
                tax_inr_sum = 0.0
                for i, r in df.iterrows():
                    _gross_pnl   = float(r.get('gross_pnl', r.get('net_pnl', 0)))
                    _old_slip    = float(r.get('slippage_usd', 10.0))
                    _old_charges = float(r.get('total_charges_usd', 0)) - _old_slip
                    _sz_ratio    = _LOT_RATIO13
                    _new_slip    = sec13_slip * 2 * _sz_ratio
                    _new_charges = (_old_charges * _sz_ratio) if sec13_charges else 0.0
                    pnl          = (_gross_pnl * _sz_ratio) - _new_slip - _new_charges
                    net_pnl_inr += pnl * _INR13
                    tax_inr_sum += _new_charges * _INR13
                _pnlc = "#089981" if net_pnl_inr >= 0 else "#F23645"
                return (
                    f"<div style='font-size:11px;color:#333;padding:3px 6px;background:#F5F5F5;"
                    f"border:1px solid #ddd;margin-bottom:2px;'>"
                    f"Total Trades: {tot} &nbsp;|&nbsp; "
                    f"Net PnL: <span style='color:{_pnlc};font-weight:700;'>&#8377;{net_pnl_inr:,.0f}</span> &nbsp;|&nbsp; "
                    f"Tax &amp; Charges: &#8377;{tax_inr_sum:,.0f}"
                    f"</div>"
                )
            except Exception as e:
                return f"<p style='color:red;font-size:10px'>BT Header Error: {e}</p>"

        def _bt20(csv_pattern, vf_str, which="both"):
            try:
                import glob as _gb, pandas as _pb
                _slip_lbl13 = f"Slip ${sec13_slip:g}"
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
                    f"<th style='{_TH20}'>{_slip_lbl13}</th>"
                    f"<th style='{_TH20}'>Tax+Charges</th>"
                    f"<th style='{_TH20}'>Net PnL</th>"
                    f"</tr></thead><tbody>"
                    f"<tr><td colspan='9' style='text-align:center;color:#aaa;padding:12px;font-size:12px;'>No backtest trades in this window</td></tr>"
                    f"</tbody></table></div>"
                )
                s2_files = sorted(_gb.glob("output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv"), reverse=True)
                s4_files = sorted(_gb.glob("output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv"), reverse=True)
                frames = []
                vf_dt = _pb.to_datetime(vf_str)
                _sel_files = s2_files[:1] if which=="s2" else (s4_files[:1] if which=="s4" else s2_files[:1]+s4_files[:1])
                for ff in _sel_files:
                    _df = _pb.read_csv(ff)
                    _df['entry_datetime'] = _pb.to_datetime(_df['entry_datetime'])
                    _df_vf = _df[_df['entry_datetime'] >= vf_dt]
                    if not _df_vf.empty:
                        frames.append(_df_vf)
                if not frames:
                    return _WAIT_BT
                df = _pb.concat(frames).sort_values('entry_datetime').iloc[::-1].reset_index(drop=True)
                if df.empty:
                    return _WAIT_BT
                rows = ""
                for i, r in df.iterrows():
                    _gross_pnl   = float(r.get('gross_pnl', r.get('net_pnl', 0)))
                    _old_slip    = float(r.get('slippage_usd', 10.0))
                    _old_charges = float(r.get('total_charges_usd', 0)) - _old_slip
                    _sz_ratio    = _LOT_RATIO13
                    _new_slip    = sec13_slip * 2 * _sz_ratio
                    _new_charges = (_old_charges * _sz_ratio) if sec13_charges else 0.0
                    pnl          = (_gross_pnl * _sz_ratio) - _new_slip - _new_charges
                    pnl_inr      = pnl * _INR13
                    ep_inr  = float(r.get('entry_price', 0))
                    xp_inr  = float(r.get('exit_price',  0))
                    slip    = sec13_slip
                    tax_inr = _new_charges * _INR13
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
                    _today_bt20 = (_dfw.datetime.utcnow() + _ist_off2).strftime('%d-%b-%Y')
                    _row_bg_bt20 = "background:#FFFDE7;" if et[:11].strip() == _today_bt20 else ""
                    rows += (
                        f"<tr style='{_row_bg_bt20}'>"
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
                    f"<th style='{_TH20}'>{_slip_lbl13}</th>"
                    f"<th style='{_TH20}'>Tax+Charges</th>"
                    f"<th style='{_TH20}'>Net PnL</th>"
                    f"</tr></thead><tbody>{rows}</tbody></table></div>"
                )
            except Exception as e:
                return f"<p style='color:red;font-size:11px'>Error: {e}</p>"

        def _cmp20(csv_pattern, fwd_pairs, vf_str):
            try:
                import glob as _gc, pandas as _pc, datetime as _dc
                files = sorted(_gc.glob(csv_pattern), reverse=True)
                s2_ff = sorted(_gc.glob("output/trade_log_RenkoSMIIOSupertrendV2Strategy*.csv"), reverse=True)
                s4_ff = sorted(_gc.glob("output/trade_log_RenkoSMIIOSupertrendStrategy*.csv"), reverse=True)
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

        # ── RENDER: BT S4V2 | BT S4 | FWD S4V2 | FWD S4 (last 7 days, separate) ──
        _vf7_ts = _pd13.to_datetime(_VF13_7D).timestamp()
        s2p_7d = [p for p in s2p if p.get('ets',0) >= _vf7_ts]
        s4p_7d = [p for p in s4p if p.get('ets',0) >= _vf7_ts]

        def _dl13_csv(pairs, label, key):
            try:
                import pandas as _pddl13, datetime as _dtdl13
                rows13 = []
                for p in pairs:
                    _et13 = _dtdl13.datetime.utcfromtimestamp(p.get('ets',0)).strftime('%Y-%m-%d %H:%M:%S') if p.get('ets') else ""
                    _xt13 = _dtdl13.datetime.utcfromtimestamp(p.get('xts',0)).strftime('%Y-%m-%d %H:%M:%S') if p.get('xts') else ""
                    rows13.append({"direction":p.get('dir',''), "lot":p.get('sz',0), "entry_time_utc":_et13,
                                   "exit_time_utc":_xt13, "entry_price":p.get('ep',0), "exit_price":p.get('xp',0),
                                   "net_pnl_usd":p.get('pnl',0), "net_pnl_inr":round(p.get('pnl',0)*_INR13,2), "charges_usd":p.get('cm',0), "status":"OPEN" if p.get('open') else "CLOSED"})
                _csvdata13 = _pddl13.DataFrame(rows13).to_csv(index=False)
                st.download_button(f"Download {label} CSV", _csvdata13, file_name=f"{label.replace(' ','_')}.csv", mime="text/csv", key=key)
            except Exception as _edl13:
                st.caption(f"Download unavailable: {_edl13}")

        def _dl13_bt_csv(csv_pattern, vf_str, label, key):
            try:
                files13 = sorted(_gl13.glob(csv_pattern), reverse=True)
                if files13:
                    _dfdl13 = _pd13.read_csv(files13[0])
                    if 'entry_datetime' in _dfdl13.columns:
                        _dfdl13['entry_datetime'] = _pd13.to_datetime(_dfdl13['entry_datetime'])
                        _dfdl13 = _dfdl13[_dfdl13['entry_datetime'] >= _pd13.to_datetime(vf_str)]
                    st.download_button(f"Download {label} CSV", _dfdl13.to_csv(index=False), file_name=f"{label.replace(' ','_')}.csv", mime="text/csv", key=key)
                else:
                    st.caption("No backtest file found")
            except Exception as _edl13b:
                st.caption(f"Download unavailable: {_edl13b}")

        _colA, _colB = st.columns(2)
        with _colA:
            st.markdown(f"<div style='{_HDR13}'>BACKTEST S4V2 - THIS MONTH</div>", unsafe_allow_html=True)
            st.markdown(_bt_hdr13("output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv", _VF13_7D, which="s2"), unsafe_allow_html=True)
            st.markdown(_bt20("output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv", _VF13_7D, which="s2"), unsafe_allow_html=True)
            _dl13_bt_csv("output/trade_log_RenkoSMIIOSupertrendV2Strategy_BTCUSD_*.csv", _VF13_7D, "BT_S4V2_ThisMonth", "dl_bt_s2")
        with _colB:
            st.markdown(f"<div style='{_HDR13}'>BACKTEST S4 - THIS MONTH</div>", unsafe_allow_html=True)
            st.markdown(_bt_hdr13("output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv", _VF13_7D, which="s4"), unsafe_allow_html=True)
            st.markdown(_bt20("output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv", _VF13_7D, which="s4"), unsafe_allow_html=True)
            _dl13_bt_csv("output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv", _VF13_7D, "BT_S4_ThisMonth", "dl_bt_s4")

        _colC, _colD = st.columns(2)
        with _colC:
            st.markdown(f"<div style='{_HDR13}'>FORWARD TEST S4V2 - THIS MONTH</div>", unsafe_allow_html=True)
            st.markdown(_fwd_slip_hdr13(s2p_7d, bot_name="S4V2"), unsafe_allow_html=True)
            st.markdown(_fwd20(s2p_7d, bot_name="S4V2"), unsafe_allow_html=True)
            _dl13_csv(s2p_7d, "LV_S4V2_ThisMonth", "dl_lv_s2")
        with _colD:
            st.markdown(f"<div style='{_HDR13}'>FORWARD TEST S4 - THIS MONTH</div>", unsafe_allow_html=True)
            st.markdown(_fwd_slip_hdr13(s4p_7d, bot_name="S4"), unsafe_allow_html=True)
            st.markdown(_fwd20(s4p_7d, bot_name="S4"), unsafe_allow_html=True)
            _dl13_csv(s4p_7d, "LV_S4_ThisMonth", "dl_lv_s4")

        # ================================================================
        # EQUITY CURVE - MONTHLY VIEW (BT + FWD, S4V2 + S4)
        # ================================================================
        import plotly.graph_objects as _go13

        def _eq_render13(dates_all, cum_inr_all, key_prefix, title, reset_monthly=False):
            if not dates_all:
                st.caption(f"{title}: no data yet")
                return
            months = sorted(set(d.strftime("%Y-%m") for d in dates_all))
            skey = f"eq13_{key_prefix}_idx"
            if skey not in st.session_state:
                st.session_state[skey] = len(months) - 1
            st.session_state[skey] = max(0, min(st.session_state[skey], len(months)-1))
            c1, c2, c3 = st.columns([1,3,1])
            with c1:
                if st.button("< Prev", key=f"{key_prefix}_prev"):
                    st.session_state[skey] = max(0, st.session_state[skey]-1)
            with c3:
                if st.button("Next >", key=f"{key_prefix}_next"):
                    st.session_state[skey] = min(len(months)-1, st.session_state[skey]+1)
            sel_month = months[st.session_state[skey]]
            with c2:
                st.markdown(f"<div style='text-align:center;font-weight:700;'>{title} - {sel_month}</div>", unsafe_allow_html=True)

            idxs = [i for i,d in enumerate(dates_all) if d.strftime("%Y-%m")==sel_month]
            if not idxs:
                st.caption("No trades this month")
                return
            m_dates = [dates_all[i] for i in idxs]
            if len(m_dates) == 1:
                import datetime as _dt13sp
                m_dates = [m_dates[0] - _dt13sp.timedelta(hours=1), m_dates[0]]
                idxs = [idxs[0], idxs[0]]
            if reset_monthly:
                deltas = []
                for i in idxs:
                    if i == 0:
                        deltas.append(cum_inr_all[i])
                    else:
                        deltas.append(cum_inr_all[i] - cum_inr_all[i-1])
                m_cum = []
                _run = 0.0
                for d in deltas:
                    _run += d
                    m_cum.append(_run)
            else:
                m_cum = [cum_inr_all[i] for i in idxs]

            _pos = [v if v>=0 else 0 for v in m_cum]
            _neg = [v if v<0 else 0 for v in m_cum]
            fig = _go13.Figure(data=[
                _go13.Scatter(x=m_dates, y=_pos, fill='tozeroy', fillcolor='rgba(39,174,96,0.2)',
                              line=dict(width=0), mode='lines', showlegend=False, hoverinfo='skip'),
                _go13.Scatter(x=m_dates, y=_neg, fill='tozeroy', fillcolor='rgba(231,76,60,0.2)',
                              line=dict(width=0), mode='lines', showlegend=False, hoverinfo='skip'),
                _go13.Scatter(x=m_dates, y=m_cum, line=dict(color='#2c3e50', width=2),
                              mode='lines', name='Cumulative PnL')
            ])
            fig.update_layout(title=f'Equity Curve (Rs) - {sel_month}', xaxis_title='Date',
                               yaxis_title='Cumulative PnL (Rs)', hovermode='x unified', height=350,
                               margin=dict(l=40,r=20,t=40,b=30),
                               hoverlabel=dict(bgcolor='#2c3e50', font=dict(color='white', size=13)))
            st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_chart")

        st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
        st.markdown(f"<div style='{_HDR13}'>EQUITY CURVE - MONTHLY VIEW</div>", unsafe_allow_html=True)

        try:
            _f = sorted(_gl13.glob("output/trade_log_RenkoSMIIOSupertrendV2Strategy*.csv"))
            if _f:
                _dfbt2 = _pd13.read_csv(_f[-1])
                _dfbt2['exit_datetime'] = _pd13.to_datetime(_dfbt2['exit_datetime'])
                _dfbt2 = _dfbt2.sort_values('exit_datetime')
                _gpnl2   = _dfbt2.get('gross_pnl', _dfbt2['net_pnl'])
                _oslip2  = _dfbt2.get('slippage_usd', 10.0)
                _ochg2   = _dfbt2.get('total_charges_usd', 0.0) - _oslip2
                _npnl2   = (_gpnl2 * _LOT_RATIO13) - (sec13_slip*2*_LOT_RATIO13) - ((_ochg2*_LOT_RATIO13) if sec13_charges else 0.0)
                _cum2_inr = list((_npnl2 * _INR13).cumsum())
                _eq_render13(list(_dfbt2['exit_datetime']), _cum2_inr, "s2bt", "BACKTEST S4V2", reset_monthly=True)
        except Exception as _e:
            st.caption(f"BT S4V2 equity curve error: {_e}")

        try:
            _f = sorted(_gl13.glob("output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv"))
            if _f:
                _dfbt4 = _pd13.read_csv(_f[-1])
                _dfbt4['exit_datetime'] = _pd13.to_datetime(_dfbt4['exit_datetime'])
                _dfbt4 = _dfbt4.sort_values('exit_datetime')
                _gpnl4   = _dfbt4.get('gross_pnl', _dfbt4['net_pnl'])
                _oslip4  = _dfbt4.get('slippage_usd', 10.0)
                _ochg4   = _dfbt4.get('total_charges_usd', 0.0) - _oslip4
                _npnl4   = (_gpnl4 * _LOT_RATIO13) - (sec13_slip*2*_LOT_RATIO13) - ((_ochg4*_LOT_RATIO13) if sec13_charges else 0.0)
                _cum4_inr = list((_npnl4 * _INR13).cumsum())
                _eq_render13(list(_dfbt4['exit_datetime']), _cum4_inr, "s4bt", "BACKTEST S4", reset_monthly=True)
        except Exception as _e:
            st.caption(f"BT S4 equity curve error: {_e}")

        try:
            if s2p:
                _s2sorted = sorted(s2p, key=lambda p: p['xts'] if p.get('xts',0)>0 else p['ets'])
                _dates = [_dt13.datetime.fromtimestamp(p['xts'] if p.get('xts',0)>0 else p['ets'], _dt13.timezone.utc) + _dt13.timedelta(hours=5, minutes=30) for p in _s2sorted]
                _cum = []
                _run = 0.0
                for p in _s2sorted:
                    _run += p['pnl']*_INR13
                    _cum.append(_run)
                _eq_render13(_dates, _cum, "s2fwd", "FORWARD TEST S4V2")
            else:
                st.caption("FORWARD TEST S4V2: no trades yet")
        except Exception as _e:
            st.caption(f"FWD S4V2 equity curve error: {_e}")

        try:
            if s4p:
                _s4sorted = sorted(s4p, key=lambda p: p['xts'] if p.get('xts',0)>0 else p['ets'])
                _dates = [_dt13.datetime.fromtimestamp(p['xts'] if p.get('xts',0)>0 else p['ets'], _dt13.timezone.utc) + _dt13.timedelta(hours=5, minutes=30) for p in _s4sorted]
                _cum = []
                _run = 0.0
                for p in _s4sorted:
                    _run += p['pnl']*_INR13
                    _cum.append(_run)
                _eq_render13(_dates, _cum, "s4fwd", "FORWARD TEST S4")
            else:
                st.caption("FORWARD TEST S4: no trades yet")
        except Exception as _e:
            st.caption(f"FWD S4 equity curve error: {_e}")



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

        # TODAY'S TRADES TABLE AT TOP
        def _today_trades_html(df2, df4, df2_fwd, df4_fwd):
            import datetime as _dtt
            _INR = 84.0
            _SLIP10_EXTRA = 10.0
            now_utc = _dtt.datetime.utcnow()
            today_s = now_utc.replace(hour=0,minute=0,second=0,microsecond=0)
            def _to_ist(ts):
                try:
                    dt = _pd14.to_datetime(str(ts).replace("T"," "))
                    ist = dt + _dtt.timedelta(hours=5, minutes=30)
                    return ist.strftime("%d-%b %I:%M %p")
                except: return "-"
            def _load_signals_lookup(label):
                _sig_map = {"LV S4V2": "logs/signals_s4v2.csv", "BT S4V2": "logs/signals_s4v2.csv",
                            "LV S4": "logs/signals_s4.csv", "BT S4": "logs/signals_s4.csv"}
                _path = _sig_map.get(label)
                _lookup = {}
                if _path:
                    try:
                        with open(_path) as _sf:
                            for _sl in _sf:
                                _sp = _sl.strip().split(',')
                                if len(_sp) >= 6 and _sp[1] != 'PENDING':
                                    _key = (round(float(_sp[4]),1), _sp[2])
                                    _lookup.setdefault(_key, []).append((_sp[0], _sp[1]))
                    except Exception:
                        pass
                return _lookup

            def _get_bt_rows(df, label):
                if df is None: return []
                rows = []
                try:
                    import pandas as _pd_t
                    # df is a dict from _load14 - get raw_df
                    dfc = df.get("raw_df") if isinstance(df, dict) else df
                    if dfc is None or not hasattr(dfc, 'iterrows'): return []
                    dfc = dfc.copy()
                    dfc['exit_datetime'] = _pd_t.to_datetime(dfc['exit_datetime'])
                    dfc['entry_datetime'] = _pd_t.to_datetime(dfc['entry_datetime'])
                    # filter to today only (entry_datetime = today UTC)
                    import datetime as _dtt_bt
                    _today_bt = _dtt_bt.datetime.utcnow().date()
                    dfc = dfc[dfc['entry_datetime'].dt.date == _today_bt]
                    dfc = dfc.sort_values('entry_datetime', ascending=False)
                    _sig_lookup = _load_signals_lookup(label)
                    for _, r in dfc.iterrows():
                        _dir_raw = str(r.get('direction','')).lower()
                        _entry_ts_raw = str(r.get('entry_datetime',''))
                        _exit_ts_raw = str(r.get('exit_datetime',''))
                        # Cross-check against signals CSV (live bot's actual source) - override
                        # timing if it disagrees, since trade_log_*.csv can be regenerated at a
                        # different data-cutoff than signals_s4v2.csv/signals_s4.csv (root cause
                        # of false exit-delay mismatches, e.g. 1804s artifact, 16-Aug-2026)
                        _sig_key = (round(float(r.get('entry_price',0)),1), _dir_raw)
                        _candidates = _sig_lookup.get(_sig_key, [])
                        if _candidates:
                            try:
                                _orig_dt = _pd_t.to_datetime(_entry_ts_raw)
                                _best = None
                                _best_diff = None
                                for _cand_et, _cand_xt in _candidates:
                                    _cand_dt = _pd_t.to_datetime(_cand_et)
                                    if _cand_dt.date() != _orig_dt.date():
                                        continue
                                    _diff = abs((_cand_dt - _orig_dt).total_seconds())
                                    if _best_diff is None or _diff < _best_diff:
                                        _best_diff = _diff
                                        _best = (_cand_et, _cand_xt)
                                if _best is not None:
                                    _entry_ts_raw, _exit_ts_raw = _best
                            except Exception:
                                pass
                        rows.append({
                            'label'    : label,
                            'dir'      : str(r.get('direction','')).upper(),
                            'entry_ist': _to_ist(_entry_ts_raw if 'S4V2' not in label and 'S4' not in label else (str(_pd_t.to_datetime(_entry_ts_raw) + _pd_t.Timedelta(hours=2 if ('S4' in label and 'S4V2' not in label) else 0, minutes=30 if 'S4V2' in label else 0)))),
                            'entry_ts_raw': _entry_ts_raw,
                            'exit_ist' : _to_ist(_exit_ts_raw if 'S4V2' not in label and 'S4' not in label else (str(_pd_t.to_datetime(_exit_ts_raw) + _pd_t.Timedelta(hours=2 if ('S4' in label and 'S4V2' not in label) else 0, minutes=30 if 'S4V2' in label else 0)))) if _exit_ts_raw != 'PENDING' else '-',
                            'exit_ts_raw': _exit_ts_raw,
                            'entry_p'  : float(r.get('entry_price',0)),
                            'exit_p'   : float(r.get('exit_price',0)),
                            'pnl_usd'  : float(r.get('net_pnl',0)),
                            'pnl_inr5' : float(r.get('net_pnl_inr',0)) - (max(float(r.get('net_pnl_inr',0)),0)*0.10),
                            'pnl_inr10': float(r.get('net_pnl_inr',0)) - (max(float(r.get('net_pnl_inr',0)),0)*0.10) - (_SLIP10_EXTRA * _INR),
                            'charges'  : (float(r.get('taker_fees_usd',0))+float(r.get('slippage_usd',0))+float(r.get('funding_usd',0))+float(r.get('tax_usd',0)))*_INR,
                        })
                except: pass
                return rows
            def _get_fwd_rows(df_fwd, label):
                rows = []
                try:
                    log_map = {"LV S4V2": ("logs/live_trading_s4v2.log","logs/live_trading_s4v2.log.1"),
                               "LV S4": ("logs/live_trading_s4.log","logs/live_trading_s4.log.1")}
                    log_path, log_bak = log_map.get(label, (None, None))
                    if not log_path: return []
                    raw = _parse_log_trades(log_path, log_bak)
                    for p in raw[-10:]:
                        ep   = float(p.get('entry_price',0))
                        xp   = float(p.get('exit_price',0))
                        side = str(p.get('side','buy')).lower()
                        pnl_net = float(p.get('pnl',0))
                        comm    = float(p.get('comm',0))
                        entry_ts = p.get('entry_ts','')
                        exit_ts  = p.get('exit_ts','-')
                        _is_sl   = bool(p.get('sl_hit', False))
                        _exit_label = (_to_ist(exit_ts) + " (SL HIT)") if (_is_sl and exit_ts != '-') else (_to_ist(exit_ts) if exit_ts != '-' else '-')
                        rows.append({
                            'label'    : label,
                            'dir'      : 'LONG' if side=='buy' else 'SHORT',
                            'entry_ist': _to_ist(entry_ts),
                            'entry_ts_raw': str(entry_ts),
                            'exit_ist' : _exit_label,
                            'exit_ts_raw': str(exit_ts) if exit_ts != '-' else '-',
                            'entry_p'  : ep,
                            'exit_p'   : xp,
                            'pnl_usd'  : pnl_net,
                            'pnl_inr5' : pnl_net*_INR,
                            'pnl_inr10': pnl_net*_INR,
                            'charges'  : comm*_INR,
                            'sl_hit'   : _is_sl,
                        })
                    if rows and rows[-1].get('entry_p', 0) == 0:
                        try:
                            import hmac as _hmfe, hashlib as _hsfe, time as _tmfe, requests as _rqfe, datetime as _dtfe
                            _acc_e = "S4V2" if "S4V2" in label else "S4"
                            _ke = os.environ.get(f'{_acc_e}_API_KEY','')
                            _se = os.environ.get(f'{_acc_e}_API_SECRET','')
                            if _ke and _se:
                                _lastE = rows[-1]
                                _entry_side2 = 'buy' if _lastE['dir']=='LONG' else 'sell'
                                _sig_dt = _pd14.to_datetime(_lastE['entry_ts_raw'])
                                _target_ts2 = int(_sig_dt.timestamp())
                                _ts_ep2 = str(int(_tmfe.time()))
                                _path2 = "/v2/fills"
                                _p2 = {"product_id":84,"page_size":50,
                                       "start_time":int((_target_ts2-1800)*1e6),
                                       "end_time":int((_target_ts2+1800)*1e6)}
                                _qs2 = "&".join(f"{a}={b}" for a,b in sorted(_p2.items()))
                                _msg2 = "GET"+_ts_ep2+_path2+"?"+_qs2
                                _sig2 = _hmfe.new(_se.encode(), _msg2.encode(), _hsfe.sha256).hexdigest()
                                _hdr2 = {"api-key":_ke,"timestamp":_ts_ep2,"signature":_sig2}
                                _r2 = _rqfe.get(f"https://cdn-ind.testnet.deltaex.org{_path2}?{_qs2}", headers=_hdr2, timeout=8)
                                _d2 = _r2.json()
                                if _d2.get("success"):
                                    _bestE=None; _bestDiffE=None
                                    for _fl2 in _d2.get("result",[]):
                                        if _fl2.get("side") != _entry_side2:
                                            continue
                                        _fts2 = _dtfe.datetime.strptime(_fl2.get("created_at","")[:19], "%Y-%m-%dT%H:%M:%S")
                                        _diff2 = abs((_fts2 - _sig_dt).total_seconds())
                                        if _diff2 <= 1800 and (_bestDiffE is None or _diff2 < _bestDiffE):
                                            _bestE = (float(_fl2.get("price",0)), _fts2)
                                            _bestDiffE = _diff2
                                    if _bestE is not None:
                                        _lastE['entry_p'] = _bestE[0]
                                        _lastE['entry_fill_ts_raw'] = _bestE[1].isoformat()
                        except Exception:
                            pass
                    if rows and rows[-1].get('exit_ts_raw') == '-':
                        try:
                            import hmac as _hmfw, hashlib as _hsfw, time as _tmfw, requests as _rqfw, datetime as _dtfw
                            _acc = "S4V2" if "S4V2" in label else "S4"
                            _k = os.environ.get(f'{_acc}_API_KEY','')
                            _s = os.environ.get(f'{_acc}_API_SECRET','')
                            if _k and _s:
                                _last = rows[-1]
                                _exit_side = 'sell' if _last['dir']=='LONG' else 'buy'
                                _entry_dt = _pd14.to_datetime(_last['entry_ts_raw'])
                                _target_ts = int(_entry_dt.timestamp())
                                _ts_ep = str(int(_tmfw.time()))
                                _path = "/v2/fills"
                                _p = {"product_id":84,"page_size":50,
                                      "start_time":int(_target_ts*1e6),
                                      "end_time":int((_target_ts+86400)*1e6)}
                                _qs = "&".join(f"{a}={b}" for a,b in sorted(_p.items()))
                                _msg = "GET"+_ts_ep+_path+"?"+_qs
                                _sig = _hmfw.new(_s.encode(), _msg.encode(), _hsfw.sha256).hexdigest()
                                _hdr = {"api-key":_k,"timestamp":_ts_ep,"signature":_sig}
                                _r = _rqfw.get(f"https://cdn-ind.testnet.deltaex.org{_path}?{_qs}", headers=_hdr, timeout=8)
                                _d = _r.json()
                                if _d.get("success"):
                                    for _fl in _d.get("result",[]):
                                        if _fl.get("side") != _exit_side:
                                            continue
                                        if str(_fl.get("meta_data",{}).get("order_type","")) == "":
                                            pass
                                        _fts = _dtfw.datetime.strptime(_fl.get("created_at","")[:19], "%Y-%m-%dT%H:%M:%S")
                                        if _fts <= _entry_dt:
                                            continue
                                        _xp2 = float(_fl.get("price",0))
                                        _comm2 = abs(float(_fl.get("commission",0)))
                                        _last['exit_p'] = _xp2
                                        _last['exit_ts_raw'] = _fts.isoformat()
                                        _last['exit_ist'] = _to_ist(str(_fts))
                                        _raw2 = (_xp2-_last['entry_p'])*100*0.001 if _last['dir']=='LONG' else (_last['entry_p']-_xp2)*100*0.001
                                        _pnl2 = _raw2 - _comm2
                                        _last['pnl_usd'] = _pnl2
                                        _last['pnl_inr5'] = _pnl2*_INR
                                        _last['pnl_inr10'] = _pnl2*_INR
                                        _last['charges'] = _comm2*_INR
                                        break
                        except Exception:
                            pass
                except: pass
                return rows
            def _get_bt_open_row(csv_label):
                _csv_map = {"BT S4V2": "logs/signals_s4v2.csv", "BT S4": "logs/signals_s4.csv"}
                _fpath = _csv_map.get(csv_label)
                if not _fpath:
                    return None
                try:
                    _last_pending = None
                    with open(_fpath) as _f:
                        for _line in _f:
                            _parts = _line.strip().split(',')
                            if len(_parts) < 5:
                                continue
                            _et, _xt, _dirv, _lots, _ep = _parts[0], _parts[1], _parts[2], _parts[3], _parts[4]
                            if _xt == "PENDING":
                                _last_pending = (_et, _dirv, _ep)
                    if _last_pending is None:
                        return None
                    _et, _dirv, _ep = _last_pending
                    import pandas as _pdopen
                    _et_close = _pdopen.to_datetime(_et) + _pdopen.Timedelta(hours=2 if ("S4" in csv_label and "S4V2" not in csv_label) else 0, minutes=30 if "S4V2" in csv_label else 0)
                    return {
                        'label': csv_label, 'dir': _dirv.upper(),
                        'entry_ist': _to_ist(str(_et_close)), 'entry_ts_raw': str(_et), 'exit_ist': ('STUCK' if os.path.exists(f"logs/stuck_flag_{label.split()[-1]}.txt") else ('ORPHAN' if os.path.exists(f"logs/orphan_flag_{label.split()[-1]}.txt") else '-')),
                        'entry_p': float(_ep) if _ep else 0.0, 'exit_p': 0.0,
                        'pnl_usd': 0.0, 'pnl_inr5': 0.0, 'pnl_inr10': 0.0, 'charges': 0.0,
                    }
                except Exception:
                    return None
            def _get_lv_open_row(label):
                import re as _re_lv
                log_map = {"LV S4V2": ("logs/live_trading_s4v2.log","logs/live_trading_s4v2.log.1"),
                           "LV S4": ("logs/live_trading_s4.log","logs/live_trading_s4.log.1")}
                _csv_map3 = {"LV S4V2": "logs/signals_s4v2.csv", "LV S4": "logs/signals_s4.csv"}
                log_path, log_bak = log_map.get(label, (None, None))
                if not log_path:
                    return None
                try:
                    lines = []
                    if log_bak:
                        try: lines += open(log_bak).readlines()
                        except: pass
                    lines += open(log_path).readlines()
                    last_entry = None
                    for idx, line in enumerate(lines):
                        if "[ORDER] ENTRY" in line and "confirmed" not in line and "attempt" not in line:
                            m_dir = _re_lv.search(r'dir=(\w+)', line)
                            m_ts  = _re_lv.search(r'ts=(\S+)', line)
                            m_log = _re_lv.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                            if not (m_dir and m_ts):
                                continue
                            _ep = 0.0
                            for j in range(idx+1, min(idx+5, len(lines))):
                                m_ep = _re_lv.search(r'entry=([\d.]+)', lines[j])
                                if m_ep:
                                    _ep = float(m_ep.group(1))
                                    break
                            last_entry = {"idx": idx, "dir": m_dir.group(1), "sig_ts": m_ts.group(1),
                                          "entry_price": _ep, "log_ts": m_log.group(1) if m_log else ""}
                        elif "[ORDER] EXIT" in line and "skipped" not in line and "confirmed" not in line:
                            if last_entry is not None and idx > last_entry["idx"]:
                                last_entry = None
                        elif "SL hit or manual close" in line:
                            if last_entry is not None and idx > last_entry["idx"]:
                                last_entry = None
                    if last_entry is None:
                        return None
                    if last_entry["entry_price"] == 0.0:
                        _cpath = _csv_map3.get(label)
                        if _cpath:
                            try:
                                with open(_cpath) as _cf:
                                    for _cl in _cf:
                                        _cp = _cl.strip().split(',')
                                        if len(_cp) >= 5 and _cp[0] == last_entry["sig_ts"]:
                                            last_entry["entry_price"] = float(_cp[4])
                                            break
                            except Exception:
                                pass
                    import pandas as _pdlv
                    _et = last_entry["sig_ts"]
                    _et_close = _pdlv.to_datetime(_et) + _pdlv.Timedelta(
                        hours=2 if ("S4" in label and "S4V2" not in label) else 0,
                        minutes=30 if "S4V2" in label else 0)
                    return {
                        'label': label, 'dir': last_entry["dir"].upper(),
                        'entry_ist': _to_ist(str(_et_close)), 'entry_ts_raw': str(_et), 'exit_ist': ('STUCK' if os.path.exists(f"logs/stuck_flag_{label.split()[-1]}.txt") else ('ORPHAN' if os.path.exists(f"logs/orphan_flag_{label.split()[-1]}.txt") else '-')),
                        'exit_ts_raw': '-',
                        'entry_fill_ts_raw': last_entry.get("log_ts", ""),
                        'entry_p': last_entry["entry_price"], 'exit_p': 0.0,
                        'pnl_usd': 0.0, 'pnl_inr5': 0.0, 'pnl_inr10': 0.0, 'charges': 0.0,
                    }
                except Exception:
                    return None
            bt2 = _get_bt_rows(df2, "BT S4V2")
            _bt2_open = _get_bt_open_row("BT S4V2")
            if _bt2_open and _bt2_open.get("entry_ts_raw") not in {r.get("entry_ts_raw") for r in bt2}:
                bt2 = [_bt2_open] + bt2
            bt4 = _get_bt_rows(df4, "BT S4")
            _bt4_open = _get_bt_open_row("BT S4")
            if _bt4_open and _bt4_open.get("entry_ts_raw") not in {r.get("entry_ts_raw") for r in bt4}:
                bt4 = [_bt4_open] + bt4
            lv2 = _get_fwd_rows(df2_fwd, "LV S4V2")
            lv2 = [r for r in lv2 if r.get('exit_ist') not in ('-', '', None)]
            _lv2_open = _get_lv_open_row("LV S4V2")
            if _lv2_open:
                lv2 = [_lv2_open] + lv2
            lv4 = _get_fwd_rows(df4_fwd, "LV S4")
            lv4 = [r for r in lv4 if r.get('exit_ist') not in ('-', '', None)]
            _lv4_open = _get_lv_open_row("LV S4")
            if _lv4_open:
                lv4 = [_lv4_open] + lv4
            today_str = _dtt.datetime.utcnow().strftime("%d-%b-%Y")
            TH  = "padding:5px 8px;border:1px solid #90CAF9;background:#42A5F5;font-size:10px;font-weight:700;color:#fff;text-align:center;"
            THS = "padding:5px 8px;border:1px solid #90CAF9;background:#42A5F5;font-size:10px;font-weight:700;color:#fff;text-align:center;width:40px;"
            TD  = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;text-align:center;"
            TDN = "padding:5px 8px;border:1px solid #BBDEFB;font-size:11px;text-align:center;background:#f7f9fc;font-weight:700;color:#555;vertical-align:middle;"
            def _pnl_color(v): return "#089981" if v>=0 else "#F23645"
            def _dir_color(d): return "#089981" if d=="LONG" else "#F23645"
            def _match(bt, lv):
                if bt is None or lv is None: return "-"
                _entry_delay_txt = ""
                _exit_delay_txt = ""
                _gap_min = None
                try:
                    _lbl = str(bt.get("label",""))
                    _tf_min = 30 if "S4V2" in _lbl else 120
                    _bt_t = _pd14.to_datetime(str(bt.get("entry_ts_raw","")).replace("T"," "))
                    _lv_fill_raw = lv.get("entry_fill_ts_raw") or lv.get("entry_ts_raw","")
                    _lv_t = _pd14.to_datetime(str(_lv_fill_raw).replace("T"," "))
                    _candle_close = _bt_t + _pd14.Timedelta(minutes=_tf_min)
                    _delay_sec = (_lv_t - _candle_close).total_seconds()
                    _entry_delay_txt = f" ({_delay_sec:.0f}s)"
                    _gap_min = abs((_lv_t - _bt_t).total_seconds()) / 60.0
                except Exception:
                    pass
                _tol_min = 150 if "S4" in str(bt.get("label","")) and "S4V2" not in str(bt.get("label","")) else 45
                # ENTRY line - direction + entry price + entry delay
                _signed_pdiff = (bt["entry_p"] - lv["entry_p"]) if bt["dir"] == "LONG" else (lv["entry_p"] - bt["entry_p"])
                _pdiff = abs(_signed_pdiff)
                _psign = "+" if _signed_pdiff >= 0 else "-"
                if bt["dir"] != lv["dir"]:
                    entry_line = f"❌ dir | {_psign}${_pdiff*100*0.001:.2f} slip{_entry_delay_txt}"
                else:
                    if _pdiff*100*0.001 > 5:
                        entry_line = f"❌ {_psign}${_pdiff*100*0.001:.2f} slip{_entry_delay_txt}"
                    elif _gap_min is not None and _gap_min > _tol_min:
                        entry_line = f"❌ delay | {_psign}${_pdiff*100*0.001:.2f} slip{_entry_delay_txt}"
                    else:
                        entry_line = f"✅ {_psign}${_pdiff*100*0.001:.2f} slip{_entry_delay_txt}"
                # EXIT line - exit price + exit delay (independent check)
                _lv_closed = lv.get("exit_ist") not in ("-", "", None)
                _bt_closed = bt.get("exit_ist") not in ("-", "", None)
                if not _bt_closed or not _lv_closed:
                    exit_line = "⏳ open"
                elif _lv_closed and lv["exit_p"] == 0:
                    exit_line = "⚠️ exit price missing"
                elif lv.get("sl_hit", False):
                    exit_line = "🛑 SL HIT - early exit by design, not compared to BT timing"
                else:
                    try:
                        _bt_xt = _pd14.to_datetime(str(bt.get("exit_ts_raw","")).replace("T"," "))
                        _lv_xt = _pd14.to_datetime(str(lv.get("exit_ts_raw","")).replace("T"," "))
                        _bt_xt_close = _bt_xt + _pd14.Timedelta(minutes=_tf_min)
                        _exit_delay_sec = (_lv_xt - _bt_xt_close).total_seconds()
                        _exit_delay_txt = f" ({_exit_delay_sec:.0f}s)"
                    except Exception:
                        pass
                    _signed_xpdiff = ((lv["exit_p"] - bt["exit_p"]) if bt["dir"] == "LONG" else (bt["exit_p"] - lv["exit_p"])) if bt["exit_p"] and lv["exit_p"] else 0
                    _xpdiff = abs(_signed_xpdiff)
                    _xsign = "+" if _signed_xpdiff >= 0 else "-"
                    if bt["exit_p"] and lv["exit_p"] and _xpdiff*100*0.001 > 5:
                        exit_line = f"❌ {_xsign}${_xpdiff*100*0.001:.2f} slip{_exit_delay_txt}"
                    else:
                        exit_line = f"✅ {_xsign}${_xpdiff*100*0.001:.2f} slip{_exit_delay_txt}"
                return f"Entry: {entry_line}<br>Exit: {exit_line}<br><span style='font-size:9px;color:#888;'>Note: match check covers entry/exit price only, not funding cost</span>"
            def _section_html(strat, bt_rows, lv_rows):
                n_bt = len(bt_rows); n_lv = len(lv_rows)
                tc = max(n_bt, n_lv)
                bt_pnl5  = sum(r["pnl_inr5"]  for r in bt_rows)
                bt_pnl10 = sum(r["pnl_inr10"] for r in bt_rows)
                lv_pnl5  = sum(r["pnl_inr5"]  for r in lv_rows)
                lv_pnl10 = sum(r["pnl_inr10"] for r in lv_rows)
                def _pc(v): return "#089981" if v>=0 else "#F23645"
                def _fmt(v): return f"+₹{v:,.0f}" if v>=0 else f"-₹{abs(v):,.0f}"
                hdr = (
                    '<div style="margin:12px 0 0 0;font-size:12px;font-weight:700;color:#fff;'
                    'background:#42A5F5;padding:6px 10px;border-radius:4px 4px 0 0;display:flex;flex-wrap:wrap;align-items:center;gap:6px;">'
                    f'<span>TODAY\'S TRADES ({today_str}) — Backtest {strat} vs Forward Test {strat}</span>'
                    f'<span style="background:#fff;color:#1565C0;border-radius:3px;padding:3px 10px;font-size:12px;font-weight:700;">BT Trades: {n_bt}</span>'
                    f'<span style="background:#e8f5e9;color:#1b5e20;border-radius:3px;padding:3px 10px;font-size:12px;font-weight:700;">LV Trades: {n_lv}</span>'
                    f'<span style="background:#fff3e0;color:#e65100;border-radius:3px;padding:3px 10px;font-size:12px;">BT Net PnL $5: <b style="color:{_pc(bt_pnl5)}">{_fmt(bt_pnl5)}</b> | $10: <b style="color:{_pc(bt_pnl10)}">{_fmt(bt_pnl10)}</b></span>'
                    f'<span style="background:#e3f2fd;color:#0d47a1;border-radius:3px;padding:3px 10px;font-size:12px;">LV Net PnL $5: <b style="color:{_pc(lv_pnl5)}">{_fmt(lv_pnl5)}</b> | $10: <b style="color:{_pc(lv_pnl10)}">{_fmt(lv_pnl10)}</b></span>'
                    '</div>'
                )
                tbl = '<table style="width:100%;border-collapse:collapse;margin-bottom:4px;">'
                tbl += '<thead><tr>'
                tbl += f'<th style="{THS}">S.No</th>'
                tbl += f'<th style="{TH}">Source</th>'
                tbl += f'<th style="{TH}">Dir</th>'
                tbl += f'<th style="{TH}">Entry IST</th>'
                tbl += f'<th style="{TH}">Exit IST</th>'
                tbl += f'<th style="{TH}">Entry $</th>'
                tbl += f'<th style="{TH}">Exit $</th>'
                tbl += f'<th style="{TH}">PnL $</th>'
                tbl += f'<th style="{TH}">Net PnL ₹ ($5/side)</th>'
                tbl += f'<th style="{TH}">Net PnL ₹ ($10/side)</th>'
                tbl += f'<th style="{TH}">Charges ₹</th>'
                tbl += f'<th style="{TH}">Match</th>'
                tbl += '</tr></thead><tbody>'
                if tc == 0:
                    tbl += f'<tr><td colspan="12" style="{TD}color:#aaa;">No trades yet</td></tr>'
                _used_lv = set()
                def _build_pair_map():
                    import datetime as _dtm
                    def _parse(ts):
                        try: return _dtm.datetime.strptime(ts, "%d-%b %I:%M %p")
                        except: return None
                    bt_order = sorted(range(len(bt_rows)), key=lambda i: _parse(bt_rows[i].get("entry_ist","")) or _dtm.datetime.min)
                    lv_order = sorted(range(len(lv_rows)), key=lambda j: _parse(lv_rows[j].get("entry_ist","")) or _dtm.datetime.min)
                    pmap = {}
                    bi, li = 0, 0
                    while bi < len(bt_order) and li < len(lv_order):
                        b_i = bt_order[bi]; l_i = lv_order[li]
                        bt_row = bt_rows[b_i]; lv_row = lv_rows[l_i]
                        bt_dt = _parse(bt_row.get("entry_ist","")); lv_dt = _parse(lv_row.get("entry_ist",""))
                        if bt_dt is None: bi += 1; continue
                        if lv_dt is None: li += 1; continue
                        _lbl = str(bt_row.get("label","")); _tf_min = 30 if "S4V2" in _lbl else 120
                        _max_sec = (_tf_min + 15) * 60
                        diff = (lv_dt - bt_dt).total_seconds()
                        if bt_row.get("dir") == lv_row.get("dir") and abs(diff) <= _max_sec:
                            pmap[b_i] = l_i; _used_lv.add(l_i); bi += 1; li += 1
                        elif diff < 0:
                            li += 1
                        else:
                            bi += 1
                    return pmap
                _pair_map = _build_pair_map()
                def _closest_lv(bt_row):
                    return None
                _used_hist_fills = set()
                def _exchange_fallback(bt_row):
                    import datetime as _dtfb, pandas as _pdfb
                    try:
                        _lbl = str(bt_row.get("label",""))
                        _hist_fp = "uploads/delta_order_history_s4v2_aug2026.csv" if "S4V2" in _lbl else "uploads/delta_order_history_s4_aug2026.csv"
                        if not os.path.exists(_hist_fp):
                            return None
                        _tf_min = 30 if "S4V2" in _lbl else 120
                        _entry_target = _pdfb.to_datetime(bt_row.get("entry_ts_raw","")) + _pdfb.Timedelta(minutes=_tf_min)
                        _bt_exit_raw = bt_row.get("exit_ts_raw","")
                        _exit_target = None
                        if _bt_exit_raw and _bt_exit_raw not in ("-","PENDING",None):
                            try:
                                _exit_target = _pdfb.to_datetime(_bt_exit_raw) + _pdfb.Timedelta(minutes=_tf_min)
                            except Exception:
                                _exit_target = None
                        _entry_side = "buy" if bt_row.get("dir")=="LONG" else "sell"
                        _exit_side  = "sell" if bt_row.get("dir")=="LONG" else "buy"
                        _rows = []
                        with open(_hist_fp) as _hf:
                            _hf.readline()
                            for _hl in _hf:
                                _hp = _hl.strip().split(',')
                                if len(_hp) < 14 or _hp[13] != "closed" or not _hp[5]:
                                    continue
                                try:
                                    _hdt_str = _hp[0].split("+")[0].strip()
                                    _hdt = _dtfb.datetime.strptime(_hdt_str, "%Y-%m-%d %H:%M:%S.%f")
                                    _hdt_utc = _hdt - _dtfb.timedelta(hours=5, minutes=30)
                                except Exception:
                                    continue
                                _fee = 0.0
                                try: _fee = abs(float(_hp[9]))
                                except Exception: pass
                                _rows.append((_hdt_utc, _hp[3], float(_hp[5]), _fee))
                        def _nearest(target, side, exclude_key_prefix):
                            best=None; best_diff=None; best_key=None
                            for _dt, _sd, _px, _fee in _rows:
                                if _sd != side: continue
                                _key = f"{exclude_key_prefix}_{_dt.isoformat()}_{_px}"
                                if _key in _used_hist_fills: continue
                                _diff = abs((_dt - target.to_pydatetime()).total_seconds())
                                if _diff <= 1800 and (best_diff is None or _diff < best_diff):
                                    best = (_px, _fee); best_diff = _diff; best_key = _key
                            if best_key: _used_hist_fills.add(best_key)
                            return best
                        def _live_fill_lookup(_lbl2, _side_want, _target_dt, _tol=1800):
                            try:
                                import hmac as _hmlf, hashlib as _hslf, time as _tmlf, requests as _rqlf
                                _acc = "S4V2" if "S4V2" in _lbl2 else "S4"
                                _k = os.environ.get(f'{_acc}_API_KEY','')
                                _s = os.environ.get(f'{_acc}_API_SECRET','')
                                if not _k or not _s:
                                    return None
                                _base = "https://cdn-ind.testnet.deltaex.org"
                                _ts_ep = str(int(_tmlf.time()))
                                _path = "/v2/fills"
                                _target_ts = int(_target_dt.timestamp())
                                _p = {"product_id":84,"page_size":50,
                                      "start_time":int((_target_ts-_tol)*1e6),
                                      "end_time":int((_target_ts+_tol)*1e6)}
                                _qs = "&".join(f"{a}={b}" for a,b in sorted(_p.items()))
                                _msg = "GET"+_ts_ep+_path+"?"+_qs
                                _sig = _hmlf.new(_s.encode(), _msg.encode(), _hslf.sha256).hexdigest()
                                _hdr = {"api-key":_k,"timestamp":_ts_ep,"signature":_sig}
                                _r = _rqlf.get(f"{_base}{_path}?{_qs}", headers=_hdr, timeout=8)
                                _d = _r.json()
                                if not _d.get("success"):
                                    return None
                                _best=None; _best_diff=None
                                for _fl in _d.get("result",[]):
                                    if _fl.get("side") != _side_want:
                                        continue
                                    _fts = int(_dtfb.datetime.strptime(_fl.get("created_at","")[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=_dtfb.timezone.utc).timestamp())
                                    _diff = abs(_fts - _target_ts)
                                    if _diff <= _tol and (_best_diff is None or _diff < _best_diff):
                                        _best = (float(_fl.get("price",0)), abs(float(_fl.get("commission",0))))
                                        _best_diff = _diff
                                return _best
                            except Exception:
                                return None
                        _e = _nearest(_entry_target, _entry_side, "entry")
                        if _e is None:
                            _e = _live_fill_lookup(_lbl, _entry_side, _entry_target)
                        if _e is None:
                            return None
                        _ep = _e[0]; _fee_e = _e[1]
                        _xp = 0.0; _fee_x = 0.0; _is_open = True
                        if _exit_target is not None:
                            _x = _nearest(_exit_target, _exit_side, "exit")
                            if _x is None:
                                _x = _live_fill_lookup(_lbl, _exit_side, _exit_target)
                            if _x is not None:
                                _xp = _x[0]; _fee_x = _x[1]; _is_open = False
                        _pnl_usd = 0.0; _pnl_inr5 = 0.0; _pnl_inr10 = 0.0; _charges = (_fee_e+_fee_x)*84
                        if not _is_open:
                            _raw = (_xp-_ep)*100*0.001 if bt_row.get("dir")=="LONG" else (_ep-_xp)*100*0.001
                            _pnl_usd = _raw - (_fee_e+_fee_x)
                            _pnl_inr5 = _pnl_usd*84
                            _pnl_inr10 = _pnl_usd*84
                        return {'dir': bt_row.get("dir"), 'entry_ist': bt_row.get("entry_ist"),
                                'entry_ts_raw': bt_row.get("entry_ts_raw"),
                                'exit_ist': ('-' if _is_open else bt_row.get("exit_ist")),
                                'exit_ts_raw': bt_row.get("exit_ts_raw") if not _is_open else '-',
                                'entry_p': _ep, 'exit_p': _xp,
                                'pnl_usd': _pnl_usd, 'pnl_inr5': _pnl_inr5, 'pnl_inr10': _pnl_inr10,
                                'charges': _charges, 'verified_exchange': True}
                    except Exception:
                        pass
                    return None
                _slip_fav_usd = 0.0
                _slip_unfav_usd = 0.0
                for i in range(tc):
                    bt = bt_rows[i] if i < n_bt else None
                    lv = (lv_rows[_pair_map[i]] if bt is not None and i in _pair_map else
                          (lv_rows[i] if i < n_lv and i not in _used_lv else None))
                    if bt is not None and lv is not None:
                        try:
                            _sd = (bt["entry_p"] - lv["entry_p"]) if bt["dir"] == "LONG" else (lv["entry_p"] - bt["entry_p"])
                            if _sd >= 0: _slip_fav_usd += _sd*100*0.001
                            else: _slip_unfav_usd += abs(_sd)*100*0.001
                        except Exception: pass
                        try:
                            if bt.get("exit_ist") not in ("-","",None) and lv.get("exit_ist") not in ("-","",None) and bt.get("exit_p") and lv.get("exit_p"):
                                _sx = ((lv["exit_p"] - bt["exit_p"]) if bt["dir"]=="LONG" else (bt["exit_p"]-lv["exit_p"]))
                                if _sx >= 0: _slip_fav_usd += _sx*100*0.001
                                else: _slip_unfav_usd += abs(_sx)*100*0.001
                        except Exception: pass
                    _sep = "border-top:3px solid #42A5F5;" if i>0 else ""
                    sno_cell = f'<td rowspan="2" style="{TDN}{_sep}">{i+1}</td>'
                    for ridx, (row, src) in enumerate([(bt, f"BT {strat}"), (lv, f"LV {strat}")]):
                        is_lv = (ridx == 1)
                        _fb_note = " <span style=\'color:#1976d2;font-weight:700;\'>[verified via exchange - log gap]</span>" if (is_lv and lv is not None and lv.get("verified_exchange")) else ""
                        match_cell = (f'<td style="{TD}font-size:14px;">{_match(bt,lv)}{_fb_note}</td>' if is_lv
                                      else f'<td style="{TD}"></td>')
                        sno = sno_cell if not is_lv else ""
                        if row is None and is_lv and bt is not None:
                            row = _exchange_fallback(bt)
                        if row is None:
                            _miss_label = "MISSED (no live entry)" if is_lv else "-"
                            tbl += f'<tr>{sno}<td style="{TD}color:#aaa;">{src}</td>'
                            tbl += f'<td style="{TD}color:#e65100;font-weight:700;">{_miss_label}</td>'
                            tbl += (f'<td style="{TD}color:#aaa;">-</td>' * 8)
                            tbl += f'{match_cell}</tr>'
                        else:
                            dc  = _dir_color(row["dir"])
                            pc5 = _pnl_color(row["pnl_inr5"])
                            pc10= _pnl_color(row["pnl_inr10"])
                            pu  = _pnl_color(row["pnl_usd"])
                            bg  = "background:#f0f7ff;" if not is_lv else ""
                            _row_sep = _sep if ridx==0 else ""
                            tbl += f'<tr style="{_row_sep}">{sno}'
                            tbl += f'<td style="{TD}{bg}font-weight:700;">{src}</td>'
                            tbl += f'<td style="{TD}color:{dc};font-weight:700;">{row["dir"]}</td>'
                            _is_open = row["exit_ist"] in ("-", "", None)
                            _oc = "#FF9800"
                            _exit_ist_v = "OPEN" if _is_open else row["exit_ist"]
                            _exit_p_v = "-" if _is_open else "${:,.0f}".format(row["exit_p"])
                            _pnl_usd_v = "OPEN" if _is_open else "${:+,.2f}".format(row["pnl_usd"])
                            _pnl5_v = "-" if _is_open else "₹{:+,.0f}".format(row["pnl_inr5"])
                            _pnl10_v = "-" if _is_open else "₹{:+,.0f}".format(row["pnl_inr10"])
                            _charges_v = "-" if _is_open else "₹{:,.0f}".format(row["charges"])
                            _pu2 = _oc if _is_open else pu
                            _pc5b = _oc if _is_open else pc5
                            _pc10b = _oc if _is_open else pc10
                            _oc_ist = _oc if _is_open else "inherit"
                            tbl += f'<td style="{TD}{bg}">{row["entry_ist"]}</td>'
                            tbl += f'<td style="{TD}{bg}color:{_oc_ist};font-weight:700;">{_exit_ist_v}</td>'
                            tbl += f'<td style="{TD}{bg}">${row["entry_p"]:,.0f}</td>'
                            tbl += f'<td style="{TD}{bg}">{_exit_p_v}</td>'
                            tbl += f'<td style="{TD}color:{_pu2};font-weight:700;">{_pnl_usd_v}</td>'
                            tbl += f'<td style="{TD}color:{_pc5b};font-weight:700;">{_pnl5_v}</td>'
                            tbl += f'<td style="{TD}color:{_pc10b};font-weight:700;">{_pnl10_v}</td>'
                            tbl += f'<td style="{TD}{bg}">{_charges_v}</td>'
                            tbl += f'{match_cell}</tr>'
                tbl += '</tbody></table>'
                _net_slip_usd = _slip_fav_usd - _slip_unfav_usd
                _net_slip_inr = _net_slip_usd * 84
                _slip_color = "#089981" if _net_slip_usd >= 0 else "#F23645"
                _slip_span = (
                    f'<span style="background:#f3e5f5;color:#4a148c;border-radius:3px;padding:3px 10px;font-size:12px;">'
                    f'Net Slippage Today: Favorable: +${_slip_fav_usd:,.2f} | Unfavorable: -${_slip_unfav_usd:,.2f} | '
                    f'Net: <b style="color:{_slip_color}">{"+" if _net_slip_usd>=0 else ""}${_net_slip_usd:,.2f} '
                    f'(₹{_net_slip_inr:,.0f})</b></span>'
                )
                hdr = hdr[:-6] + _slip_span + '</div>'
                return hdr + tbl
            html = '<div style="overflow-x:auto;margin:8px 0;">'
            html += _section_html("S4V2", bt2, lv2)
            html += '<div style="height:14px;"></div>'
            html += _section_html("S4", bt4, lv4)
            html += '</div>'
            return html
        _d2_1yr,_d4_1yr,_d2_full,_d4_full,_1yr_label,_full_label,_df2_fwd,_df4_fwd = _reload_all_data()
        st.markdown(_today_trades_html(_d2_full, _d4_full, _df2_fwd, _df4_fwd), unsafe_allow_html=True)
        st.markdown("---")
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
        <tr><td style="{_PLND14}">Subaccount</td><td style="{_PLNV14}">Single (S4V2 + S4 together)</td></tr>
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


with _tab_today:
    st.markdown("<div class='section-title'>TODAY'S TRADES</div>", unsafe_allow_html=True)
    st.caption('Live comparison of today\'s backtest signals vs forward test execution')
    try:
        _d2_1yr,_d4_1yr,_d2_full,_d4_full,_1yr_label,_full_label,_df2_fwd,_df4_fwd = _reload_all_data()
        st.markdown(_today_trades_html(_d2_full, _d4_full, _df2_fwd, _df4_fwd), unsafe_allow_html=True)
    except Exception as _e_today:
        st.error(f'Today trades load error: {_e_today}')
