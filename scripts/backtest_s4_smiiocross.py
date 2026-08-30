# scripts/backtest_s4_smiiocross.py
# STANDALONE backtest runner for S4V3 (SMIIO-CROSS TEST VARIANT)
# Isolated file - does NOT modify run_backtest_cli.py or any S4/S4V2 file.
# Uses the SAME engine + SAME HTML report generator as the original CLI.

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.backtest_engine_v2 import run_backtest
from strategy_registry import strategy_registry
from backtest_analyzer import BacktestReportGenerator
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

print(f"Running S4V3 (SMIIO-CROSS) backtest: {args.strategy} | Lots: {args.lots} | {args.start} to {args.end}")

available = strategy_registry.get_all_strategies()
if args.strategy not in available:
    print(f"ERROR: Strategy {args.strategy} not found")
    print(f"Available: {list(available.keys())}")
    sys.exit(1)

strategy_class = available[args.strategy]

if args.no_charges:
    import config.charges_config as cc
    cc.charges_config['taker_fee_rate'] = 0.0
    cc.charges_config['tax_rate'] = 0.0
    cc.charges_config['funding_rate_annual'] = 0.0
    cc.charges_config['insurance_fund_rate'] = 0.0

# Explicit params - SAME Renko/SMIIO params as live-matched S4 (box_pct=0.001, 2h, smiio 10/10/3)
# Supertrend params intentionally NOT included - not used by this strategy.
strategy_params = dict(
    renko_box_pct=0.001,
    renko_timeframe="2h",
    smiio_shortlen=10,
    smiio_longlen=10,
    smiio_siglen=3,
)
print(f"Using S4V3 params (SMIIO-cross, Renko/SMIIO identical to S4): {strategy_params}")

# Frozen reference_price support (isolated file, own suffix s4v3, won't clash with s4/s4v2)
if args.symbol == "BTCUSD":
    _ref_path = "logs/box_ref_price_s4v3.txt"
    if os.path.exists(_ref_path):
        try:
            strategy_params["reference_price"] = float(open(_ref_path).read().strip())
            print(f"Using frozen reference_price={strategy_params['reference_price']} from {_ref_path}")
        except Exception as _e:
            print(f"WARNING: could not read {_ref_path}: {_e} - falling back to live recalculation")

result = run_backtest(
    strategy_class=strategy_class,
    symbol=args.symbol,
    lot_size=args.lots,
    start_date=args.start,
    end_date=args.end,
    csv_path=args.csv,
    strategy_params=strategy_params or None,
    slippage=args.slippage
)

if result:
    print("Backtest complete")
    metrics = result.get('metrics', {})
    skip_keys = ['equity_curve', 'equity_curve_inr', 'drawdown_series']
    for k, v in metrics.items():
        if k not in skip_keys:
            print(f"{k}: {v}")

    reporter = BacktestReportGenerator(
        trades=result.get('trades', []),
        metrics=result.get('metrics', {}),
        strategy_name=args.strategy,
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        slippage=args.slippage,
        lot_size=args.lots,
        include_charges=not args.no_charges
    )
    _html_out = reporter.generate_html_report()
    _csv_out = reporter.generate_csv_trade_log()
    import os as _os_t
    print(f"\n=== TERMINAL RUN COMPLETE - {args.strategy} | HTML: {_os_t.path.basename(_html_out)} | CSV: {_os_t.path.basename(_csv_out)} ===")
else:
    print("ERROR: Backtest failed")
    sys.exit(1)
