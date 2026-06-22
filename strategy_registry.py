# strategy_registry.py
# Responsibility: Auto-discover and register all strategies

import importlib
import inspect
from pathlib import Path
from strategies.base_strategy import BaseStrategy


class StrategyRegistry:
    """
    Auto-discovers and registers all strategies from strategies/ folder.
    """

    def __init__(self):
        """Initialize StrategyRegistry."""
        self.strategies = {}
        self.load_all_strategies()

    def load_all_strategies(self):
        """
        Scan strategies/ folder and load all strategy classes.
        """
        strategy_dir = Path("strategies")

        # Get all .py files in strategies folder
        for strategy_file in strategy_dir.glob("*.py"):
            # Skip __init__.py and base_strategy.py
            if strategy_file.name in ["__init__.py", "base_strategy.py"]:
                continue

            module_name = strategy_file.stem

            try:
                # Import module
                module = importlib.import_module(f"strategies.{module_name}")

                # Find all classes that inherit from BaseStrategy
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, BaseStrategy) and obj != BaseStrategy:
                        self.strategies[name] = obj
                        print(f"✅ Registered strategy: {name}")

            except Exception as e:
                print(f"⚠️  Error loading {module_name}: {e}")

    def get_all_strategies(self):
        """
        Get all registered strategies.

        Returns
        -------
        dict
            Dictionary of strategy name -> strategy class
        """
        return self.strategies

    def get_strategy(self, name):
        """
        Get specific strategy by name.

        Parameters
        ----------
        name : str
            Strategy name

        Returns
        -------
        class
            Strategy class
        """
        if name not in self.strategies:
            raise ValueError(f"Strategy '{name}' not found. Available: {list(self.strategies.keys())}")
        return self.strategies[name]

    def get_strategy_info(self, name):
        """
        Get strategy information.

        Parameters
        ----------
        name : str
            Strategy name

        Returns
        -------
        dict
            Strategy info
        """
        strategy_class = self.get_strategy(name)

        # Create dummy instance to get properties
        dummy_data = {'30M': None}
        try:
            instance = strategy_class(dummy_data, 1)
            return {
                'name': name,
                'required_timeframes': instance.required_timeframes,
                'optimization_params': instance.optimization_params
            }
        except:
            return {'name': name}

    def display_menu(self):
        """
        Display strategy menu.
        """
        print("\nAvailable Strategies:")
        print("=" * 50)

        for i, (name, strategy_class) in enumerate(self.strategies.items(), 1):
            print(f"{i}. {name}")

        print("=" * 50)


# Create a singleton instance of the StrategyRegistry
strategy_registry = StrategyRegistry()
