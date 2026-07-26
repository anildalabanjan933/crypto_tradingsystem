import streamlit as st
import pandas as pd
import glob
import json
import datetime
import requests
import hmac
import hashlib
import time
import re

st.set_page_config(page_title="Today's Trades", layout="wide", initial_sidebar_state="collapsed")

# Auto refresh every 60s
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=60000, limit=None, key="today_refresh")
except:
    pass

# CSS
st.markdown("""<style>
.stApp { background-color: #FFFFFF; }
.block-container { padding: 0.5rem 1rem !important; max-width: 100% !important; }
section[data-testid="stSidebar"] { display: none; }
header[data-testid="stHeader"] { background: transparent !important; }
</style>""", unsafe_allow_html=True)

_INR = 84.0
_SLIP10_EXTRA = 10.0

def load_config():
    try:
        return json.load(open("dashboard/algo_config.json"))
    except:
        return {}

def _to_ist(ts):
    try:
        dt = datetime.datetime.strptime(str(ts).replace('T',' ')[:19], '%Y-%m-%d %H:%M:%S')
        dt_ist = dt + datetime.timedelta(hours=5, minutes=30)
        return dt_ist.strftime('%d-%b-%Y %I:%M %p IST')
    except:
        return str(ts)

def _load_bt(pattern):
    files = sorted(glob.glob(pattern), reverse=True)
    if not files: return None
    df = pd.read_csv(files[0])
    df['entry_datetime'] = pd.to_datetime(df['entry_datetime'], format='mixed')
    df['exit_datetime'] = pd.to_datetime(df['exit_datetime'], format='mixed')
    return df

def _get_bt_rows(df, label):
    if df is None: return []
    rows = []
    try:
        now_utc = datetime.datetime.utcnow()
        today_s = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        dfc = df[df['exit_datetime'] >= pd.Timestamp(today_s)].copy()
        for _, r in dfc.iterrows():
            pnl_inr = float(r.get('net_pnl_inr', 0))
            win_tax = max(pnl_inr, 0) * 0.10
            pnl_inr5 = pnl_inr - win_tax
            rows.append({
                'label': label,
                'dir': str(r.get('direction', '')).upper(),
                'entry_ist': _to_ist(r.get('entry_datetime', '')),
                'exit_ist': _to_ist(r.get('exit_datetime', '')),
                'entry_p': float(r.get('entry_price', 0)),
                'exit_p': float(r.get('exit_price', 0)),
                'pnl_usd': float(r.get('net_pnl', 0)),
                'pnl_inr5': pnl_inr5,
                'pnl_inr10': pnl_inr5 - (_SLIP10_EXTRA * _INR),
                'charges': (float(r.get('taker_fees_usd', 0)) + float(r.get('slippage_usd', 0)) + float(r.get('funding_usd', 0))) * _INR,
            })
    except:
        pass
    return rows

def _get_fwd_rows(df_fwd, label):
    if df_fwd is None: return []
    rows = []
    try:
        raw = df_fwd.get('raw_pairs', [])
        now_utc = datetime.datetime.utcnow()
        today_s = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d')
        for p in raw:
            if str(p.get('entry_ts', ''))[:10] >= today_s or str(p.get('exit_ts', ''))[:10] >= today_s:
                pnl = float(p.get('pnl', 0))
                win_tax = max(pnl * _INR, 0) * 0.10
                rows.append({
                    'label': label,
                    'dir': 'LONG' if p.get('side') == 'buy' else 'SHORT',
                    'entry_ist': _to_ist(p.get('entry_ts', '')),
                    'exit_ist': _to_ist(p.get('exit_ts', '')),
                    'entry_p': float(p.get('entry_price', 0)),
                    'exit_p': float(p.get('exit_price', 0)),
                    'pnl_usd': pnl,
                    'pnl_inr5': pnl * _INR - win_tax,
                    'pnl_inr10': pnl * _INR - win_tax - (_SLIP10_EXTRA * _INR),
                    'charges': float(p.get('comm', 0)) * _INR,
                })
    except:
        pass
    return rows

