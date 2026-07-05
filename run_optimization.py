# run_optimization.py
# Responsibility: Script to run strategy optimization

from engine.optimizer import Optimizer
from engine.optimization_analyzer import OptimizationAnalyzer
from strategy_registry import strategy_registry
from datetime import datetime, timedelta
from config.backtest_config import backtest_config
import os
import itertools

# ================================================================
# PHASE-1 OPTIMIZATION PARAMETER RANGES (COPY-PASTE READY)
# Never type ranges manually - all defined here
# ================================================================

PREDEFINED_RANGES = {
    "supertrend": {
        "atr_length": {"values": [5, 7, 10, 14]},
        "factor":     {"values": [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]}
    },
    "smiio": {
        "smiio_length": {"values": [10, 14, 20, 30]},
        "smiio_signal": {"values": [3, 5, 7, 9]}
    },
    "distance_filter": {
        # Corrected: cross_gap values in data are 0.06–2.09 (SMI scale)
        # Range now covers actual gap distribution to trigger filter
        "crossover_distance":      {"values": [0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 2.5]},
        "crossover_count_limit":   {"values": [1, 2, 3]},
        "smiio_avoid_entry_above": {"values": [0.2, 0.3, 0.4, 0.5, 0.6]}
    },
    "renko": {
        "renko_timeframe": {"values": ["1m", "5m", "15m", "30m", "1h", "2h"]},
        "renko_box_pct":   {"values": [0.0004, 0.0005, 0.0006, 0.0007, 0.0008,
                                        0.0009, 0.0010, 0.0015, 0.0020, 0.0025]}
    }
}



# Full sweep = all groups combined
FULL_SWEEP_PARAMS = {}
for group in PREDEFINED_RANGES.values():
    FULL_SWEEP_PARAMS.update(group)


def select_strategy():
    print("\n" + "=" * 70)
    print("STRATEGY OPTIMIZATION")
    print("=" * 70)
    print("\nAvailable Strategies:")
    available_strategies = strategy_registry.get_all_strategies()
    for i, name in enumerate(available_strategies.keys()):
        print(f"  {i + 1}. {name}")
    choice = int(input("Select strategy (number): "))
    selected_name = list(available_strategies.keys())[choice - 1]
    selected_class = available_strategies[selected_name]
    print(f"Selected: {selected_name}")
    return selected_name, selected_class


def select_date_range():
    print("\nSelect date range:")
    date_presets = backtest_config.get("date_range_presets", {})
    for i, label in enumerate(date_presets.keys()):
        print(f"  {i + 1}. {label.replace('_', ' ').title()}")
    print(f"  {len(date_presets) + 1}. Custom Date Range")
    date_choice = int(input("Enter choice: "))
    end_date = datetime.now().strftime("%Y-%m-%d")
    if date_choice <= len(date_presets):
        selected_preset = list(date_presets.values())[date_choice - 1]
        days = selected_preset.get("days", 0)
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    else:
        start_date = input("Enter custom start date (YYYY-MM-DD): ")
        end_date = input("Enter custom end date (YYYY-MM-DD): ")
    print(f"Date range: {start_date} to {end_date}")
    return start_date, end_date


def select_csv_and_symbol():
    csv_path = input(
        f"Enter CSV file path (or press Enter for default: "
        f"{backtest_config.get('default_csv_path', 'data/btc_ohlcv.csv')}): "
    ).strip()
    if not csv_path:
        csv_path = backtest_config.get('default_csv_path', 'data/btc_ohlcv.csv')
    print(f"CSV file: {csv_path}")

    symbol = input("Enter symbol (e.g., BTCUSD, ETHUSD) [default: BTCUSD]: ").strip().upper()
    if not symbol:
        symbol = "BTCUSD"
    print(f"Symbol: {symbol}")
    return csv_path, symbol


def run_optimization_workflow():
    # --- Step 1: Select Strategy ---
    selected_strategy_name, selected_strategy_class = select_strategy()

    # --- Step 2: Select Optimization Mode ---
    print("\n" + "=" * 70)
    print("SELECT OPTIMIZATION MODE")
    print("=" * 70)
    print("  1. Separate Parameter Optimization")
    print("     - Optimize one parameter group at a time")
    print("     - All other params stay at strategy defaults")
    print("     - Faster, focused results")
    print()
    print("  2. Full Sweep (Single Execution)")
    print("     - All parameter groups optimized together")
    print("     - Every combination tested (grid search)")
    print("     - Slower but finds global best combination")
    print()
    mode_choice = int(input("Select mode (1 or 2): "))
    if mode_choice not in [1, 2]:
        print("Invalid choice. Please enter 1 or 2.")
        return


    # --- Step 3: Build params to optimize ---
    if mode_choice == 1:
        # SEPARATE MODE - pick one group
        print("\nSelect parameter group to optimize:")
        group_names = list(PREDEFINED_RANGES.keys())
        for i, g in enumerate(group_names):
            params_in_group = list(PREDEFINED_RANGES[g].keys())
            print(f"  {i + 1}. {g.upper()} {params_in_group}")
        group_choice = int(input("Select group (number): ")) - 1
        selected_group_name = group_names[group_choice]
        final_params_to_optimize = PREDEFINED_RANGES[selected_group_name]
        print(f"\nOptimizing group: {selected_group_name.upper()}")
        for k, v in final_params_to_optimize.items():
            print(f"  {k}: {v['values']}")

    else:
        # FULL SWEEP MODE - all groups
        final_params_to_optimize = FULL_SWEEP_PARAMS
        total_combos = 1
        for v in final_params_to_optimize.values():
            total_combos *= len(v['values'])
        print(f"\nFull sweep selected — {total_combos} total combinations")
        for k, v in final_params_to_optimize.items():
            print(f"  {k}: {v['values']}")

    # --- Step 4: Date range, CSV, Symbol ---
    start_date, end_date = select_date_range()
    csv_path, symbol = select_csv_and_symbol()

    # --- Step 4b: Slippage input (dynamic, same as backtest) ---
    slippage_input = input("Enter slippage per trade in USD (press Enter for default 0): ").strip()
    slippage = float(slippage_input) if slippage_input else 0.0
    print(f"Slippage: ${slippage} USD/trade")

    # --- Step 5: Run Optimizer ---
    optimizer = Optimizer(
        strategy_class=selected_strategy_class,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        csv_path=csv_path
    )
    optimizer.final_params_to_optimize = final_params_to_optimize
    optimization_results = optimizer.run_optimization()

    # --- Step 6: Analyze and Report ---
    analyzer = OptimizationAnalyzer(
        optimization_results=optimization_results,
        strategy_name=selected_strategy_name,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        lot_size=100,
        slippage=slippage,  # FIXED: dynamic input from user
    )

    report_path = analyzer.generate_html_report()
    print(f"\nOptimization report generated: {report_path}")


if __name__ == "__main__":
    run_optimization_workflow()
