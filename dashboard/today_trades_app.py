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
        from collections import defaultdict
        now_ts = int(time.time())
        from_ts = now_ts - 30*24*3600
        start_us = from_ts * 1000000
        end_us   = now_ts  * 1000000
        all_fills = []
        after_cursor = None
        for page in range(1, 20):
            ts_str = str(int(time.time()))
            params = {'product_id': product_id, 'page_size': 100,
                      'start_time': start_us, 'end_time': end_us}
            if after_cursor:
                params['after'] = after_cursor
            qs = '?' + '&'.join(f'{k}={v}' for k,v in params.items())
            sig_data = 'GET' + ts_str + '/v2/fills' + qs
            sig = hmac.new(api_secret.encode(), sig_data.encode(), hashlib.sha256).hexdigest()
            headers = {'api-key': api_key, 'timestamp': ts_str, 'signature': sig, 'Content-Type': 'application/json'}
            r = requests.get(base_url + '/v2/fills', params=params, headers=headers, timeout=5)
            fills = r.json().get('result', [])
            if not fills: break
            all_fills.extend(fills)
            meta = r.json().get('meta', {})
            after_cursor = meta.get('after')
            if not after_cursor or len(fills) < 100: break
        if not all_fills: return {'raw_pairs': []}
        order_fills = defaultdict(list)
        for f in all_fills:
            order_fills[f.get('order_id','')].append(f)
        orders = []
        for oid, fills in order_fills.items():
            total_size = sum(float(f.get('size',0)) for f in fills)
            wavg = sum(float(f.get('price',0) or 0)*float(f.get('size',0)) for f in fills) / max(total_size,1)
            comm = sum(abs(float(f.get('commission',0))) for f in fills)
            orders.append({'order_id': oid, 'side': fills[0].get('side',''),
                           'size': total_size, 'price': wavg, 'comm': comm,
                           'time': fills[0].get('created_at','')[:19]})
        orders = sorted(orders, key=lambda x: x['time'])
        pairs = []
        used = set()
        for i, e in enumerate(orders):
            if i in used: continue
            es = e['side']
            xs = 'sell' if es == 'buy' else 'buy'
            for j, x in enumerate(orders):
                if j <= i or j in used: continue
                if x['side'] != xs: continue
                sz = e['size']
                ep = e['price']; xp = x['price']
                comm = e['comm'] + x['comm']
                pnl = (xp-ep)*sz*0.001 if es=='buy' else (ep-xp)*sz*0.001
                pairs.append({'pnl': pnl-comm, 'entry_ts': e['time'], 'exit_ts': x['time'],
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