def _load14_fwd(product_id, api_key, api_secret, base_url):
    try:
        method = 'GET'
        path = '/v2/orders'
        ts = str(int(time.time()))
        qs = f'?product_id={product_id}&page_size=100&state=closed'
        sig_data = method + ts + path + qs
        sig = hmac.new(api_secret.encode(), sig_data.encode(), hashlib.sha256).hexdigest()
        headers = {'api-key': api_key, 'timestamp': ts, 'signature': sig, 'Content-Type': 'application/json'}
        r = requests.get(base_url + path + qs, headers=headers, timeout=5)
        orders = r.json().get('result', [])
        if not orders: return {'raw_pairs': []}
        pairs = []
        used = set()
        srt = sorted(orders, key=lambda x: x.get('created_at', ''))
        for i, e in enumerate(srt):
            if i in used: continue
            if str(e.get('reduce_only', '')).lower() in ['true', '1']: continue
            es = e.get('side', '')
            if es not in ['buy', 'sell']: continue
            xs = 'sell' if es == 'buy' else 'buy'
            ep = float(e.get('average_fill_price') or e.get('limit_price') or 0)
            ets = e.get('created_at', '')[:19]
            comm_e = float(e.get('paid_commission') or 0)
            for j, x in enumerate(srt):
                if j in used or j == i: continue
                if x.get('side') != xs: continue
                if str(x.get('reduce_only', '')).lower() not in ['true', '1']: continue
                xp = float(x.get('average_fill_price') or x.get('limit_price') or 0)
                xts = x.get('created_at', '')[:19]
                if xts < ets: continue
                sz = int(e.get('size', 0))
                comm = comm_e + float(x.get('paid_commission') or 0)
                pnl = (xp - ep) * sz * 0.001 if es == 'buy' else (ep - xp) * sz * 0.001
                pairs.append({'pnl': pnl - comm, 'entry_ts': ets, 'exit_ts': xts,
                               'entry_price': ep, 'exit_price': xp, 'side': es,
                               'size': sz, 'comm': comm})
                used.add(i); used.add(j); break
        return {'raw_pairs': pairs}
    except:
        return {'raw_pairs': []}

# Header
now_ist = (datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)).strftime('%d-%b-%Y %I:%M:%S %p')
st.markdown(f"""
<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid #e0e0e0;margin-bottom:8px;">
    <span style="font-size:16px;font-weight:700;color:#131722;">TODAY'S TRADES</span>
    <span style="font-size:11px;color:#444;">Auto-refresh 60s &nbsp;|&nbsp; Last updated: {now_ist} IST &nbsp;
    <span style="background:#e8f5e9;color:#2e7d32;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:700;">LIVE</span></span>
</div>""", unsafe_allow_html=True)

# Load data
config = load_config()
system = config.get('system', {})
base_url = system.get('base_url', 'https://cdn-ind.testnet.deltaex.org')

d2 = _load_bt("output/trade_log_RenkoReversal*.csv")
d4 = _load_bt("output/trade_log_RenkoSMIIOSupertrend*.csv")
df2_fwd = _load14_fwd(84, system.get('s2_api_key', ''), system.get('s2_api_secret', ''), base_url)
df4_fwd = _load14_fwd(84, system.get('s4_api_key', ''), system.get('s4_api_secret', ''), base_url)

