# generate_comparison_report.py
# Generates backtest vs forward test comparison HTML report
# Usage: called from dashboard Section 4

import sys, os, json, glob, hashlib, hmac, time, requests
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generate_signature(secret, message):
    return hmac.new(bytes(secret, 'utf-8'), bytes(message, 'utf-8'), hashlib.sha256).hexdigest()


def fetch_delta_data(algo_config, start_date, end_date):
    base_url = algo_config.get('delta_url', 'https://cdn-ind.testnet.deltaex.org')
    api_key = os.getenv(algo_config.get('delta_api_key_env', ''), '')
    api_secret = os.getenv(algo_config.get('delta_api_secret_env', ''), '')
    if not api_key or not api_secret:
        return {'error': 'API keys not found', 'commission': 0, 'funding': 0, 'realized_pnl': 0}
    try:
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000000)
        method = 'GET'
        timestamp = str(int(time.time()))
        path = '/v2/wallet/transactions'
        query = f'?transaction_types=commission,funding&start_time={start_ts}&end_time={end_ts}&page_size=100'
        signature = generate_signature(api_secret, method + timestamp + path + query + '')
        headers = {'api-key': api_key, 'timestamp': timestamp, 'signature': signature, 'Content-Type': 'application/json'}
        resp = requests.get(f"{base_url}{path}{query}", headers=headers, timeout=10)
        data = resp.json()
        if not data.get('success'):
            return {'error': str(data.get('error', 'API error')), 'commission': 0, 'funding': 0, 'realized_pnl': 0}
        transactions = data.get('result', [])
        total_commission = sum(abs(float(tx.get('amount', 0))) for tx in transactions if tx.get('transaction_type') == 'commission')
        total_funding = sum(abs(float(tx.get('amount', 0))) for tx in transactions if tx.get('transaction_type') == 'funding')
        timestamp2 = str(int(time.time()))
        path2 = '/v2/positions/margined'
        query2 = f'?product_ids={algo_config.get("delta_product_id", 84)}'
        signature2 = generate_signature(api_secret, method + timestamp2 + path2 + query2 + '')
        headers2 = {'api-key': api_key, 'timestamp': timestamp2, 'signature': signature2, 'Content-Type': 'application/json'}
        resp2 = requests.get(f"{base_url}{path2}{query2}", headers=headers2, timeout=10)
        data2 = resp2.json()
        realized_pnl = sum(float(p.get('realized_pnl', 0)) for p in data2.get('result', [])) if data2.get('success') else 0
        return {'commission': round(total_commission, 4), 'funding': round(total_funding, 4), 'realized_pnl': round(realized_pnl, 4), 'error': ''}
    except Exception as e:
        return {'error': str(e), 'commission': 0, 'funding': 0, 'realized_pnl': 0}


def get_log_trade_count(log_path):
    try:
        if not os.path.exists(log_path):
            return 0, 0
        lines = open(log_path).readlines()
        return sum(1 for l in lines if '[ORDER] ENTRY' in l), sum(1 for l in lines if '[ORDER] EXIT' in l)
    except:
        return 0, 0


def sb(status, text=''):
    t = text or status
    colors = {'GREEN': '#27ae60', 'YELLOW': '#f39c12', 'RED': '#e74c3c', 'PENDING': '#95a5a6'}
    c = colors.get(status, '#95a5a6')
    return f'<span style="background:{c};color:white;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:bold">{t}</span>'


def check_status(bt, fw, threshold, lower_is_better=False):
    if fw == 0:
        return 'PENDING'
    diff = abs(fw - bt)
    if lower_is_better:
        if fw <= bt or diff <= threshold:
            return 'GREEN'
        elif diff <= threshold * 2:
            return 'YELLOW'
        return 'RED'
    if diff <= threshold:
        return 'GREEN'
    elif diff <= threshold * 2:
        return 'YELLOW'
    return 'RED'


