# engine/optimizer.py
# Responsibility: Orchestrates strategy optimization by running multiple backtests

import itertools
from engine.backtest_engine import BacktestEngine
from config.charges_config import charges_config
from config.margin_config import margin_config
from config.backtest_config import backtest_config
from datetime import datetime


class Optimizer:
    """
    Orchestrates strategy optimization by running multiple backtests
    with different parameter combinations.
    """

    def __init__(self, strategy_class, symbol, start_date, end_date, csv_path):
        self.strategy_class = strategy_class
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.csv_path = csv_path
        self.optimization_results = []
        self.final_params_to_optimize = {}  # NEW: To store the parameters to optimize

    def run_optimization(self):
        """
        Generates parameter combinations and runs backtests for each.
        """
        print("\n" + "=" * 70)
        print(f"STRATEGY OPTIMIZATION - {self.strategy_class.__name__}")
        print("=" * 70)

        # Get optimization parameters from the strategy
        # Use self.final_params_to_optimize which is set by run_optimization.py
        params_to_optimize = self.final_params_to_optimize
        param_names = []
        param_values = []

        for param_name, param_info in params_to_optimize.items():
            param_names.append(param_name)
            if 'values' in param_info:  # For discrete values
                param_values.append(param_info['values'])
            else:  # For range (start-end-step)
                start = param_info['min']
                end = param_info['max']
                step = param_info['step']

                # CORRECTED BLOCK: Generate float range manually
                values = []
                current_value = start
                # Use a small epsilon to handle float precision issues in comparison
                epsilon = 1e-9
                while current_value <= end + epsilon:  # Loop until current_value exceeds end
                    values.append(round(current_value, 5))  # Round to avoid float precision display issues
                    current_value += step
                param_values.append(values)

        all_combinations = list(itertools.product(*param_values))
        print(f"Testing {len(all_combinations)} parameter combinations...")

        for i, combo in enumerate(all_combinations):
            param_combo = dict(zip(param_names, combo))
            print(f"\n--- Running backtest for combination {i + 1}/{len(all_combinations)} ---")
            print(f"Parameters: {param_combo}")

            # Extract lot_size for the engine, rest goes to strategy
            # Use .pop() to remove lot_size from param_combo if it's there,
            # so it's not passed twice to strategy_params
            lot_size = param_combo.pop('lot_size', backtest_config.get('default_lot_size', 1))

            engine = BacktestEngine(
                strategy_class=self.strategy_class,
                symbol=self.symbol,
                lot_size=lot_size,
                start_date=self.start_date,
                end_date=self.end_date,
                csv_path=self.csv_path,
                strategy_params=param_combo  # Pass remaining optimization params to the engine
            )

            results = engine.run()

            metrics = results['metrics']

            self.optimization_results.append({
                'parameters': param_combo,  # Store the parameters used for this run
                'metrics': metrics
            })

        print("\n✅ Optimization complete!")
        return self.optimization_results

