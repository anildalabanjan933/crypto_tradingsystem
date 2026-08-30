# scripts/optimize_s4_smiiocross.py
# STANDALONE optimizer for S4V3 (SMIIO-CROSS TEST VARIANT)
# Isolated file - does NOT modify run_optimization_cli.py or any S4/S4V2 file.
# Uses the SAME Optimizer engine + SAME OptimizationAnalyzer as the original CLI.

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.optimizer import Optimizer
from engine.optimization_analyzer import OptimizationAnalyzer
from strategy_registry import strategy_registry
from datetime import datetime
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--strategy', default='RenkoSMIIOCrossV3Strategy')
parser.add_argument('--lots', type=int, default=100)
parser.add_argument('--start', required=True)
parser.add_argument('--end', required=True)
parser.add_argument('--slippage', type=float, default=5.0)
parser.add_argument('--symbol', default='BTCUSD')
parser.add_argument('--csv', default='data/btc_1m_delta.csv')
parser.add_argument('--no-charges', action='store_true', default=False)
args = parser.parse_args()

print(f"Running S4V3 (SMIIO-CROSS) FULL optimisation: {args.strategy} | {args.start} to {args.end}")

available = strategy_registry.get_all_strategies()
if args.strategy not in available:
    print(f"ERROR: Strategy {args.strategy} not found")
    print(f"Available: {list(available.keys())}")
    sys.exit(1)

# FULL COMBINATORIAL GRID - timeframe x SMIIO params
# renko_box_pct intentionally FIXED (not swept) - identical to S4/S4V2 (0.001)
# Supertrend params intentionally EXCLUDED - not used by this strategy.
param_ranges = {
    "renko_timeframe": {"values": ["1h","1h30m","2h","2h30m","3h","3h30m","4h"]},
    "smiio_shortlen":  {"values": [5, 10, 14, 20, 30]},
    "smiio_longlen":   {"values": [10, 20, 30, 40]},
    "smiio_siglen":    {"values": [3, 5, 7, 9]},
}

total_combos = 1
for k, v in param_ranges.items():
    total_combos *= len(v["values"])
print(f"Total combinations to run: {total_combos}")

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
