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

    # Parameter name mapping: PREDEFINED_RANGES keys → strategy __init__ keys
    # engine/optimizer.py — PARAM_NAME_MAP dict (replace existing)

    PARAM_NAME_MAP = {
        'st_atr_length': 'st_atr_length',
        'st_factor': 'st_factor',
        'smiio_shortlen': 'smiio_shortlen',
        'smiio_siglen': 'smiio_siglen',
        'renko_timeframe': 'renko_timeframe',
        'renko_box_pct': 'renko_box_pct',
    }

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
        import copy

        print("\n" + "=" * 70)
        print(f"STRATEGY OPTIMIZATION - {self.strategy_class.__name__}")
        print("=" * 70)

        params_to_optimize = self.final_params_to_optimize
        param_names = []
        param_values = []

        for param_name, param_info in params_to_optimize.items():
            param_names.append(param_name)
            if 'values' in param_info:
                param_values.append(param_info['values'])
            else:
                start = param_info['min']
                end = param_info['max']
                step = param_info['step']
                values = []
                current_value = start
                epsilon = 1e-9
                while current_value <= end + epsilon:
                    values.append(round(current_value, 5))
                    current_value += step
                param_values.append(values)

        all_combinations = list(itertools.product(*param_values))
        print(f"Testing {len(all_combinations)} parameter combinations...")

        for i, combo in enumerate(all_combinations):
            param_combo = dict(zip(param_names, combo))
            print(f"\n--- Running backtest for combination {i + 1}/{len(all_combinations)} ---")
            print(f"Parameters: {param_combo}")

            lot_size = param_combo.pop('lot_size', backtest_config.get('default_lot_size', 100))

            mapped_combo = {self.PARAM_NAME_MAP.get(k, k): v for k, v in param_combo.items()}
            strategy_params_copy = copy.deepcopy(mapped_combo)

            # DEBUG — confirm exact params reaching engine each combo
            print(f"[OPTIMIZER] combo {i + 1} strategy_params={strategy_params_copy}")

            engine = BacktestEngine(
                strategy_class=self.strategy_class,
                symbol=self.symbol,
                lot_size=lot_size,
                start_date=self.start_date,
                end_date=self.end_date,
                csv_path=self.csv_path,
                strategy_params=strategy_params_copy
            )

            results = engine.run()
            metrics = results['metrics']

            self.optimization_results.append({
                'parameters': mapped_combo,
                'metrics': metrics
            })

        print("\n✅ Optimization complete!")
        return self.optimization_results
