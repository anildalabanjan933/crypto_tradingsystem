# run_portfolio_cli.py
# CLI wrapper for run_portfolio_backtest.py - used by dashboard

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.backtest_engine import run_backtest
from engine.portfolio_aggregator import PortfolioAggregator
from backtest_analyzer import BacktestReportGenerator
from strategy_registry import StrategyRegistry
import argparse
import shutil
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument('--strategies', required=True, help='Comma-separated strategy names')
parser.add_argument('--lots', type=int, default=100)
parser.add_argument('--start', required=True)
parser.add_argument('--end', required=True)
parser.add_argument('--slippage', type=float, default=5.0)
parser.add_argument('--symbol', default='BTCUSD')
parser.add_argument('--csv', default='data/btc_1m_delta.csv')
parser.add_argument('--no-charges', action='store_true', default=False)
args = parser.parse_args()

if args.no_charges:
    import config.charges_config as cc
    cc.charges_config['taker_fee_rate'] = 0.0
    cc.charges_config['tax_rate'] = 0.0
    cc.charges_config['funding_rate_annual'] = 0.0
    cc.charges_config['insurance_fund_rate'] = 0.0

strategy_names = [s.strip() for s in args.strategies.split(',')]
print(f"Running portfolio backtest: {strategy_names} | Lots: {args.lots} | {args.start} to {args.end}")

registry = StrategyRegistry()
available = registry.get_all_strategies()

for s in strategy_names:
    if s not in available:
        print(f"ERROR: Strategy {s} not found")
        print(f"Available: {list(available.keys())}")
        sys.exit(1)

aggregator = PortfolioAggregator(initial_capital=100000)
all_trades = []

for strategy_name in strategy_names:
    print(f"[Strategy] {strategy_name}")
    strategy_class = available[strategy_name]
    result = run_backtest(
        strategy_class=strategy_class,
        symbol=args.symbol,
        lot_size=args.lots,
        start_date=args.start,
        end_date=args.end,
        csv_path=args.csv,
        slippage=args.slippage
    )
    if result:
        all_trades.append(result['trades'])
    else:
        print(f"ERROR: Backtest failed for {strategy_name}")
        sys.exit(1)

combined_trades = aggregator.aggregate_trades(all_trades)
portfolio_metrics = aggregator.calculate_portfolio_metrics()

portfolio_name = "Portfolio_Dynamic"
generator = BacktestReportGenerator(
    trades=combined_trades,
    metrics=portfolio_metrics,
    strategy_name=portfolio_name,
    symbol=args.symbol,
    start_date=args.start,
    end_date=args.end,
    slippage=args.slippage,
    lot_size=args.lots,
    include_charges=not args.no_charges
)

html_file = generator.generate_html_report()
csv_file = generator.generate_csv_trade_log()

# Rename to portfolio_report_* for dashboard identification
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
new_html = f"output/portfolio_report_{portfolio_name}_{args.symbol}_{ts}.html"
new_csv  = f"output/portfolio_trade_log_{portfolio_name}_{args.symbol}_{ts}.csv"

if html_file and os.path.exists(html_file):
    shutil.move(html_file, new_html)
    print(f"Portfolio HTML saved: {new_html}")

if csv_file and os.path.exists(csv_file):
    shutil.move(csv_file, new_csv)
    print(f"Portfolio CSV saved: {new_csv}")

print("Portfolio backtest complete")
