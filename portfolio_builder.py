# portfolio_builder.py
# Responsibility: Build dynamic portfolios from strategy selection

from strategy_registry import StrategyRegistry


class PortfolioBuilder:
    """
    Builds dynamic portfolios from user-selected strategies.
    """

    def __init__(self):
        """Initialize PortfolioBuilder."""
        self.registry = StrategyRegistry()
        self.selected_strategies = []
        self.lot_sizes = {}

    def select_strategies(self):
        """
        Allow user to select multiple strategies.

        Returns
        -------
        list
            List of selected strategy configs
        """
        print("\nAvailable Strategies:")
        print("=" * 50)

        self.registry.display_menu()

        strategy_nums = input("\nEnter strategy numbers (comma-separated, e.g., 1,3,5): ").strip()

        try:
            strategy_nums = [int(x.strip()) for x in strategy_nums.split(',')]
            strategies_list = list(self.registry.get_all_strategies().items())

            self.selected_strategies = []
            for num in strategy_nums:
                if 1 <= num <= len(strategies_list):
                    strategy_name, strategy_class = strategies_list[num - 1]
                    self.selected_strategies.append({
                        'name': strategy_name,
                        'class': strategy_class,
                        'symbol': 'BTCUSD'
                    })
                else:
                    print(f"❌ Invalid strategy number: {num}")
                    return None

            print(f"\n✅ Selected {len(self.selected_strategies)} strategies")
            return self.selected_strategies

        except ValueError:
            print("❌ Invalid input. Use comma-separated numbers.")
            return None

    def set_lot_sizes(self):
        """
        Set lot size for each selected strategy.

        Returns
        -------
        dict
            Dictionary of strategy name -> lot size
        """
        print("\nEnter lot size for each strategy:")
        print("=" * 50)

        self.lot_sizes = {}

        for strategy in self.selected_strategies:
            strategy_name = strategy['name']

            while True:
                try:
                    lot_size = int(input(f"{strategy_name} lot size (e.g., 1000): "))
                    if lot_size > 0:
                        self.lot_sizes[strategy_name] = lot_size
                        break
                    else:
                        print("❌ Lot size must be positive")
                except ValueError:
                    print("❌ Invalid input. Enter a number.")

        print(f"\n✅ Lot sizes configured")
        return self.lot_sizes

    def get_portfolio_config(self):
        """
        Get complete portfolio configuration.

        Returns
        -------
        dict
            Portfolio configuration
        """
        if not self.selected_strategies or not self.lot_sizes:
            print("❌ Portfolio not configured. Select strategies and set lot sizes first.")
            return None

        portfolio_config = {
            'name': 'Dynamic Portfolio',
            'strategies': []
        }

        for strategy in self.selected_strategies:
            strategy_name = strategy['name']
            lot_size = self.lot_sizes.get(strategy_name, 1000)

            portfolio_config['strategies'].append({
                'name': strategy_name,
                'symbol': strategy['symbol'],
                'lot_size': lot_size
            })

        return portfolio_config

    def display_portfolio_summary(self):
        """
        Display portfolio summary.
        """
        config = self.get_portfolio_config()

        if not config:
            return

        print("\n" + "=" * 70)
        print("PORTFOLIO SUMMARY")
        print("=" * 70)

        print(f"\nPortfolio Name: {config['name']}")
        print(f"Total Strategies: {len(config['strategies'])}\n")

        print("Strategies:")
        for i, strategy in enumerate(config['strategies'], 1):
            print(f"  {i}. {strategy['name']}")
            print(f"     Symbol: {strategy['symbol']}")
            print(f"     Lot Size: {strategy['lot_size']}")

        print("\n" + "=" * 70)

    def validate_portfolio(self):
        """
        Validate portfolio configuration.

        Returns
        -------
        bool
            True if valid, False otherwise
        """
        if not self.selected_strategies:
            print("❌ No strategies selected")
            return False

        if not self.lot_sizes:
            print("❌ Lot sizes not configured")
            return False

        if len(self.selected_strategies) != len(self.lot_sizes):
            print("❌ Lot sizes not configured for all strategies")
            return False

        return True


def build_portfolio():
    """
    Main function to build dynamic portfolio.

    Returns
    -------
    dict
        Portfolio configuration
    """
    builder = PortfolioBuilder()

    # Select strategies
    if not builder.select_strategies():
        return None

    # Set lot sizes
    builder.set_lot_sizes()

    # Validate
    if not builder.validate_portfolio():
        return None

    # Display summary
    builder.display_portfolio_summary()

    # Get configuration
    return builder.get_portfolio_config()


if __name__ == "__main__":
    portfolio = build_portfolio()
    if portfolio:
        print("\n✅ Portfolio ready for backtest")
