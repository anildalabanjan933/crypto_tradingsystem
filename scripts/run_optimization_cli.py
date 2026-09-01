# run_optimization_cli.py
# CLI wrapper for run_optimization.py - used by dashboard

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.optimizer import Optimizer
from engine.optimization_analyzer import OptimizationAnalyzer
from strategy_registry import strategy_registry
from datetime import datetime
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--strategy', required=True)
parser.add_argument('--group', required=True)
parser.add_argument('--lots', type=int, default=100)
parser.add_argument('--start', required=True)
parser.add_argument('--end', required=True)
parser.add_argument('--slippage', type=float, default=5.0)
parser.add_argument('--symbol', default='BTCUSD')
parser.add_argument('--csv', default='data/btc_1m_delta.csv')
parser.add_argument('--no-charges', action='store_true', default=False)
args = parser.parse_args()


STRATEGY_NAME_MAP = {
    "S2 - Renko Reversal (Bot Running)": "RenkoReversalStrategy",
    "S4 - Renko SMIIO Supertrend (Bot Running)": "RenkoSMIIOSupertrendStrategy",
    "Renko Breakout": "RenkoBreakoutStrategy",
    "Renko Options": "RenkoOptionsStrategy",
    "Renko Pattern Breakout": "RenkoPatternBreakoutStrategy",
    "Renko Trendline Pullback": "RenkoTrendlinePullbackStrategy",
}

args.strategy = STRATEGY_NAME_MAP.get(args.strategy, args.strategy)
print(f"Running optimisation: {args.strategy} | Group: {args.group} | {args.start} to {args.end}")

available = strategy_registry.get_all_strategies()
if args.strategy not in available:
    print(f"ERROR: Strategy {args.strategy} not found")
    sys.exit(1)

PREDEFINED_RANGES = {
    "supertrend": {
        "st_atr_length": {"values": [5, 7, 10, 14]},
        "st_factor": {"values": [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]}
    },
    "smiio": {
        "smiio_shortlen": {"values": [10, 14, 20, 30]},
        "smiio_siglen": {"values": [3, 5, 7, 9]}
    },
    "renko": {
        "renko_box_pct": {"values": [0.001, 0.0015, 0.002, 0.0025, 0.003]},
        "renko_timeframe": {"values": ["30m", "1h", "2h", "4h"]}
    },
    "s2_combined": {
        "renko_box_pct":   {"values": [0.001, 0.0015, 0.002]},
        "renko_timeframe": {"values": ["30m", "1h", "2h"]},
        "st_atr_length":   {"values": [5, 7, 10]},
        "st_factor":       {"values": [1.5, 2.0, 3.0]}
    },
    "s4_combined": {
        "renko_box_pct":   {"values": [0.001, 0.0015]},
        "renko_timeframe": {"values": ["1m", "5m", "15m", "30m", "1h", "2h"]},
        "st_atr_length":   {"values": [5, 10]},
        "st_factor":       {"values": [1.5, 2.0, 3.0]},
        "smiio_shortlen":  {"values": [10, 20]},
        "smiio_siglen":    {"values": [3, 7, 9]}
    },
    "s4v2_combined": {
        "renko_box_pct":   {"values": [0.001, 0.0015]},
        "renko_timeframe": {"values": ["15m", "30m", "1h", "2h"]},
        "st_atr_length":   {"values": [5, 10]},
        "st_factor":       {"values": [1.5, 2.0, 3.0]},
        "smiio_shortlen":  {"values": [10, 20]},
        "smiio_longlen":   {"values": [10, 20, 30]},
        "smiio_siglen":    {"values": [3, 7, 9]}
    },
    "sma_adx_combined": {
        "sma_fast_len":        {"values": [10, 20, 30]},
        "sma_slow_len":        {"values": [50, 100, 200]},
        "adx_period":          {"values": [10, 14, 20]},
        "adx_entry_threshold": {"values": [20.0, 25.0, 30.0]},
        "adx_exit_threshold":  {"values": [15.0, 20.0, 25.0]},
        "atr_period":          {"values": [10, 14, 20]},
        "atr_mult":            {"values": [1.5, 2.0, 2.5, 3.0]}
    },
    "ema_pullback_combined": {
        "ema_fast_len":   {"values": [10, 20, 30]},
        "ema_slow_len":   {"values": [30, 50, 100]},
        "rsi_period":     {"values": [10, 14, 20]},
        "swing_lookback": {"values": [3, 5, 10]}
    },
    "supertrend_pullback_combined": {
        "st_atr_period": {"values": [7, 10, 14]},
        "st_mult":       {"values": [2.0, 3.0, 4.0]},
        "ema_len":       {"values": [30, 50, 100]}
    },
    "range_breakout_combined": {
        "range_lookback":  {"values": [10, 20, 30]},
        "atr_period":      {"values": [10, 14, 20]},
        "atr_ma_period":   {"values": [10, 20, 30]},
        "atr_trail_mult":  {"values": [2.0, 3.0, 4.0]}
    },
    "donchian_breakout_combined": {
        "donchian_period": {"values": [10, 20, 30]},
        "adx_period":      {"values": [10, 14, 20]},
        "adx_threshold":   {"values": [15.0, 20.0, 30.0]},
        "atr_mult":        {"values": [1.5, 2.0, 3.0]}
    }
}