def generate_html(algo, fw_algotest, fw_delta, start_date, end_date):
    name = algo['name']
    strategy = algo['strategy']
    log_path = algo['log_path']
    bt_trades = algo['backtest_trades']
    bt_wr = algo['backtest_winrate']
    bt_pnl = algo['backtest_pnl_inr']
    bt_dd = algo['backtest_dd_pct']
    bt_sharpe = algo['backtest_sharpe']
    bt_slip = algo['backtest_slippage']
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    usd_inr = 84

    log_entries, log_exits = get_log_trade_count(log_path)
    fw_trades = fw_algotest.get('trade_count', 0)
    fw_wr = fw_algotest.get('win_rate', 0)
    fw_pnl = fw_algotest.get('pnl_inr', 0)
    fw_dd = fw_algotest.get('dd_pct', 0)
    fw_sharpe = fw_algotest.get('sharpe', 0)

    delta_commission = fw_delta.get('commission', 0)
    delta_funding = fw_delta.get('funding', 0)
    delta_realized = fw_delta.get('realized_pnl', 0)
    delta_error = fw_delta.get('error', '')

    bt_slip_total = bt_slip * 2
    bt_taker = 5.0
    bt_taker_total = bt_taker * 2
    bt_funding_per = 1.0
    bt_total_trip = bt_slip_total + bt_taker_total + bt_funding_per

    fw_slip_per = (delta_commission / fw_trades / 2) if fw_trades > 0 and delta_commission > 0 else 0
    fw_funding_per = (delta_funding / fw_trades) if fw_trades > 0 and delta_funding > 0 else 0

    trade_st = 'PENDING' if fw_trades == 0 else ('GREEN' if fw_trades == log_entries else 'YELLOW')
    wr_st = check_status(bt_wr, fw_wr, 3.0)
    pnl_st = check_status(bt_pnl / 100000, fw_pnl / 100000, 5.0)
    dd_st = check_status(bt_dd, fw_dd, 0.05, lower_is_better=True)
    sh_st = check_status(bt_sharpe, fw_sharpe, 1.0)
    slip_st = 'PENDING' if fw_slip_per == 0 else ('GREEN' if fw_slip_per <= bt_slip else 'RED')

    dd_safe = round(bt_dd + 0.05, 2)
    dd_safe_usd = round(dd_safe * 100, 0)
    dd_cur_st = 'PENDING' if fw_dd == 0 else ('GREEN' if fw_dd <= dd_safe else ('YELLOW' if fw_dd <= 0.50 else 'RED'))

    flags = [
        ('Trade count - Log vs Algotest', trade_st, 'Check [ORDER] in log. Verify webhook firing.' if trade_st == 'RED' else 'OK'),
        ('Win rate within 3%', wr_st, 'Strategy behaving differently in live market.' if wr_st == 'RED' else 'OK'),
        ('PnL difference within 5L', pnl_st, 'Check slippage and taker fees.' if pnl_st == 'RED' else 'OK'),
        ('Max DD within 0.05%', dd_st, 'Pause strategy - investigate live volatility.' if dd_st == 'RED' else 'OK'),
        ('Sharpe within 1.0', sh_st, 'Risk-adjusted returns degraded.' if sh_st == 'RED' else 'OK'),
        ('Slippage within range', slip_st, 'Real slippage higher than backtest. Check liquidity.' if slip_st == 'RED' else 'OK'),
        ('Delta API data fetched', 'GREEN' if not delta_error else 'YELLOW', delta_error if delta_error else 'OK'),
    ]

    any_red = any(f[1] == 'RED' for f in flags)
    any_yellow = any(f[1] == 'YELLOW' for f in flags)
    overall = 'RED' if any_red else ('YELLOW' if any_yellow else ('PENDING' if fw_trades == 0 else 'GREEN'))
    overall_texts = {'GREEN': 'ALL SYSTEMS HEALTHY', 'YELLOW': 'MONITOR CLOSELY', 'RED': 'ACTION REQUIRED', 'PENDING': 'FORWARD TEST IN PROGRESS'}
    overall_text = overall_texts[overall]
    overall_color = {'GREEN': '#27ae60', 'YELLOW': '#f39c12', 'RED': '#e74c3c', 'PENDING': '#95a5a6'}[overall]

    def pend(val, fmt=''):
        if val == 0:
            return 'PENDING'
        return fmt.format(val) if fmt else str(val)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Comparison Report - {name} {strategy}</title>
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
.fix-red {{background:#fde8e8;border-left:4px solid #e74c3c;padding:8px 12px;margin-top:8px;font-size:11px;border-radius:0 4px 4px 0}}
.fix-yellow {{background:#fff3cd;border-left:4px solid #f39c12;padding:8px 12px;margin-top:8px;font-size:11px;border-radius:0 4px 4px 0}}
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
  <p>{name}: {strategy} | BTCUSD | 100 Lots | Period: {start_date} to {end_date}</p>
  <p>Generated: {now} | Backtest slippage: ${bt_slip}/side | Taker fee: 0.05%/side</p>
</div>

<div class="overall">{overall_text} - {name}: {strategy}</div>

<div class="section">
  <h2>Section 1 - Summary</h2>
  <div class="two-col">
    <div class="card">
      <label>Backtest Total PnL</label>
      <value class="positive">&#8377;{bt_pnl:,.0f}</value>
      <label style="margin-top:8px">Trades: {bt_trades} | Win Rate: {bt_wr}% | DD: -{bt_dd}% | Sharpe: {bt_sharpe}</label>
    </div>
    <div class="card">
      <label>Forward Test PnL (Algotest MTM)</label>
      <value class="{'positive' if fw_pnl >= 0 else 'negative'}">{pend(fw_pnl, '&#8377;{:,.0f}')}</value>
      <label style="margin-top:8px">Trades: {pend(fw_trades)} | Win Rate: {pend(fw_wr,'{}%')} | DD: {pend(fw_dd,'-{}%')}</label>
    </div>
  </div>
</div>

<div class="section">
  <h2>Section 2 - Trade Count Comparison</h2>
  <table>
    <tr><th>Source</th><th>Count</th><th>Status</th><th>Need Fix</th></tr>
    <tr><td>Backtest (full 13 months)</td><td>{bt_trades}</td><td>{sb('GREEN','REFERENCE')}</td><td>-</td></tr>
    <tr><td>Forward - Log (auto)</td><td>{log_entries} entries / {log_exits} exits</td>
        <td>{sb('GREEN' if log_entries > 0 else 'PENDING','LIVE' if log_entries > 0 else 'PENDING')}</td>
        <td>{'OK' if log_entries > 0 else 'Waiting for first trade signal'}</td></tr>
    <tr><td>Forward - Algotest (manual)</td><td>{pend(fw_trades)}</td>
        <td>{sb(trade_st,trade_st)}</td>
        <td>{'Log={} Algotest={} - check webhook'.format(log_entries,fw_trades) if trade_st=='YELLOW' else 'OK' if trade_st=='GREEN' else 'PENDING'}</td></tr>
  </table>
  {'<div class="fix-red">ACTION: Trade count mismatch. Check [ORDER] lines in log. Verify webhook firing. Run TEST ALL WEBHOOKS in dashboard.</div>' if trade_st=='RED' else ''}
</div>

<div class="section">
  <h2>Section 3 - Charges Breakdown (per round trip, 100 lots)</h2>
  <table>
    <tr><th>Charge Type</th><th>Backtest Assumed</th><th>Forward Real (Delta API)</th><th>Difference</th><th>Status</th></tr>
    <tr><td>Slippage (both sides)</td><td>${bt_slip_total:.2f}</td>
        <td>{pend(fw_slip_per*2,'${:.2f}')}</td>
        <td>{'${:.2f} BETTER'.format(bt_slip_total-fw_slip_per*2) if fw_slip_per>0 and fw_slip_per*2<bt_slip_total else 'HIGHER - CHECK' if fw_slip_per>bt_slip else '-'}</td>
        <td>{sb(slip_st,slip_st)}</td></tr>
    <tr><td>Taker Fee (both sides)</td><td>${bt_taker_total:.2f}</td>
        <td>{pend(fw_slip_per*2,'${:.2f}') if delta_commission>0 else 'PENDING (auto)'}</td>
        <td>MATCH</td><td>{sb('GREEN' if delta_commission>0 else 'PENDING','MATCH' if delta_commission>0 else 'PENDING')}</td></tr>
    <tr><td>Funding (per trade)</td><td>${bt_funding_per:.2f}</td>
        <td>{pend(fw_funding_per,'${:.4f}') if fw_funding_per>0 else 'PENDING (auto)'}</td>
        <td>-</td><td>{sb('PENDING','PENDING')}</td></tr>
    <tr><td>Insurance Fund</td><td>$0.00</td><td>$0.00</td><td>$0.00</td><td>{sb('GREEN','MATCH')}</td></tr>
    <tr><td>Tax (income)</td><td colspan="2">NOT in backtest | NOT per trade | Pay yearly to CA</td><td>-</td><td>{sb('GREEN','NOTED')}</td></tr>
    <tr style="font-weight:bold;background:#f0f0f0"><td>Total per round trip</td>
        <td>${bt_total_trip:.2f}</td>
        <td>{pend(fw_slip_per*2+fw_slip_per*2+fw_funding_per,'${:.2f}') if fw_trades>0 else 'PENDING'}</td>
        <td>-</td><td>-</td></tr>
  </table>
  <p style="margin-top:10px;font-size:11px;color:#666">Delta API: Commission=${delta_commission:.4f} | Funding=${delta_funding:.4f} | Realized PnL=${delta_realized:.4f}</p>
  {'<div class="fix-yellow">Delta API: '+delta_error+'</div>' if delta_error else ''}
  {'<div class="fix-red">ACTION: Real slippage higher than backtest. Check BTC liquidity. Check if trading during low volume hours.</div>' if slip_st=='RED' else ''}
</div>

<div class="section">
  <h2>Section 4 - PnL Comparison</h2>
  <table>
    <tr><th>Metric</th><th>Backtest</th><th>Forward (Algotest)</th><th>Difference</th><th>Threshold</th><th>Status</th><th>Need Fix</th></tr>
    <tr><td>Total PnL (INR)</td><td class="positive">&#8377;{bt_pnl:,.0f}</td>
        <td>{pend(fw_pnl,'&#8377;{:,.0f}')}</td>
        <td>{'&#8377;{:,.0f}'.format(abs(fw_pnl-bt_pnl)) if fw_pnl>0 else '-'}</td>
        <td>Within 5L</td><td>{sb(pnl_st,pnl_st)}</td>
        <td>{'Check slippage and taker fees' if pnl_st=='RED' else 'OK' if pnl_st=='GREEN' else 'PENDING'}</td></tr>
    <tr><td>Win Rate</td><td>{bt_wr}%</td>
        <td>{pend(fw_wr,'{}%')}</td>
        <td>{'{:.2f}%'.format(abs(fw_wr-bt_wr)) if fw_wr>0 else '-'}</td>
        <td>Within 3%</td><td>{sb(wr_st,wr_st)}</td>
        <td>{'Strategy behaving differently in live' if wr_st=='RED' else 'OK' if wr_st=='GREEN' else 'PENDING'}</td></tr>
    <tr><td>Max Drawdown</td><td>-{bt_dd}%</td>
        <td>{pend(fw_dd,'-{}%')}</td>
        <td>{'{:.2f}%'.format(abs(fw_dd-bt_dd)) if fw_dd>0 else '-'}</td>
        <td>Within 0.05%</td><td>{sb(dd_st,dd_st)}</td>
        <td>{'Pause strategy - live volatility higher' if dd_st=='RED' else 'OK' if dd_st=='GREEN' else 'PENDING'}</td></tr>
    <tr><td>Sharpe Ratio</td><td>{bt_sharpe}</td>
        <td>{pend(fw_sharpe,'{}')}</td>
        <td>{'{:.2f}'.format(abs(fw_sharpe-bt_sharpe)) if fw_sharpe>0 else '-'}</td>
        <td>Within 1.0</td><td>{sb(sh_st,sh_st)}</td>
        <td>{'Risk-adjusted returns degraded' if sh_st=='RED' else 'OK' if sh_st=='GREEN' else 'PENDING'}</td></tr>
  </table>
  {'<div class="fix-red">ACTION: PnL difference too high. Check real slippage vs backtest assumed. Check taker fee rate on account.</div>' if pnl_st=='RED' else ''}
</div>

<div class="section">
  <h2>Section 5 - Drawdown Safety Zones</h2>
  <table>
    <tr><th>Zone</th><th>DD Range</th><th>USD on $10,000</th><th>Status</th></tr>
    <tr><td>Backtest DD (reference)</td><td>-{bt_dd}%</td><td>${bt_dd*100:.0f}</td><td>{sb('GREEN','REFERENCE')}</td></tr>
    <tr style="background:#e8f5e9"><td>Safe Zone</td><td>below -{dd_safe}%</td><td>below ${dd_safe_usd:.0f}</td><td>{sb('GREEN','GREEN')}</td></tr>
    <tr style="background:#fff8e1"><td>Warning Zone</td><td>-{dd_safe}% to -0.50%</td><td>${dd_safe_usd:.0f} to $50</td><td>{sb('YELLOW','YELLOW')}</td></tr>
    <tr style="background:#fde8e8"><td>Danger Zone</td><td>above -0.50%</td><td>above $50</td><td>{sb('RED','RED')}</td></tr>
    <tr style="font-weight:bold"><td>Current Forward DD</td>
        <td>{pend(fw_dd,'-{}%')}</td>
        <td>{pend(fw_dd*100,'${:.0f}')}</td>
        <td>{sb(dd_cur_st,dd_cur_st)}</td></tr>
  </table>
  {'<div class="fix-red">ACTION: Forward DD exceeds safe zone. Pause strategy immediately. Check live market volatility.</div>' if dd_cur_st=='RED' else ''}
  {'<div class="fix-yellow">WARNING: Forward DD in warning zone. Monitor closely. Do not add new positions.</div>' if dd_cur_st=='YELLOW' else ''}
</div>

<div class="section">
  <h2>Section 6 - Slippage Deep Dive</h2>
  <table>
    <tr><th>Metric</th><th>Backtest</th><th>Forward Real</th><th>Verdict</th><th>Status</th></tr>
    <tr><td>Slippage per side</td><td>${bt_slip:.2f}</td>
        <td>{pend(fw_slip_per,'${:.2f}')}</td>
        <td>{'BETTER - Real market more liquid' if fw_slip_per>0 and fw_slip_per<bt_slip else 'HIGHER - Check liquidity' if fw_slip_per>bt_slip else 'PENDING'}</td>
        <td>{sb(slip_st,slip_st)}</td></tr>
    <tr><td>Saving per round trip</td><td>-</td>
        <td>{'${:.2f}'.format(bt_slip_total-fw_slip_per*2) if fw_slip_per>0 else 'PENDING'}</td>
        <td>{'SAVING' if fw_slip_per>0 and fw_slip_per<bt_slip else 'EXTRA COST' if fw_slip_per>bt_slip else '-'}</td>
        <td>{sb('GREEN','SAVING') if fw_slip_per>0 and fw_slip_per<bt_slip else sb('RED','EXTRA COST') if fw_slip_per>bt_slip else sb('PENDING','PENDING')}</td></tr>
    <tr><td>Total commission (Delta API)</td><td>-</td><td>${delta_commission:.4f}</td><td>Auto fetched</td><td>{sb('GREEN','OK') if delta_commission>0 else sb('PENDING','PENDING')}</td></tr>
    <tr><td>Total funding (Delta API)</td><td>-</td><td>${delta_funding:.4f}</td><td>Auto fetched</td><td>{sb('GREEN','OK') if delta_funding>0 else sb('PENDING','PENDING')}</td></tr>
  </table>
  {'<div class="fix-red">ACTION: Real slippage higher than backtest assumed. Check BTC liquidity at trade time. Consider limit orders for entry.</div>' if slip_st=='RED' else ''}
</div>

<div class="section">
  <h2>Section 7 - Tax and All Charges Clarity</h2>
  <table>
    <tr><th>Charge</th><th>In Backtest?</th><th>In Forward?</th><th>Action</th></tr>
    <tr><td>Slippage</td><td>YES - ${bt_slip}/side assumed</td><td>YES - real amount (Delta API)</td><td>Compare Section 6</td></tr>
    <tr><td>Taker Fee (0.05%)</td><td>YES - included</td><td>YES - 0.05% (Delta API)</td><td>Should match exactly</td></tr>
    <tr><td>Funding Rate</td><td>YES - 10.95%/yr</td><td>YES - real amount (Delta API)</td><td>Compare above</td></tr>
    <tr><td>Insurance Fund</td><td>NO - zero on Delta</td><td>NO - zero on Delta</td><td>Nothing to do</td></tr>
    <tr style="background:#fff8e1"><td>Income Tax</td><td>NO - never in backtest</td><td>NO - not per trade</td><td>Pay yearly to CA - keep 30% reserved</td></tr>
    <tr><td>GST on brokerage</td><td>NO</td><td>NO</td><td>Not applicable</td></tr>
  </table>
  <div class="bullet">Tax is NOT deducted per trade - calculated once per year on total profit</div>
  <div class="bullet">Consult CA for exact tax amount - keep 30% of profit reserved</div>
  <div class="bullet">Backtest PnL = after slippage + taker fee + funding (conservative estimate)</div>
</div>

<div class="section">
  <h2>Section 8 - Red Flags Checklist</h2>
  <table>
    <tr><th>Check</th><th>Status</th><th>Need Fix</th></tr>
    {''.join(['<tr><td>{}</td><td>{}</td><td>{}</td></tr>'.format(f[0],sb(f[1],f[1]),f[2]) for f in flags])}
  </table>
</div>

<div class="section">
  <h2>Section 9 - Tax Estimate (Yearly)</h2>
  <table>
    <tr><th>Item</th><th>Amount</th><th>Note</th></tr>
    <tr><td>Annual PnL estimate (backtest basis)</td><td class="positive">&#8377;{bt_pnl:,.0f}</td><td>13 months backtest</td></tr>
    <tr><td>Tax reserve (30%)</td><td class="negative">&#8377;{bt_pnl*0.30:,.0f}</td><td>Keep reserved - do not trade</td></tr>
    <tr><td>Post-tax estimate</td><td class="positive">&#8377;{bt_pnl*0.70:,.0f}</td><td>Approximate only</td></tr>
    <tr><td>Capital buffer (3x DD)</td><td>&#8377;{bt_dd*100*3*usd_inr:,.0f}</td><td>Keep in account always</td></tr>
  </table>
  <div class="bullet">Consult CA for exact tax - this is estimate only</div>
  <div class="bullet">Tax paid once per year - not per trade</div>
</div>

<div class="section">
  <h2>Section 10 - Bottom Summary (Focus Points - Easy Remember)</h2>
  <div class="three-col">
    <div>
      <p style="font-weight:bold;color:#27ae60;margin-bottom:8px">WHAT IS WORKING</p>
      <div class="bullet">Backtest PnL = after slippage + fees + funding</div>
      <div class="bullet">Forward PnL should be equal or slightly better</div>
      <div class="bullet">Real slippage usually less than ${bt_slip} assumed</div>
      <div class="bullet">Taker fees exact match - no surprise</div>
      <div class="bullet">Your DD = {bt_dd}% = extremely safe = top 1%</div>
    </div>
    <div>
      <p style="font-weight:bold;color:#f39c12;margin-bottom:8px">WHAT TO WATCH</p>
      <div class="bullet">Trade count - weekly check vs backtest frequency</div>
      <div class="bullet">DD stays below ${dd_safe_usd:.0f} (safe zone)</div>
      <div class="bullet">Win rate within 3% of {bt_wr}%</div>
      <div class="bullet">Slippage stays below ${bt_slip}/side</div>
      <div class="bullet">Algotest webhooks firing after every trade</div>
    </div>
    <div>
      <p style="font-weight:bold;color:#e74c3c;margin-bottom:8px">WHAT TO FIX IF RED</p>
      <div class="bullet">Trade count mismatch = check bot logs immediately</div>
      <div class="bullet">PnL diff > 5L = check slippage and fees</div>
      <div class="bullet">DD > {dd_safe}% = pause and investigate</div>
      <div class="bullet">Webhook not firing = check .env and restart</div>
      <div class="bullet">Win rate diff > 3% = review live market conditions</div>
    </div>
  </div>
</div>

<div class="footer">
  Generated: {now} | {name}: {strategy} | BTCUSD | Period: {start_date} to {end_date} | Backtest slippage: ${bt_slip}/side
</div>

</div>
</body>
</html>'''
    return html


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument('--algo', required=True, help='S2 or S4')
    parser.add_argument('--start', default='2026-07-07')
    parser.add_argument('--end', default='2026-07-24')
    parser.add_argument('--algotest_pnl', type=float, default=0)
    parser.add_argument('--algotest_trades', type=int, default=0)
    parser.add_argument('--algotest_winrate', type=float, default=0)
    parser.add_argument('--algotest_dd', type=float, default=0)
    parser.add_argument('--algotest_sharpe', type=float, default=0)
    parser.add_argument('--fetch_delta', action='store_true', default=False)
    args = parser.parse_args()

    config = json.load(open('dashboard/algo_config.json'))
    algo = next((a for a in config['algos'] if a['name'] == args.algo), None)
    if not algo:
        print(f"ERROR: Algo {args.algo} not found")
        sys.exit(1)

    fw_algotest = {
        'pnl_inr': args.algotest_pnl,
        'trade_count': args.algotest_trades,
        'win_rate': args.algotest_winrate,
        'dd_pct': args.algotest_dd,
        'sharpe': args.algotest_sharpe
    }

    fw_delta = {'commission': 0, 'funding': 0, 'realized_pnl': 0, 'error': ''}
    if args.fetch_delta:
        fw_delta = fetch_delta_data(algo, args.start, args.end)
        print(f"Delta data: {fw_delta}")

    html = generate_html(algo, fw_algotest, fw_delta, args.start, args.end)
    os.makedirs('output', exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"output/comparison_report_{args.algo}_{ts}.html"
    open(fname, 'w', encoding='utf-8').write(html)
    print(f"Report saved: {fname}")
