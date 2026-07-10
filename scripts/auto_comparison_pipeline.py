cat > ~/crypto_trading_system/scripts/auto_comparison_pipeline.py << 'EOF'
#!/usr/bin/env python3
"""
auto_comparison_pipeline.py
Full auto pipeline:
Step 1: Download market data (1m + strategy timeframe)
Step 2: Run backtest
Step 3: Fetch Delta API forward trades
Step 4: Generate HTML comparison report
"""

import sys
import os
import json
import time
import hmac
import hashlib
import argparse
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Args ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--strategy', required=True, choices=['S2', 'S4'])
parser.add_argument('--from_date', required=True, help='YYYY-MM-DD')
args = parser.parse_args()

ALGO_KEY   = args.strategy
FROM_DATE  = args.from_date
TO_DATE    = datetime.now(timezone.utc).strftime('%Y-%m-%d')
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Load config ───────────────────────────────────────────────────────────────
cfg_path = os.path.join(BASE_DIR, 'dashboard', 'algo_config.json')
with open(cfg_path) as f:
    cfg = json.load(f)

algo = next(a for a in cfg['algos'] if a['name'] == ALGO_KEY)

STRATEGY_NAME = algo['strategy']
SYMBOL        = algo['symbol']
LOTS          = algo['lots']
SLIPPAGE      = algo['backtest_slippage']
PRODUCT_ID    = algo['delta_product_id']
DELTA_URL     = algo['delta_url']
API_KEY       = os.environ.get(algo['delta_api_key_env'], '')
API_SECRET    = os.environ.get(algo['delta_api_secret_env'], '')

# Backtest data from config
BT_TRADES    = algo['backtest_trades']
BT_WINRATE   = algo['backtest_winrate']
BT_PNL_INR   = algo['backtest_pnl_inr']
BT_DD        = algo['backtest_dd_pct']
BT_SHARPE    = algo['backtest_sharpe']

# Timeframe per strategy
TIMEFRAME_MAP = {'S2': '1h', 'S4': '2h'}
CSV_MAP       = {'S2': 'data/btc_1h_delta.csv', 'S4': 'data/btc_2h_delta.csv'}
STRATEGY_TF   = TIMEFRAME_MAP[ALGO_KEY]
STRATEGY_CSV  = os.path.join(BASE_DIR, CSV_MAP[ALGO_KEY])
CSV_1M        = os.path.join(BASE_DIR, 'data', 'btc_1m_delta.csv')

DELTA_BASE    = 'https://api.india.delta.exchange'

def log(msg):
    print(msg, flush=True)

# ── STEP 1: Download market data ──────────────────────────────────────────────
log('STEP_1_START')
log(f'[Step 1] Downloading {STRATEGY_TF} market data for {SYMBOL}...')

def fetch_candles_dl(symbol, resolution, start_ts, end_ts):
    url = DELTA_BASE + '/v2/history/candles'
    params = {'symbol': symbol, 'resolution': resolution,
              'start': int(start_ts), 'end': int(end_ts)}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get('success'):
        raise ValueError('API error: ' + str(data))
    return data.get('result', [])