# Build rows
for strat, df, df_fwd, pid in [('S2', d2, df2_fwd, 84), ('S4', d4, df4_fwd, 84)]:
    bt_rows = _get_bt_rows(df, f'BT {strat}')
    lv_rows = _get_fwd_rows(df_fwd, f'LV {strat}')
    bt_pnl5 = sum(r['pnl_inr5'] for r in bt_rows)
    lv_pnl5 = sum(r['pnl_inr5'] for r in lv_rows)
    bt_pnl10 = sum(r['pnl_inr10'] for r in bt_rows)
    lv_pnl10 = sum(r['pnl_inr10'] for r in lv_rows)

    def fmt(v):
        c = '#089981' if v >= 0 else '#F23645'
        return f"<span style='color:{c};font-weight:700;'>₹{v:,.0f}</span>"

    st.markdown(f"""
    <div style="background:#1565C0;color:white;padding:6px 12px;border-radius:4px;margin:8px 0 4px 0;display:flex;gap:16px;align-items:center;flex-wrap:wrap;">
        <span style="font-weight:700;">TODAY'S TRADES — Backtest {strat} vs Forward Test {strat}</span>
        <span style="background:rgba(255,255,255,0.2);padding:2px 8px;border-radius:3px;">BT Trades: {len(bt_rows)}</span>
        <span style="background:rgba(255,255,255,0.2);padding:2px 8px;border-radius:3px;">LV Trades: {len(lv_rows)}</span>
        <span style="background:rgba(255,255,255,0.15);padding:2px 8px;border-radius:3px;">BT PnL $5: {fmt(bt_pnl5)} | $10: {fmt(bt_pnl10)}</span>
        <span style="background:rgba(255,255,255,0.15);padding:2px 8px;border-radius:3px;">LV PnL $5: {fmt(lv_pnl5)} | $10: {fmt(lv_pnl10)}</span>
    </div>""", unsafe_allow_html=True)

    # Table
    all_rows = []
    max_rows = max(len(bt_rows), len(lv_rows))
    for i in range(max_rows):
        if i < len(bt_rows): all_rows.append((i+1, bt_rows[i]))
        if i < len(lv_rows): all_rows.append((i+1, lv_rows[i]))

    if not all_rows:
        st.info("No trades yet today")
        continue

    rows_html = ""
    prev_sno = None
    for sno, r in all_rows:
        if prev_sno is not None and sno != prev_sno:
            rows_html += f"<tr><td colspan='12' style='padding:0;border:none;background:#1565C0;height:2px;'></td></tr>"
        prev_sno = sno
        is_bt = r['label'].startswith('BT')
        bg = '#ffffff' if is_bt else '#f8f9ff'
        dir_c = '#089981' if r['dir'] == 'LONG' else '#F23645'
        pnl_c = '#089981' if r['pnl_inr5'] >= 0 else '#F23645'
        rows_html += f"""<tr style="background:{bg};">
            <td style="padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;">{sno}</td>
            <td style="padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;">{r['label']}</td>
            <td style="padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;color:{dir_c};font-weight:700;">{r['dir']}</td>
            <td style="padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;">{r['entry_ist']}</td>
            <td style="padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;">{r['exit_ist']}</td>
            <td style="padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;">${r['entry_p']:,.0f}</td>
            <td style="padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;">${r['exit_p']:,.0f}</td>
            <td style="padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;color:{pnl_c};font-weight:700;">₹{r['pnl_inr5']:,.0f}</td>
            <td style="padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;color:{pnl_c};">₹{r['pnl_inr10']:,.0f}</td>
            <td style="padding:4px 6px;border:1px solid #E0E3EB;font-size:11px;">₹{r['charges']:,.0f}</td>
        </tr>"""

    st.markdown(f"""<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;">
        <thead><tr style="background:#f0f3fa;">
            <th style="padding:4px 6px;border:1px solid #C8D0DC;font-size:10px;">S.No</th>
            <th style="padding:4px 6px;border:1px solid #C8D0DC;font-size:10px;">Source</th>
            <th style="padding:4px 6px;border:1px solid #C8D0DC;font-size:10px;">Dir</th>
            <th style="padding:4px 6px;border:1px solid #C8D0DC;font-size:10px;">Entry IST</th>
            <th style="padding:4px 6px;border:1px solid #C8D0DC;font-size:10px;">Exit IST</th>
            <th style="padding:4px 6px;border:1px solid #C8D0DC;font-size:10px;">Entry $</th>
            <th style="padding:4px 6px;border:1px solid #C8D0DC;font-size:10px;">Exit $</th>
            <th style="padding:4px 6px;border:1px solid #C8D0DC;font-size:10px;">Net PnL ₹($5)</th>
            <th style="padding:4px 6px;border:1px solid #C8D0DC;font-size:10px;">Net PnL ₹($10)</th>
            <th style="padding:4px 6px;border:1px solid #C8D0DC;font-size:10px;">Charges ₹</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
    </table></div>""", unsafe_allow_html=True)