PREDEFINED_RANGES["s4v3_smiio_all"] = {
    "renko_box_pct":   {"values": [0.002, 0.0025, 0.003, 0.0035, 0.004, 0.005, 0.006, 0.0075]},
    "renko_timeframe": {"values": ["1m"]},
    "smiio_shortlen":  {"values": [10, 14, 20, 30]},
    "smiio_longlen":   {"values": [10, 20, 30, 40]},
    "smiio_siglen":    {"values": [3, 5, 7, 9]}
}


PREDEFINED_RANGES["s4_full_grid_box1"] = {
    "renko_box_pct":   {"values": [0.002]},
    "renko_timeframe": {"values": ["1m"]},
    "st_atr_length":   {"values": [7, 10, 14]},
    "st_factor":       {"values": [2.0, 2.5, 3.0]},
    "smiio_shortlen":  {"values": [10, 14, 20, 30]},
    "smiio_longlen":   {"values": [10, 20, 30, 40]},
    "smiio_siglen":    {"values": [3, 5, 7, 9]}
}

PREDEFINED_RANGES["s4_full_grid_box2"] = {
    "renko_box_pct":   {"values": [0.0025]},
    "renko_timeframe": {"values": ["1m"]},
    "st_atr_length":   {"values": [7, 10, 14]},
    "st_factor":       {"values": [2.0, 2.5, 3.0]},
    "smiio_shortlen":  {"values": [10, 14, 20, 30]},
    "smiio_longlen":   {"values": [10, 20, 30, 40]},
    "smiio_siglen":    {"values": [3, 5, 7, 9]}
}

PREDEFINED_RANGES["s4_full_grid_box3"] = {
    "renko_box_pct":   {"values": [0.003]},
    "renko_timeframe": {"values": ["1m"]},
    "st_atr_length":   {"values": [7, 10, 14]},
    "st_factor":       {"values": [2.0, 2.5, 3.0]},
    "smiio_shortlen":  {"values": [10, 14, 20, 30]},
    "smiio_longlen":   {"values": [10, 20, 30, 40]},
    "smiio_siglen":    {"values": [3, 5, 7, 9]}
}

PREDEFINED_RANGES["s4_full_grid_box4"] = {
    "renko_box_pct":   {"values": [0.0035]},
    "renko_timeframe": {"values": ["1m"]},
    "st_atr_length":   {"values": [7, 10, 14]},
    "st_factor":       {"values": [2.0, 2.5, 3.0]},
    "smiio_shortlen":  {"values": [10, 14, 20, 30]},
    "smiio_longlen":   {"values": [10, 20, 30, 40]},
    "smiio_siglen":    {"values": [3, 5, 7, 9]}
}

