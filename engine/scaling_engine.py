# engine/scaling_engine.py
# Scaling Optimiser Engine
# Reads existing backtest CSV and applies scaling combinations
# Zero re-run of backtest - under 5 seconds
# Never decreases lots on losing period - freeze only

import pandas as pd
import numpy as np
import os
import csv
from datetime import datetime
from itertools import product

USD_TO_INR = 84

# Predefined scaling groups (same structure as PREDEFINED_RANGES in optimizer)
SCALING_GROUPS = {
    "period": {
        "scale_period_months": [1, 2, 3]
    },
    "step": {
        "increment_step": [50, 100, 200]
    },
    "cap": {
        "max_lots_cap": [500, 1000, 2000, 999999]
    }
}

def load_trades(csv_path):
    """Load trades from backtest CSV"""
    trades = []
    with open(csv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            trades.append(row)
    return trades

def get_period_key(entry_datetime, period_months):
    """Get period bucket for a trade"""
    try:
        dt = datetime.strptime(entry_datetime[:10], "%Y-%m-%d")
        if period_months == 1:
            return f"{dt.year}-{dt.month:02d}"
        elif period_months == 2:
            half = (dt.month - 1) // 2
            return f"{dt.year}-H{half+1}"
        elif period_months == 3:
            quarter = (dt.month - 1) // 3
            return f"{dt.year}-Q{quarter+1}"
    except:
        return "unknown"

def apply_scaling(trades, starting_lots, increment_step, 
                  scale_period_months, max_lots_cap, 
                  scale_type="step", reinvest_pct=0.5):
    """
    Apply scaling to trades.
    Step mode: add increment_step lots each profitable period
    Formula mode: reinvest % of profit as additional lots
    Never decrease lots on losing period - freeze only
    """
    if not trades:
        return [], {}

    # Group trades by period
    periods = {}
    for t in trades:
        key = get_period_key(t['entry_datetime'], scale_period_months)
        if key not in periods:
            periods[key] = []
        periods[key].append(t)

    # Calculate period PnL
    period_pnl = {}
    for key, period_trades in periods.items():
        period_pnl[key] = sum(float(t['net_pnl']) for t in period_trades)

    # Apply scaling lot progression
    current_lots = starting_lots
    lot_schedule = {}
    for key in sorted(periods.keys()):
        lot_schedule[key] = current_lots
        pnl = period_pnl[key]
        if pnl > 0:  # Only increase on profitable period
            if scale_type == "step":
                new_lots = current_lots + increment_step
            else:  # formula
                profit_inr = pnl * USD_TO_INR
                lot_increase = int((profit_inr * reinvest_pct) / (current_lots * 100))
                lot_increase = max(0, lot_increase)
                new_lots = current_lots + lot_increase
            current_lots = min(new_lots, max_lots_cap)
        # If losing period - freeze (never decrease)

    # Apply lot schedule to trades
    scaled_trades = []
    for t in trades:
        key = get_period_key(t['entry_datetime'], scale_period_months)
        lots = lot_schedule.get(key, starting_lots)
        scale_factor = lots / starting_lots
        scaled_t = dict(t)
        scaled_t['scaled_lots'] = lots
        scaled_t['scaled_gross_pnl'] = float(t['gross_pnl']) * scale_factor
        scaled_t['scaled_net_pnl'] = float(t['net_pnl']) * scale_factor
        scaled_t['scaled_net_pnl_inr'] = float(t['net_pnl_inr']) * scale_factor
        scaled_t['scaled_charges'] = float(t['total_charges_usd']) * scale_factor
        scaled_trades.append(scaled_t)

    return scaled_trades, lot_schedule

def calculate_metrics(scaled_trades, starting_lots):
    """Calculate all metrics from scaled trades"""
    if not scaled_trades:
        return {}

    total = len(scaled_trades)
    wins = sum(1 for t in scaled_trades if float(t['scaled_net_pnl']) > 0)
    losses = total - wins
    win_rate = wins / total * 100

    net_usd = sum(float(t['scaled_net_pnl']) for t in scaled_trades)
    net_inr = sum(float(t['scaled_net_pnl_inr']) for t in scaled_trades)
    gross = sum(float(t['scaled_gross_pnl']) for t in scaled_trades)
    charges = sum(float(t['scaled_charges']) for t in scaled_trades)

    win_pnls = [float(t['scaled_net_pnl']) for t in scaled_trades if float(t['scaled_net_pnl']) > 0]
    loss_pnls = [float(t['scaled_net_pnl']) for t in scaled_trades if float(t['scaled_net_pnl']) <= 0]
    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0
    pf = sum(win_pnls) / abs(sum(loss_pnls)) if loss_pnls else 0
    rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    # Max drawdown
    cum = 0
    peak = 0
    max_dd = 0
    cum_inr = 0
    peak_inr = 0
    max_dd_inr = 0
    for t in scaled_trades:
        cum += float(t['scaled_net_pnl'])
        cum_inr += float(t['scaled_net_pnl_inr'])
        if cum > peak: peak = cum
        if cum_inr > peak_inr: peak_inr = cum_inr
        if peak - cum > max_dd: max_dd = peak - cum
        if peak_inr - cum_inr > max_dd_inr: max_dd_inr = peak_inr - cum_inr

    # Monthly breakdown
    monthly = {}
    for t in scaled_trades:
        month = t['entry_datetime'][:7]
        if month not in monthly:
            monthly[month] = {'net_usd': 0, 'net_inr': 0, 'trades': 0, 'wins': 0}
        monthly[month]['net_usd'] += float(t['scaled_net_pnl'])
        monthly[month]['net_inr'] += float(t['scaled_net_pnl_inr'])
        monthly[month]['trades'] += 1
        if float(t['scaled_net_pnl']) > 0:
            monthly[month]['wins'] += 1

    # Yearly breakdown
    yearly = {}
    for t in scaled_trades:
        year = t['entry_datetime'][:4]
        if year not in yearly:
            yearly[year] = {'net_usd': 0, 'net_inr': 0, 'trades': 0}
        yearly[year]['net_usd'] += float(t['scaled_net_pnl'])
        yearly[year]['net_inr'] += float(t['scaled_net_pnl_inr'])
        yearly[year]['trades'] += 1

    # Sharpe
    returns = [monthly[m]['net_usd'] for m in monthly]
    avg_r = sum(returns) / len(returns) if returns else 0
    std_r = (sum((r - avg_r) ** 2 for r in returns) / len(returns)) ** 0.5 if returns else 0
    sharpe = (avg_r / std_r) * (12 ** 0.5) if std_r > 0 else 0

    profitable_months = sum(1 for m in monthly.values() if m['net_usd'] > 0)
    losing_months = sum(1 for m in monthly.values() if m['net_usd'] <= 0)

    # Max lots reached
    max_lots = max(int(t['scaled_lots']) for t in scaled_trades)

    return {
        'total_trades': total,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'net_pnl_usd': net_usd,
        'net_pnl_inr': net_inr,
        'gross_pnl_usd': gross,
        'total_charges_usd': charges,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'reward_risk': rr,
        'profit_factor': pf,
        'max_dd_usd': max_dd,
        'max_dd_inr': max_dd_inr,
        'sharpe': sharpe,
        'profitable_months': profitable_months,
        'losing_months': losing_months,
        'max_lots_reached': max_lots,
        'monthly': monthly,
        'yearly': yearly
    }

def run_full_mode(trades, starting_lots, scale_type="step", reinvest_pct=0.5):
    """Run all combinations - Full Mode"""
    results = []
    if scale_type == "step":
        combos = list(product(
            SCALING_GROUPS['period']['scale_period_months'],
            SCALING_GROUPS['step']['increment_step'],
            SCALING_GROUPS['cap']['max_lots_cap']
        ))
        for period, step, cap in combos:
            scaled_trades, lot_schedule = apply_scaling(
                trades, starting_lots, step, period, cap, "step"
            )
            metrics = calculate_metrics(scaled_trades, starting_lots)
            results.append({
                'scale_period': f"{period}M",
                'increment_step': f"+{step}",
                'max_lots_cap': "Unlimited" if cap == 999999 else str(cap),
                'max_lots_reached': metrics.get('max_lots_reached', starting_lots),
                'net_pnl_inr': metrics.get('net_pnl_inr', 0),
                'net_pnl_usd': metrics.get('net_pnl_usd', 0),
                'win_rate': metrics.get('win_rate', 0),
                'profit_factor': metrics.get('profit_factor', 0),
                'max_dd_inr': metrics.get('max_dd_inr', 0),
                'sharpe': metrics.get('sharpe', 0),
                'profitable_months': metrics.get('profitable_months', 0),
                'losing_months': metrics.get('losing_months', 0),
                'metrics': metrics
            })
    else:  # formula
        formula_options = [1.0, 0.75, 0.50, 0.25]
        combos = list(product(
            SCALING_GROUPS['period']['scale_period_months'],
            formula_options,
            SCALING_GROUPS['cap']['max_lots_cap']
        ))
        for period, pct, cap in combos:
            scaled_trades, lot_schedule = apply_scaling(
                trades, starting_lots, 50, period, cap, "formula", pct
            )
            metrics = calculate_metrics(scaled_trades, starting_lots)
            results.append({
                'scale_period': f"{period}M",
                'reinvest_pct': f"{int(pct*100)}%",
                'max_lots_cap': "Unlimited" if cap == 999999 else str(cap),
                'max_lots_reached': metrics.get('max_lots_reached', starting_lots),
                'net_pnl_inr': metrics.get('net_pnl_inr', 0),
                'net_pnl_usd': metrics.get('net_pnl_usd', 0),
                'win_rate': metrics.get('win_rate', 0),
                'profit_factor': metrics.get('profit_factor', 0),
                'max_dd_inr': metrics.get('max_dd_inr', 0),
                'sharpe': metrics.get('sharpe', 0),
                'profitable_months': metrics.get('profitable_months', 0),
                'losing_months': metrics.get('losing_months', 0),
                'metrics': metrics
            })

    # Sort by net_pnl_inr descending
    results.sort(key=lambda x: x['net_pnl_inr'], reverse=True)
    return results

def run_group_mode(trades, starting_lots, group_name, scale_type="step"):
    """Run one group at a time - Group Mode"""
    results = []
    if group_name == "period":
        for period in SCALING_GROUPS['period']['scale_period_months']:
            step = 50
            cap = 999999
            scaled_trades, _ = apply_scaling(trades, starting_lots, step, period, cap, scale_type)
            metrics = calculate_metrics(scaled_trades, starting_lots)
            results.append({
                'group': 'Period',
                'value': f"{period}M",
                'net_pnl_inr': metrics.get('net_pnl_inr', 0),
                'net_pnl_usd': metrics.get('net_pnl_usd', 0),
                'win_rate': metrics.get('win_rate', 0),
                'profit_factor': metrics.get('profit_factor', 0),
                'max_dd_inr': metrics.get('max_dd_inr', 0),
                'sharpe': metrics.get('sharpe', 0),
                'max_lots_reached': metrics.get('max_lots_reached', starting_lots),
                'metrics': metrics
            })
    elif group_name == "step":
        for step in SCALING_GROUPS['step']['increment_step']:
            period = 1
            cap = 999999
            scaled_trades, _ = apply_scaling(trades, starting_lots, step, period, cap, scale_type)
            metrics = calculate_metrics(scaled_trades, starting_lots)
            results.append({
                'group': 'Step',
                'value': f"+{step}",
                'net_pnl_inr': metrics.get('net_pnl_inr', 0),
                'net_pnl_usd': metrics.get('net_pnl_usd', 0),
                'win_rate': metrics.get('win_rate', 0),
                'profit_factor': metrics.get('profit_factor', 0),
                'max_dd_inr': metrics.get('max_dd_inr', 0),
                'sharpe': metrics.get('sharpe', 0),
                'max_lots_reached': metrics.get('max_lots_reached', starting_lots),
                'metrics': metrics
            })
    elif group_name == "cap":
        for cap in SCALING_GROUPS['cap']['max_lots_cap']:
            period = 1
            step = 50
            scaled_trades, _ = apply_scaling(trades, starting_lots, step, period, cap, scale_type)
            metrics = calculate_metrics(scaled_trades, starting_lots)
            results.append({
                'group': 'Cap',
                'value': "Unlimited" if cap == 999999 else str(cap),
                'net_pnl_inr': metrics.get('net_pnl_inr', 0),
                'net_pnl_usd': metrics.get('net_pnl_usd', 0),
                'win_rate': metrics.get('win_rate', 0),
                'profit_factor': metrics.get('profit_factor', 0),
                'max_dd_inr': metrics.get('max_dd_inr', 0),
                'sharpe': metrics.get('sharpe', 0),
                'max_lots_reached': metrics.get('max_lots_reached', starting_lots),
                'metrics': metrics
            })

    results.sort(key=lambda x: x['net_pnl_inr'], reverse=True)
    return results
