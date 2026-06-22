# engine/portfolio_aggregator.py
# Responsibility: Aggregate trades from multiple strategies

import pandas as pd
from engine.metrics_calculator import MetricsCalculator


class PortfolioAggregator:
    """
    Aggregates trades from multiple strategies into portfolio.
    """

    def __init__(self, initial_capital=100000):
        """
        Initialize PortfolioAggregator.

        Parameters
        ----------
        initial_capital : float
            Total portfolio capital
        """
        self.initial_capital = initial_capital
        self.all_trades = []
        self.combined_metrics = {}

    def aggregate_trades(self, trade_lists):
        """
        Aggregate trades from multiple strategies.

        Parameters
        ----------
        trade_lists : list of list
            List of trade lists from each strategy

        Returns
        -------
        list
            Combined trade list sorted by datetime
        """
        # Flatten all trades
        self.all_trades = []
        for trades in trade_lists:
            self.all_trades.extend(trades)

        # Sort by exit datetime
        df_all = pd.DataFrame(self.all_trades)
        df_all['exit_datetime'] = pd.to_datetime(df_all['exit_datetime'])
        df_all = df_all.sort_values('exit_datetime')

        self.all_trades = df_all.to_dict('records')

        print(f"✅ Aggregated {len(self.all_trades)} trades from multiple strategies")
        return self.all_trades

    def calculate_portfolio_metrics(self):
        """
        Calculate combined portfolio metrics.

        Returns
        -------
        dict
            Portfolio metrics
        """
        calculator = MetricsCalculator(self.all_trades, self.initial_capital)
        self.combined_metrics = calculator.calculate_all_metrics()
        return self.combined_metrics