PREDEFINED_RANGES["s4_full_grid_box5"] = {
    "renko_box_pct":   {"values": [0.004]},
    "renko_timeframe": {"values": ["1m"]},
    "st_atr_length":   {"values": [7, 10, 14]},
    "st_factor":       {"values": [2.0, 2.5, 3.0]},
    "smiio_shortlen":  {"values": [10, 14, 20, 30]},
    "smiio_longlen":   {"values": [10, 20, 30, 40]},
    "smiio_siglen":    {"values": [3, 5, 7, 9]}
}

PREDEFINED_RANGES["s4_full_grid_box6"] = {
    "renko_box_pct":   {"values": [0.005]},
    "renko_timeframe": {"values": ["1m"]},
    "st_atr_length":   {"values": [7, 10, 14]},
    "st_factor":       {"values": [2.0, 2.5, 3.0]},
    "smiio_shortlen":  {"values": [10, 14, 20, 30]},
    "smiio_longlen":   {"values": [10, 20, 30, 40]},
    "smiio_siglen":    {"values": [3, 5, 7, 9]}
}

if args.group not in PREDEFINED_RANGES:
    print(f"ERROR: Group {args.group} not found")
    print(f"Available groups: {list(PREDEFINED_RANGES.keys())}")
    sys.exit(1)

param_ranges = PREDEFINED_RANGES[args.group]

if args.no_charges:
    import config.charges_config as cc
    cc.charges_config['taker_fee_rate'] = 0.0
    cc.charges_config['tax_rate'] = 0.0
    cc.charges_config['funding_rate_annual'] = 0.0
    cc.charges_config['insurance_fund_rate'] = 0.0

optimizer = Optimizer(
    strategy_class=available[args.strategy],
    symbol=args.symbol,
    start_date=args.start,
    end_date=args.end,
    csv_path=args.csv
)
optimizer.final_params_to_optimize = param_ranges

results = optimizer.run_optimization()

if results:
    analyzer = OptimizationAnalyzer(results, args.strategy, args.symbol, args.start, args.end, lot_size=args.lots, slippage=args.slippage, include_charges=not args.no_charges)
    analyzer.generate_html_report()
    print("Optimisation complete - reports saved to output/")
else:
    print("ERROR: Optimisation failed")
    sys.exit(1)

# Save optimization results as CSV
if results:
    import pandas as pd
    from datetime import datetime
    SKIP_KEYS = {"equity_curve", "equity_curve_inr", "drawdown_series", "monthly_returns", "yearly_returns"}
    rows = []
    for r in results:
        params = r.get("parameters", {})
        metrics = r.get("metrics", {})
        row = {}
        row.update(params)
        for k, v in metrics.items():
            if k in SKIP_KEYS:
                continue
            if isinstance(v, (int, float, str, bool)) or hasattr(v, "item"):
                row[k] = float(v) if hasattr(v, "item") else v
        rows.append(row)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    strat_name = available[args.strategy].__name__
    csv_out = f"output/optimization_results_{strat_name}_{args.symbol}_{ts}.csv"
    pd.DataFrame(rows).to_csv(csv_out, index=False)
    print(f"CSV saved: {csv_out}")
    import glob as _glob_t, os as _os_t
    _html_matches = sorted(_glob_t.glob(f"output/optimization_results_{strat_name}_{args.symbol}_*.html"), key=_os_t.path.getmtime, reverse=True)
    _html_nm = _os_t.path.basename(_html_matches[0]) if _html_matches else "N/A"
    print(f"\n=== TERMINAL RUN COMPLETE - {strat_name} | HTML: {_html_nm} | CSV: {_os_t.path.basename(csv_out)} ===")