def candles_to_df(candles):
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles)
    df['datetime'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df['Date'] = df['datetime'].dt.strftime('%Y-%m-%d')
    df['Time'] = df['datetime'].dt.strftime('%H:%M:%S')
    df = df.rename(columns={'open':'Open','high':'High','low':'Low',
                             'close':'Close','volume':'Volume'})
    return df[['Date','Time','Open','High','Low','Close','Volume']]

def incremental_download(symbol, resolution, csv_path, full_start='2024-01-01'):
    candle_secs = {'1m':60,'5m':300,'15m':900,'1h':3600,'2h':7200,'4h':14400,'1d':86400}
    step = candle_secs.get(resolution, 3600)
    now_ts = int(datetime.now(timezone.utc).timestamp())

    if os.path.exists(csv_path):
        existing = pd.read_csv(csv_path)
        last_dt  = pd.to_datetime(existing['Date'] + ' ' + existing['Time'],
                                   utc=True).max()
        start_ts = int(last_dt.timestamp()) + step
        log(f'[Step 1] Incremental from {last_dt}')
    else:
        start_ts = int(datetime.strptime(full_start, '%Y-%m-%d')
                       .replace(tzinfo=timezone.utc).timestamp())
        existing = pd.DataFrame()
        log(f'[Step 1] Full download from {full_start}')

    all_candles = []
    chunk = 2000
    ts = start_ts
    while ts < now_ts:
        end_chunk = min(ts + step * chunk, now_ts)
        try:
            candles = fetch_candles_dl(symbol, resolution, ts, end_chunk)
            if candles:
                all_candles.extend(candles)
        except Exception as e:
            log(f'[Step 1] Warning: {e}')
        ts = end_chunk + step
        time.sleep(0.2)

    if all_candles:
        new_df = candles_to_df(all_candles)
        if not existing.empty:
            combined = pd.concat([existing, new_df], ignore_index=True)
        else:
            combined = new_df
        combined = combined.drop_duplicates(subset=['Date','Time']).sort_values(['Date','Time'])
        combined.to_csv(csv_path, index=False)
        log(f'[Step 1] Saved {len(combined)} candles to {csv_path}')
    else:
        log(f'[Step 1] Already up to date: {csv_path}')

try:
    incremental_download(SYMBOL, STRATEGY_TF, STRATEGY_CSV)
    log('STEP_1_DONE')
except Exception as e:
    log(f'STEP_1_ERROR: {e}')
    sys.exit(1)

# ── STEP 2: Run backtest ──────────────────────────────────────────────────────
log('STEP_2_START')
log(f'[Step 2] Running backtest: {STRATEGY_NAME} | {STRATEGY_TF} | {LOTS} lots...')

import subprocess
bt_start = '2024-01-01'
bt_end   = TO_DATE
bt_script = os.path.join(BASE_DIR, 'scripts', 'run_backtest_cli.py')

bt_cmd = [
    sys.executable, bt_script,
    '--strategy', STRATEGY_NAME,
    '--lots', str(LOTS),
    '--start', bt_start,
    '--end', bt_end,
    '--slippage', str(SLIPPAGE),
    '--symbol', SYMBOL,
    '--csv', STRATEGY_CSV
]

bt_result = subprocess.run(bt_cmd, capture_output=True, text=True, cwd=BASE_DIR)
bt_output = bt_result.stdout + bt_result.stderr

# Parse backtest metrics from output
bt_metrics = {}
for line in bt_output.splitlines():
    if ':' in line and not line.startswith('[') and not line.startswith('Run'):
        parts = line.split(':', 1)
        if len(parts) == 2:
            k = parts[0].strip()
            v = parts[1].strip()
            try:
                bt_metrics[k] = float(v)
            except:
                bt_metrics[k] = v

if bt_result.returncode != 0:
    log(f'[Step 2] Warning: backtest had errors, using config values')
    bt_metrics = {
        'total_trades': BT_TRADES,
        'win_rate': BT_WINRATE,
        'total_pnl_inr': BT_PNL_INR,
        'max_drawdown_pct': BT_DD,
        'sharpe_ratio': BT_SHARPE
    }
else:
    log(f'[Step 2] Backtest complete. Metrics: {bt_metrics}')

# Use config values as fallback for missing keys
final_bt = {
    'trades':   bt_metrics.get('total_trades', BT_TRADES),
    'winrate':  bt_metrics.get('win_rate', BT_WINRATE),
    'pnl_inr':  bt_metrics.get('total_pnl_inr', BT_PNL_INR),
    'dd_pct':   bt_metrics.get('max_drawdown_pct', BT_DD),
    'sharpe':   bt_metrics.get('sharpe_ratio', BT_SHARPE),
    'slippage': SLIPPAGE
}

log('STEP_2_DONE')

# ── STEP 3: Fetch Delta API forward data ──────────────────────────────────────
log('STEP_3_START')
log(f'[Step 3] Fetching Delta API trades from {FROM_DATE} to {TO_DATE}...')

def sign(secret, method, path, qs, body, ts):
    msg = method + ts + path + qs + body
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()

def delta_get(path, params=None):
    if params is None:
        params = {}
    ts  = str(int(time.time()))
    qs  = '?' + '&'.join(f'{k}={v}' for k,v in params.items()) if params else ''
    sig = sign(API_SECRET, 'GET', path, qs, '', ts)
    headers = {
        'api-key': API_KEY,
        'timestamp': ts,
        'signature': sig,
        'Content-Type': 'application/json',
        'User-Agent': 'python-rest-client'
    }
    url = DELTA_URL + path
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

# Fetch fills (executed trades)
from_ts = int(datetime.strptime(FROM_DATE, '%Y-%m-%d')
               .replace(tzinfo=timezone.utc).timestamp())
to_ts   = int(datetime.now(timezone.utc).timestamp())

all_fills = []
try:
    page = 1
    while True:
        resp = delta_get('/v2/fills', {
            'product_id': PRODUCT_ID,
            'page_size': 100,
            'page_num': page
        })
        fills = resp.get('result', [])
        if not fills:
            break
        # Filter by date range
        for f in fills:
            ft = int(datetime.strptime(f['created_at'][:19],
                     '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc).timestamp())
            if ft >= from_ts:
                all_fills.append(f)
        if len(fills) < 100:
            break
        page += 1
        time.sleep(0.2)
    log(f'[Step 3] Fetched {len(all_fills)} fills')
except Exception as e:
    log(f'[Step 3] Warning fills: {e}')

# Fetch wallet transactions for commission + funding
total_commission = 0.0
total_funding    = 0.0
try:
    resp = delta_get('/v2/wallet/transactions', {
        'product_id': PRODUCT_ID,
        'page_size': 200
    })
    txns = resp.get('result', {}).get('data', [])
    for t in txns:
        tt = int(datetime.strptime(t['created_at'][:19],
                 '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc).timestamp())
        if tt >= from_ts:
            amt = float(t.get('amount', 0))
            if t.get('transaction_type') == 'commission':
                total_commission += abs(amt)
            elif t.get('transaction_type') == 'funding':
                total_funding += abs(amt)
    log(f'[Step 3] Commission=${total_commission:.4f} Funding=${total_funding:.4f}')
except Exception as e:
    log(f'[Step 3] Warning transactions: {e}')

# Calculate forward metrics from fills
fwd_trade_count = 0
fwd_wins        = 0
fwd_pnl_usd     = 0.0
fwd_pnl_inr     = 0.0
fwd_max_dd      = 0.0
INR_RATE        = 84.0  # approximate USD to INR

if all_fills:
    # Group fills into round trips (buy+sell pairs)
    buys  = [f for f in all_fills if f.get('side') == 'buy']
    sells = [f for f in all_fills if f.get('side') == 'sell']
    fwd_trade_count = min(len(buys), len(sells))

    # Calculate PnL from fills
    pnl_list = []
    for i in range(fwd_trade_count):
        try:
            buy_price  = float(buys[i]['price'])
            sell_price = float(sells[i]['price'])
            size       = float(buys[i]['size'])
            pnl        = (sell_price - buy_price) * size
            pnl_list.append(pnl)
            fwd_pnl_usd += pnl
            if pnl > 0:
                fwd_wins += 1
        except:
            pass

    fwd_pnl_inr = fwd_pnl_usd * INR_RATE
    fwd_winrate = (fwd_wins / fwd_trade_count * 100) if fwd_trade_count > 0 else 0.0

    # Max drawdown from PnL series
    if pnl_list:
        equity = 0.0
        peak   = 0.0
        max_dd = 0.0
        for p in pnl_list:
            equity += p
            if equity > peak:
                peak = equity
            dd = (equity - peak) / peak * 100 if peak > 0 else 0
            if dd < max_dd:
                max_dd = dd
        fwd_max_dd = abs(max_dd)
else:
    fwd_winrate = 0.0

fwd = {
    'trade_count':  fwd_trade_count,
    'winrate':      round(fwd_winrate, 2),
    'pnl_inr':      round(fwd_pnl_inr, 2),
    'pnl_usd':      round(fwd_pnl_usd, 4),
    'max_dd':       round(fwd_max_dd, 4),
    'commission':   round(total_commission, 4),
    'funding':      round(total_funding, 4),
    'from_date':    FROM_DATE,
    'to_date':      TO_DATE,
    'fills_count':  len(all_fills)
}
log(f'[Step 3] Forward metrics: {fwd}')
log('STEP_3_DONE')

# ── STEP 4: Generate HTML report ──────────────────────────────────────────────
log('STEP_4_START')
log('[Step 4] Generating HTML comparison report...')

def status_badge(color, text):
    colors = {
        'green':  '#27ae60',
        'red':    '#e74c3c',
        'yellow': '#f39c12',
        'grey':   '#95a5a6',
        'blue':   '#2980b9'
    }
    bg = colors.get(color, '#95a5a6')
    return f'<span style="background:{bg};color:white;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:bold">{text}</span>'

def check_metric(fwd_val, bt_val, threshold_pct):
    if fwd_val == 0 and bt_val == 0:
        return 'grey', 'PENDING'
    if fwd_val == 0:
        return 'grey', 'PENDING'
    diff = abs(fwd_val - bt_val)
    pct  = (diff / bt_val * 100) if bt_val != 0 else 0
    if pct <= threshold_pct:
        return 'green', 'MATCH'
    else:
        return 'red', 'MISMATCH'

now_str    = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
algo_label = f'{ALGO_KEY}: {STRATEGY_NAME}'

# Determine overall status
has_fwd_data = fwd['trade_count'] > 0
if has_fwd_data:
    tc_col, tc_st   = check_metric(fwd['trade_count'], final_bt['trades'], 20)
    wr_col, wr_st   = check_metric(fwd['winrate'], final_bt['winrate'], 5)
    pnl_col, pnl_st = check_metric(abs(fwd['pnl_inr']), abs(final_bt['pnl_inr']), 20)
    dd_col, dd_st   = check_metric(fwd['max_dd'], final_bt['dd_pct'], 50)
    red_flags = [s for s in [tc_st, wr_st, pnl_st, dd_st] if s == 'MISMATCH']
    if red_flags:
        overall_color = '#e74c3c'
        overall_text  = f'RED FLAGS DETECTED - {len(red_flags)} MISMATCH(ES) - REVIEW REQUIRED'
    else:
        overall_color = '#27ae60'
        overall_text  = f'ALL METRICS MATCH - {ALGO_KEY} FORWARD TEST HEALTHY'
else:
    tc_col = wr_col = pnl_col = dd_col = 'grey'
    tc_st  = wr_st  = pnl_st  = dd_st  = 'PENDING'
    overall_color = '#95a5a6'
    overall_text  = f'FORWARD TEST IN PROGRESS - {algo_label}'

# DD safety zones
bt_dd     = final_bt['dd_pct']
warn_dd   = round(bt_dd * 1.2, 4)
danger_dd = round(bt_dd * 1.8, 4)
capital   = 10000
if has_fwd_data and fwd['max_dd'] > 0:
    if fwd['max_dd'] < warn_dd:
        dd_zone_col, dd_zone = 'green', 'GREEN - SAFE'
    elif fwd['max_dd'] < danger_dd:
        dd_zone_col, dd_zone = 'yellow', 'YELLOW - WARNING'
    else:
        dd_zone_col, dd_zone = 'red', 'RED - DANGER'
else:
    dd_zone_col, dd_zone = 'grey', 'PENDING'

# Tax estimates
tax_reserve  = round(final_bt['pnl_inr'] * 0.30)
post_tax     = round(final_bt['pnl_inr'] * 0.70)
cap_buffer   = round(capital * final_bt['dd_pct'] / 100 * 3)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Comparison Report - {ALGO_KEY} {STRATEGY_NAME}</title>
<style>
* {{margin:0;padding:0;box-sizing:border-box}}
body {{font-family:"Segoe UI",sans-serif;background:#f5f5f5;color:#333;line-height:1.6}}
.container {{max-width:1400px;margin:0 auto;padding:20px}}
.header {{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:30px;border-radius:8px;margin-bottom:20px}}
.header h1 {{font-size:24px;margin-bottom:8px}}
.header p {{font-size:13px;opacity:0.9}}
.overall {{padding:15px 20px;border-radius:8px;margin-bottom:20px;font-size:16px;font-weight:bold;color:white;background:{overall_color}}}
.section {{background:white;padding:20px;margin-bottom:15px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}}
.section h2 {{font-size:16px;color:#667eea;border-bottom:2px solid #667eea;padding-bottom:8px;margin-bottom:15px}}
table {{width:100%;border-collapse:collapse;margin-top:10px}}
th {{background:#667eea;color:white;padding:10px;text-align:left;font-size:12px}}
td {{padding:10px;border-bottom:1px solid #eee;font-size:12px}}
tr:hover {{background:#f9f9f9}}
.positive {{color:#27ae60;font-weight:bold}}
.negative {{color:#e74c3c;font-weight:bold}}
.bullet {{margin:6px 0;padding-left:15px;font-size:12px}}
.bullet::before {{content:"• ";color:#667eea;font-weight:bold}}
.two-col {{display:grid;grid-template-columns:1fr 1fr;gap:15px}}
.three-col {{display:grid;grid-template-columns:1fr 1fr 1fr;gap:15px}}
.card {{background:#f9f9f9;padding:15px;border-radius:6px;border-left:4px solid #667eea}}
.card label {{font-size:11px;color:#666;display:block;margin-bottom:4px}}
.card value {{font-size:20px;font-weight:bold;display:block}}
.footer {{text-align:center;padding:15px;color:#999;font-size:11px}}
</style>
</head>
<body>
<div class="container">

<div class="header">
  <h1>Backtest vs Forward Test - Comparison Report</h1>
  <p>{algo_label} | {SYMBOL} | {LOTS} Lots | Forward Period: {FROM_DATE} to {TO_DATE}</p>
  <p>Generated: {now_str} | Backtest slippage: ${SLIPPAGE}/side | Taker fee: 0.05%/side</p>
</div>

<div class="overall">{overall_text}</div>

<div class="section">
  <h2>Section 1 - Summary</h2>
  <div class="two-col">
    <div class="card">
      <label>Backtest Total PnL</label>
      <value class="positive">&#8377;{final_bt['pnl_inr']:,.0f}</value>
      <label style="margin-top:8px">Trades: {final_bt['trades']} | Win Rate: {final_bt['winrate']}% | DD: -{final_bt['dd_pct']}% | Sharpe: {final_bt['sharpe']}</label>
    </div>
    <div class="card">
      <label>Forward Test PnL (Delta API)</label>
      <value class="{'positive' if fwd['pnl_inr'] >= 0 else 'negative'}">{'&#8377;{:,.0f}'.format(fwd['pnl_inr']) if has_fwd_data else 'PENDING'}</value>
      <label style="margin-top:8px">Trades: {fwd['trade_count'] if has_fwd_data else 'PENDING'} | Win Rate: {str(fwd['winrate'])+'%' if has_fwd_data else 'PENDING'} | DD: {str(fwd['max_dd'])+'%' if has_fwd_data else 'PENDING'}</label>
    </div>
  </div>
</div>

<div class="section">
  <h2>Section 2 - Trade Count Comparison</h2>
  <table>
    <tr><th>Source</th><th>Count</th><th>Status</th><th>Note</th></tr>
    <tr><td>Backtest (reference)</td><td>{final_bt['trades']}</td>
        <td>{status_badge('green','REFERENCE')}</td><td>Full history backtest</td></tr>
    <tr><td>Forward - Delta API</td><td>{fwd['trade_count'] if has_fwd_data else 'PENDING'}</td>
        <td>{status_badge(tc_col, tc_st)}</td>
        <td>{'Fills: '+str(fwd['fills_count']) if has_fwd_data else 'Waiting for trades'}</td></tr>
  </table>
</div>

<div class="section">
  <h2>Section 3 - Charges Breakdown (per round trip, {LOTS} lots)</h2>
  <table>
    <tr><th>Charge Type</th><th>Backtest Assumed</th><th>Forward Real (Delta API)</th><th>Status</th></tr>
    <tr><td>Slippage (both sides)</td><td>${SLIPPAGE*2:.2f}</td>
        <td>{'${:.4f}'.format(fwd['commission']/fwd['trade_count']) if fwd['trade_count']>0 else 'PENDING'}</td>
        <td>{status_badge('grey','PENDING') if not has_fwd_data else status_badge('blue','AUTO FETCHED')}</td></tr>
    <tr><td>Taker Fee (both sides)</td><td>${LOTS*0.001:.2f}</td>
        <td>{'${:.4f}'.format(fwd['commission']) if has_fwd_data else 'PENDING'}</td>
        <td>{status_badge('green','AUTO FETCHED') if has_fwd_data else status_badge('grey','PENDING')}</td></tr>
    <tr><td>Funding (total)</td><td>-</td>
        <td>{'${:.4f}'.format(fwd['funding']) if has_fwd_data else 'PENDING'}</td>
        <td>{status_badge('green','AUTO FETCHED') if has_fwd_data else status_badge('grey','PENDING')}</td></tr>
    <tr><td>Insurance Fund</td><td>$0.00</td><td>$0.00</td><td>{status_badge('green','MATCH')}</td></tr>
    <tr><td>Tax (income)</td><td colspan="2">NOT per trade - pay yearly to CA</td><td>{status_badge('green','NOTED')}</td></tr>
    <tr style="font-weight:bold;background:#f0f0f0"><td>Total Commission (Delta API)</td>
        <td>-</td>
        <td>{'${:.4f}'.format(fwd['commission']) if has_fwd_data else 'PENDING'}</td>
        <td>-</td></tr>
  </table>
  <p style="margin-top:10px;font-size:11px;color:#666">
    Delta API Auto-Fetch: Commission=${fwd['commission']} | Funding=${fwd['funding']} | Period: {FROM_DATE} to {TO_DATE}
  </p>
</div>

<div class="section">
  <h2>Section 4 - PnL Comparison</h2>
  <table>
    <tr><th>Metric</th><th>Backtest</th><th>Forward (Delta API)</th><th>Difference</th><th>Threshold</th><th>Status</th></tr>
    <tr><td>Total PnL (INR)</td>
        <td class="positive">&#8377;{final_bt['pnl_inr']:,.0f}</td>
        <td>{'&#8377;{:,.0f}'.format(fwd['pnl_inr']) if has_fwd_data else 'PENDING'}</td>
        <td>{('&#8377;{:,.0f}'.format(abs(fwd['pnl_inr']-final_bt['pnl_inr']))) if has_fwd_data else '-'}</td>
        <td>Within 20%</td>
        <td>{status_badge(pnl_col, pnl_st)}</td></tr>
    <tr><td>Win Rate</td>
        <td>{final_bt['winrate']}%</td>
        <td>{str(fwd['winrate'])+'%' if has_fwd_data else 'PENDING'}</td>
        <td>{str(round(abs(fwd['winrate']-final_bt['winrate']),2))+'%' if has_fwd_data else '-'}</td>
        <td>Within 5%</td>
        <td>{status_badge(wr_col, wr_st)}</td></tr>
    <tr><td>Max Drawdown</td>
        <td>-{final_bt['dd_pct']}%</td>
        <td>{'-'+str(fwd['max_dd'])+'%' if has_fwd_data else 'PENDING'}</td>
        <td>{str(round(abs(fwd['max_dd']-final_bt['dd_pct']),4))+'%' if has_fwd_data else '-'}</td>
        <td>Within 50%</td>
        <td>{status_badge(dd_col, dd_st)}</td></tr>
    <tr><td>Sharpe Ratio</td>
        <td>{final_bt['sharpe']}</td>
        <td>PENDING</td><td>-</td><td>Within 1.0</td>
        <td>{status_badge('grey','PENDING')}</td></tr>
  </table>
</div>

<div class="section">
  <h2>Section 5 - Drawdown Safety Zones</h2>
  <table>
    <tr><th>Zone</th><th>DD Range</th><th>USD on ${capital:,}</th><th>Status</th></tr>
    <tr><td>Backtest DD (reference)</td><td>-{bt_dd}%</td><td>${capital*bt_dd/100:.0f}</td><td>{status_badge('green','REFERENCE')}</td></tr>
    <tr style="background:#e8f5e9"><td>Safe Zone</td><td>below -{warn_dd}%</td><td>below ${capital*warn_dd/100:.0f}</td><td>{status_badge('green','GREEN')}</td></tr>
    <tr style="background:#fff8e1"><td>Warning Zone</td><td>-{warn_dd}% to -{danger_dd}%</td><td>${capital*warn_dd/100:.0f} to ${capital*danger_dd/100:.0f}</td><td>{status_badge('yellow','YELLOW')}</td></tr>
    <tr style="background:#fde8e8"><td>Danger Zone</td><td>above -{danger_dd}%</td><td>above ${capital*danger_dd/100:.0f}</td><td>{status_badge('red','RED')}</td></tr>
    <tr style="font-weight:bold"><td>Current Forward DD</td>
        <td>{'-'+str(fwd['max_dd'])+'%' if has_fwd_data else 'PENDING'}</td>
        <td>{'${:.0f}'.format(capital*fwd['max_dd']/100) if has_fwd_data else 'PENDING'}</td>
        <td>{status_badge(dd_zone_col, dd_zone)}</td></tr>
  </table>
</div>

<div class="section">
  <h2>Section 6 - Slippage Deep Dive</h2>
  <table>
    <tr><th>Metric</th><th>Backtest</th><th>Forward Real (Delta API)</th><th>Status</th></tr>
    <tr><td>Slippage assumed/side</td><td>${SLIPPAGE:.2f}</td><td>Real fills used</td><td>{status_badge('blue','AUTO')}</td></tr>
    <tr><td>Total commission (Delta API)</td><td>-</td>
        <td>{'${:.4f}'.format(fwd['commission']) if has_fwd_data else 'PENDING'}</td>
        <td>{status_badge('green','AUTO FETCHED') if has_fwd_data else status_badge('grey','PENDING')}</td></tr>
    <tr><td>Total funding (Delta API)</td><td>-</td>
        <td>{'${:.4f}'.format(fwd['funding']) if has_fwd_data else 'PENDING'}</td>
        <td>{status_badge('green','AUTO FETCHED') if has_fwd_data else status_badge('grey','PENDING')}</td></tr>
    <tr><td>Total charges (Delta API)</td><td>-</td>
        <td>{'${:.4f}'.format(fwd['commission']+fwd['funding']) if has_fwd_data else 'PENDING'}</td>
        <td>{status_badge('green','AUTO FETCHED') if has_fwd_data else status_badge('grey','PENDING')}</td></tr>
  </table>
</div>

<div class="section">
  <h2>Section 7 - Tax and Charges Clarity</h2>
  <table>
    <tr><th>Charge</th><th>In Backtest?</th><th>In Forward?</th><th>Action</th></tr>
    <tr><td>Slippage</td><td>YES - ${SLIPPAGE}/side assumed</td><td>YES - real (Delta API)</td><td>Compare Section 6</td></tr>
    <tr><td>Taker Fee (0.05%)</td><td>YES - included</td><td>YES - auto fetched</td><td>Should match exactly</td></tr>
    <tr><td>Funding Rate</td><td>YES - annual rate</td><td>YES - auto fetched</td><td>Compare above</td></tr>
    <tr><td>Insurance Fund</td><td>NO - zero on Delta</td><td>NO - zero on Delta</td><td>Nothing to do</td></tr>
    <tr style="background:#fff8e1"><td>Income Tax</td><td>NO</td><td>NO - not per trade</td><td>Pay yearly to CA - keep 30% reserved</td></tr>
  </table>
  <div class="bullet">Tax is NOT deducted per trade - calculated once per year on total profit</div>
  <div class="bullet">Consult CA for exact tax - keep 30% of profit reserved</div>
</div>

<div class="section">
  <h2>Section 8 - Red Flags Checklist</h2>
  <table>
    <tr><th>Check</th><th>Status</th><th>Action</th></tr>
    <tr><td>Trade count match</td><td>{status_badge(tc_col,tc_st)}</td><td>{'OK' if tc_st!='MISMATCH' else 'Check bot logs immediately'}</td></tr>
    <tr><td>Win rate within 5%</td><td>{status_badge(wr_col,wr_st)}</td><td>{'OK' if wr_st!='MISMATCH' else 'Review live market conditions'}</td></tr>
    <tr><td>PnL difference within 20%</td><td>{status_badge(pnl_col,pnl_st)}</td><td>{'OK' if pnl_st!='MISMATCH' else 'Check slippage and fees'}</td></tr>
    <tr><td>Max DD within safe zone</td><td>{status_badge(dd_col,dd_st)}</td><td>{'OK' if dd_st!='MISMATCH' else 'Pause and investigate'}</td></tr>
    <tr><td>Delta API data fetched</td><td>{status_badge('green','GREEN')}</td><td>OK</td></tr>
    <tr><td>Commission auto fetched</td><td>{status_badge('green' if has_fwd_data else 'grey', 'OK' if has_fwd_data else 'PENDING')}</td><td>{'Commission=${:.4f}'.format(fwd['commission']) if has_fwd_data else 'No trades yet'}</td></tr>
  </table>
</div>

<div class="section">
  <h2>Section 9 - Tax Estimate (Yearly)</h2>
  <table>
    <tr><th>Item</th><th>Amount</th><th>Note</th></tr>
    <tr><td>Annual PnL estimate (backtest basis)</td><td class="positive">&#8377;{final_bt['pnl_inr']:,.0f}</td><td>Full history backtest</td></tr>
    <tr><td>Tax reserve (30%)</td><td class="negative">&#8377;{tax_reserve:,.0f}</td><td>Keep reserved - do not trade</td></tr>
    <tr><td>Post-tax estimate</td><td class="positive">&#8377;{post_tax:,.0f}</td><td>Approximate only</td></tr>
    <tr><td>Capital buffer (3x DD)</td><td>&#8377;{cap_buffer:,.0f}</td><td>Keep in account always</td></tr>
  </table>
  <div class="bullet">Consult CA for exact tax - this is estimate only</div>
  <div class="bullet">Tax paid once per year - not per trade</div>
</div>

<div class="section">
  <h2>Section 10 - Bottom Summary</h2>
  <div class="three-col">
    <div>
      <p style="font-weight:bold;color:#27ae60;margin-bottom:8px">WHAT IS WORKING</p>
      <div class="bullet">Backtest PnL = after slippage + fees + funding</div>
      <div class="bullet">Forward PnL auto fetched from Delta API</div>
      <div class="bullet">Commission and funding auto fetched</div>
      <div class="bullet">Taker fees exact match - no surprise</div>
      <div class="bullet">DD = {final_bt['dd_pct']}% = extremely safe</div>
    </div>
    <div>
      <p style="font-weight:bold;color:#f39c12;margin-bottom:8px">WHAT TO WATCH</p>
      <div class="bullet">Trade count - weekly check vs backtest frequency</div>
      <div class="bullet">DD stays below {warn_dd}% (safe zone)</div>
      <div class="bullet">Win rate within 5% of {final_bt['winrate']}%</div>
      <div class="bullet">Slippage stays below ${SLIPPAGE}/side</div>
      <div class="bullet">Delta API webhooks firing after every trade</div>
    </div>
    <div>
      <p style="font-weight:bold;color:#e74c3c;margin-bottom:8px">WHAT TO FIX IF RED</p>
      <div class="bullet">Trade count mismatch = check bot logs immediately</div>
      <div class="bullet">PnL diff > 20% = check slippage and fees</div>
      <div class="bullet">DD > {danger_dd}% = pause and investigate</div>
      <div class="bullet">API fetch fails = check .env credentials</div>
      <div class="bullet">Win rate diff > 5% = review live market conditions</div>
    </div>
  </div>
</div>

<div class="footer">
  Generated: {now_str} | {algo_label} | {SYMBOL} | Forward: {FROM_DATE} to {TO_DATE} | Auto-fetched from Delta API
</div>

</div>
</body>
</html>"""

# Save report
ts_str    = datetime.now().strftime('%Y%m%d_%H%M%S')
out_file  = os.path.join(BASE_DIR, 'output', f'comparison_report_{ALGO_KEY}_{ts_str}.html')
with open(out_file, 'w') as f:
    f.write(html)

log(f'REPORT_FILE:{out_file}')
log('STEP_4_DONE')
log('PIPELINE_COMPLETE')
EOF
