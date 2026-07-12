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
    }
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
    analyzer = OptimizationAnalyzer(results, args.strategy, args.symbol)
    analyzer.generate_report()
    print("Optimisation complete - reports saved to output/")
else:
    print("ERROR: Optimisation failed")
    sys.exit(1)
