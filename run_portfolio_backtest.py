# run_portfolio_backtest.py
# Responsibility: Entry point for portfolio backtest

from strategy_registry import StrategyRegistry
from engine.backtest_engine import run_backtest
from engine.portfolio_aggregator import PortfolioAggregator
from backtest_analyzer import BacktestReportGenerator  # CHANGED: was BacktestAnalyzer
from config.portfolio_config import portfolios
from datetime import datetime, timedelta
import os


# ADDED: Auto-resolve CSV path from symbol
SYMBOL_CSV_MAP = {
    'BTCUSD': 'data/btc_1m_delta.csv',
    'ETHUSD': 'data/eth_2h_delta.csv',
}


def run_portfolio_backtest():
    """
    Run portfolio backtest workflow.
    """
    print("\n" + "=" * 70)
    print("PORTFOLIO BACKTEST")
    print("=" * 70)

    # Step 1: Choose portfolio type
    print("\nPortfolio Type:")
    print("1. Predefined Portfolio")
    print("2. Dynamic Portfolio (Custom)")

    while True:
        try:
            portfolio_type = int(input("\nSelect type (1-2): "))
            if portfolio_type in [1, 2]:
                break
            else:
                print("❌ Invalid choice. Select 1 or 2")
        except ValueError:
            print("❌ Invalid input. Enter a number.")

    # Step 2: Select strategies
    if portfolio_type == 1:
        # Predefined portfolio
        print("\nAvailable Portfolios:")
        portfolio_names = list(portfolios.keys())
        for i, name in enumerate(portfolio_names, 1):
            print(f"{i}. {name}")

        while True:
            try:
                portfolio_num = int(input("\nSelect portfolio (number): "))
                if 1 <= portfolio_num <= len(portfolio_names):
                    selected_portfolio_name = portfolio_names[portfolio_num - 1]
                    selected_portfolio = portfolios[selected_portfolio_name]
                    break
                else:
                    print(f"❌ Invalid selection. Choose 1-{len(portfolio_names)}")
            except ValueError:
                print("❌ Invalid input. Enter a number.")

        print(f"✅ Selected: {selected_portfolio_name}")
        strategy_configs = selected_portfolio['strategies']

    else:
        # Dynamic portfolio
        registry = StrategyRegistry()
        registry.display_menu()

        strategy_nums = input("\nEnter strategy numbers (comma-separated, e.g., 1,3,5): ").strip()

        try:
            strategy_nums = [int(x.strip()) for x in strategy_nums.split(',')]
            strategies_list = list(registry.get_all_strategies().items())

            strategy_configs = []
            for num in strategy_nums:
                if 1 <= num <= len(strategies_list):
                    strategy_name, _ = strategies_list[num - 1]
                    strategy_configs.append({
                        'name': strategy_name,
                    })
                else:
                    print(f"❌ Invalid strategy number: {num}")
                    return

            print(f"✅ Selected {len(strategy_configs)} strategies")

        except ValueError:
            print("❌ Invalid input. Use comma-separated numbers.")
            return

    # ADDED: Step 2b - Get symbol (single symbol for all strategies)
    symbol_input = input("\nEnter symbol (or press Enter for default) [BTCUSD]: ").strip().upper()
    symbol = symbol_input if symbol_input else "BTCUSD"
    print(f"✅ Symbol: {symbol}")

    # ADDED: Auto-resolve CSV path from symbol
    csv_path = SYMBOL_CSV_MAP.get(symbol)
    if not csv_path:
        print(f"❌ No CSV mapping found for symbol: {symbol}")
        print(f"   Supported symbols: {', '.join(SYMBOL_CSV_MAP.keys())}")
        return
    if not os.path.exists(csv_path):
        print(f"❌ CSV file not found: {csv_path}")
        return
    print(f"✅ CSV file: {csv_path}")

    # Step 3: Get lot sizes for each strategy
    print("\nEnter lot size for each strategy:")
    lot_sizes = {}

    for config in strategy_configs:
        strategy_name = config['name']
        while True:
            try:
                lot_size = int(input(f"  {strategy_name} lot size (e.g., 1000): "))
                if lot_size > 0:
                    lot_sizes[strategy_name] = lot_size
                    break
                else:
                    print("❌ Lot size must be positive")
            except ValueError:
                print("❌ Invalid input. Enter a number.")

    # ADDED: Step 3b - Get slippage
    while True:
        try:
            slippage = float(input("\nEnter slippage per side in $ (or 0 for none): "))
            if slippage >= 0:
                print(f"✅ Slippage: {'None' if slippage == 0 else f'${slippage}/side'}")
                break
            else:
                print("❌ Slippage must be 0 or positive")
        except ValueError:
            print("❌ Invalid input. Enter a number.")

    # Step 4: Get date range
    print("\nSelect date range:")
    print("1. Last 1 Month")
    print("2. Last 3 Months")
    print("3. Last 6 Months")
    print("4. Last 1 Year")
    print("5. Custom Date Range")

    while True:
        try:
            date_choice = int(input("\nEnter choice (1-5): "))

            if date_choice == 1:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
            elif date_choice == 2:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=90)
            elif date_choice == 3:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=180)
            elif date_choice == 4:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=365)
            elif date_choice == 5:
                start_str = input("Enter start date (YYYY-MM-DD): ")
                end_str = input("Enter end date (YYYY-MM-DD): ")
                start_date = datetime.strptime(start_str, "%Y-%m-%d")
                end_date = datetime.strptime(end_str, "%Y-%m-%d")
            else:
                print("❌ Invalid choice. Select 1-5")
                continue

            start_date_str = start_date.strftime("%Y-%m-%d")
            end_date_str = end_date.strftime("%Y-%m-%d")
            print(f"✅ Date range: {start_date_str} to {end_date_str}")
            break

        except ValueError:
            print("❌ Invalid input. Use YYYY-MM-DD format.")

    # Step 5: Run portfolio backtest
    print("\n" + "=" * 70)
    print("RUNNING PORTFOLIO BACKTEST...")
    print("=" * 70)

    registry = StrategyRegistry()
    aggregator = PortfolioAggregator(initial_capital=100000)
    all_trades = []
    individual_capitals = []

    try:
        for config in strategy_configs:
            strategy_name = config['name']
            lot_size = lot_sizes[strategy_name]

            print(f"\n[Strategy] {strategy_name}")

            strategy_class = registry.get_strategy(strategy_name)

            result = run_backtest(
                strategy_class=strategy_class,
                symbol=symbol,
                lot_size=lot_size,
                start_date=start_date_str,
                end_date=end_date_str,
                csv_path=csv_path,
                slippage=slippage  # ADDED
            )

            all_trades.append(result['trades'])
            # Collect individual recommended capital = 3x individual max DD
            ind_dd = result.get('metrics', {}).get('max_drawdown_inr', 0)
            individual_capitals.append(abs(ind_dd) * 3)

        # Aggregate trades
        print("\n" + "=" * 70)
        print("AGGREGATING PORTFOLIO...")
        print("=" * 70)

        combined_trades = aggregator.aggregate_trades(all_trades)
        portfolio_metrics = aggregator.calculate_portfolio_metrics()

        # Generate HTML report
        print("\n" + "=" * 70)
        print("GENERATING PORTFOLIO REPORT...")
        print("=" * 70)

        portfolio_name = selected_portfolio_name if portfolio_type == 1 else "Portfolio_Dynamic"

        # CHANGED: Use BacktestReportGenerator (same as single strategy)
        portfolio_capital = sum(individual_capitals) if individual_capitals else None
        generator = BacktestReportGenerator(
            trades=combined_trades,
            metrics=portfolio_metrics,
            strategy_name=portfolio_name,
            symbol=symbol,
            start_date=start_date_str,
            end_date=end_date_str,
            slippage=slippage,
            portfolio_capital=portfolio_capital
        )

        html_file = generator.generate_html_report()
        csv_file = generator.generate_csv_trade_log()
        # Rename to portfolio_report_* for dashboard identification
        import shutil, os
        from datetime import datetime as _dt
        _ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        _new_html = f"output/portfolio_report_{portfolio_name}_{symbol}_{_ts}.html"
        _new_csv  = f"output/portfolio_trade_log_{portfolio_name}_{symbol}_{_ts}.csv"
        if html_file and os.path.exists(html_file):
            shutil.move(html_file, _new_html)
            html_file = _new_html
        if csv_file and os.path.exists(csv_file):
            shutil.move(csv_file, _new_csv)
            csv_file = _new_csv

        print(f"\n✅ Portfolio report generated: {html_file}")
        print(f"✅ Trade log saved: {csv_file}")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_portfolio_backtest()
