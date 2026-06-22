# run_optimization.py
# Responsibility: Script to run strategy optimization

from engine.optimizer import Optimizer
from engine.optimization_analyzer import OptimizationAnalyzer
from strategy_registry import strategy_registry  # This now imports the instance
from datetime import datetime, timedelta
from config.backtest_config import backtest_config
import os
import itertools  # Make sure itertools is imported


def run_optimization_workflow():
    """
    Guides the user through the optimization process.
    """
    print("\n" + "=" * 70)
    print("STRATEGY OPTIMIZATION")
    print("=" * 70)

    # 1. Select Strategy
    print("\nAvailable Strategies:")
    # FIX: Access the dictionary via get_all_strategies()
    available_strategies = strategy_registry.get_all_strategies()
    for i, (name, strategy_class) in enumerate(available_strategies.items()):
        print(f"{i + 1}. {name}")

    choice = int(input("Select strategy (number): "))
    # FIX: Access the dictionary via get_all_strategies()
    selected_strategy_name = list(available_strategies.keys())[choice - 1]
    selected_strategy_class = available_strategies[selected_strategy_name]  # FIX: Access the dictionary
    print(f"✅ Selected: {selected_strategy_name}")

    # 2. Define Optimization Parameters (from strategy's optimization_params)
    # FIX: Pass a dummy data_dict and lot_size to the strategy constructor
    strategy_instance_for_params = selected_strategy_class({}, 1)  # Dummy instance to get params
    params_info = strategy_instance_for_params.optimization_params

    print("\nAvailable Parameters for Optimization:")
    for i, (param_name, info) in enumerate(params_info.items()):
        if 'values' in info:
            print(f"{i + 1}. {param_name.replace('_', ' ').title()} (Values: {info['values']})")
        else:
            print(
                f"{i + 1}. {param_name.replace('_', ' ').title()} (Range: {info['min']}-{info['max']}-{info['step']})")

    selected_param_indices_str = input("Select parameters to optimize (comma-separated numbers, e.g., 1,3): ")
    selected_param_indices = [int(x.strip()) - 1 for x in selected_param_indices_str.split(',')]

    # Build the actual optimization ranges based on user selection
    final_params_to_optimize = {}
    for idx in selected_param_indices:
        param_name = list(params_info.keys())[idx]
        param_info = params_info[param_name]

        if 'values' in param_info:
            final_params_to_optimize[param_name] = param_info
        else:
            range_str = input(
                f"Parameter: {param_name.replace('_', ' ').title()} - Enter range (start-end-step, e.g., {param_info['min']}-{param_info['max']}-{param_info['step']}): ")

            # CORRECTED LINE: Use map(float, ...) instead of map(int, ...)
            start, end, step = map(float, range_str.split('-'))
            final_params_to_optimize[param_name] = {'min': start, 'max': end, 'step': step}

    # 3. Select Date Range
    print("\nSelect date range:")
    date_presets = backtest_config.get("date_range_presets", {})
    for i, (label, info) in enumerate(date_presets.items()):
        print(f"{i + 1}. {label.replace('_', ' ').title()}")
    print(f"{len(date_presets) + 1}. Custom Date Range")

    date_choice = int(input("Enter choice: "))
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

    # 4. CSV file path
    csv_path = input(
        f"Enter CSV file path (or press Enter for default: {backtest_config.get('default_csv_path', 'data/btc_ohlcv.csv')}): ")
    if not csv_path:
        csv_path = backtest_config.get('default_csv_path', 'data/btc_ohlcv.csv')
    print(f"✅ CSV file: {csv_path}")

    # Run Optimization
    optimizer = Optimizer(
        strategy_class=selected_strategy_class,
        symbol="BTCUSD",  # Assuming BTCUSD for now, can be made dynamic
        start_date=start_date,
        end_date=end_date,
        csv_path=csv_path
    )

    # Pass the generated combinations to the optimizer
    # This part needs to be integrated into the Optimizer class's run_optimization method
    # For now, let's manually construct the combinations and pass them to the optimizer

    optimizer.final_params_to_optimize = final_params_to_optimize  # Pass the structure to the optimizer

    optimization_results = optimizer.run_optimization()

    # Analyze and Report
    analyzer = OptimizationAnalyzer(
        optimization_results=optimization_results,
        strategy_name=selected_strategy_name,
        symbol="BTCUSD",
        start_date=start_date,
        end_date=end_date
    )
    report_path = analyzer.generate_html_report()
    print(f"\n✅ Optimization report generated: {report_path}")

