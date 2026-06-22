# run_single_strategy.py
# Responsibility: Run single strategy backtest

from engine.backtest_engine import run_backtest
from strategy_registry import strategy_registry
from config.backtest_config import backtest_config
from backtest_analyzer import BacktestReportGenerator # Corrected import path
from datetime import datetime, timedelta
import os
import pandas as pd


def run_single_strategy():
    """
    Run single strategy backtest workflow.
    """
    print("\n" + "=" * 70)
    print("SINGLE STRATEGY BACKTEST")
    print("=" * 70)

    # 1. Select Strategy
    # The strategy_registry.get_all_strategies() already prints registered strategies
    available_strategies = strategy_registry.get_all_strategies()
    print("\nAvailable Strategies:")
    print("=" * 50)

    for i, (name, strategy_class) in enumerate(available_strategies.items(), 1):
        print(f"{i}. {name}")

    print("=" * 50)

    choice = int(input("Select strategy (number): "))
    selected_strategy_name = list(available_strategies.keys())[choice - 1]
    selected_strategy_class = available_strategies[selected_strategy_name]
    print(f"✅ Selected: {selected_strategy_name}")

    # 2. Enter Lot Size
    lot_size = int(input("\nEnter lot size (e.g., 1000): "))
    print(f"✅ Lot size: {lot_size}")

    # 3. Select Date Range
    print("\nSelect date range:")
    date_presets = backtest_config.get("date_range_presets", {})
    for i, (label, info) in enumerate(date_presets.items(), 1):
        print(f"{i}. {label.replace('_', ' ').title()}")
    print(f"{len(date_presets) + 1}. Custom Date Range")

    while True:
        try:
            date_choice = int(input("\nEnter choice (1-5): "))
            if date_choice in range(1, 6):
                break
            print("  Please enter a number between 1 and 5.")
        except ValueError:
            print("  Invalid input. Please enter a number between 1 and 5.")

    start_date = None
    end_date = datetime.now().strftime("%Y-%m-%d")

    if date_choice <= len(date_presets):
        selected_preset = list(date_presets.values())[date_choice - 1]
        days = selected_preset.get("days", 0)
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    else:
        start_date = input("Enter custom start date (YYYY-MM-DD): ")
        end_date = input("Enter custom end date (YYYY-MM-DD): ")

    print(f"✅ Date range: {start_date} to {end_date}")

    # 4. CSV File Path
    default_csv = backtest_config.get('default_csv_path', 'data/btc_1m_delta.csv')
    csv_input = input(f"\nEnter CSV file path (or press Enter for default):\nCSV path [{default_csv}]: ")
    csv_path = csv_input if csv_input else default_csv
    print(f"✅ CSV file: {csv_path}")

    # 5. Run Backtest
    print("\n" + "=" * 70)
    print("RUNNING BACKTEST...")
    print("=" * 70)

    try:
        result = run_backtest(
            strategy_class=selected_strategy_class,
            symbol="BTCUSD",
            lot_size=lot_size,
            start_date=start_date,
            end_date=end_date,
            csv_path=csv_path
        )

        # 6. Generate Reports
        print("\n[Step 7] Generating reports...")  # Changed message
        generator = BacktestReportGenerator(  # RE-INSTANTIATED
            trades=result['trades'],
            metrics=result['metrics'],
            strategy_name=selected_strategy_name,
            symbol="BTCUSD",
            start_date=start_date,
            end_date=end_date
        )

        html_report_path = generator.generate_html_report()  # GENERATE HTML
        csv_log_path = generator.generate_csv_trade_log()  # GENERATE CSV

        print(f"✅ HTML report saved: {html_report_path}")
        print(f"✅ Trade log saved: {csv_log_path}")
        print(f"✅ Reports generated successfully")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_single_strategy()
