# engine/backtest_engine.py
# Responsibility: Universal backtest engine - orchestrates entire backtest process

from data.data_loader import DataLoader
from data.data_aggregator import DataAggregator
from engine.trade_builder import TradeBuilder
from engine.metrics_calculator import MetricsCalculator
from engine.margin_calculator import MarginCalculator
from config.charges_config import charges_config
from config.backtest_config import backtest_config
from strategies.base_strategy import BaseStrategy
from config.margin_config import margin_config


class BacktestEngine:
    """
    Universal backtest engine.
    Orchestrates entire backtest process for any strategy.
    """

    def __init__(self, strategy_class, symbol, lot_size, start_date, end_date,
                 csv_path, strategy_params=None):
        self.strategy_class  = strategy_class
        self.symbol          = symbol
        self.lot_size        = lot_size
        self.start_date      = start_date
        self.end_date        = end_date
        self.csv_path        = csv_path
        self.strategy_params = strategy_params if strategy_params is not None else {}

        self.data_1m  = None
        self.data_dict = {}
        self.strategy  = None
        self.signals   = []
        self.trades    = []
        self.metrics   = {}

        self.initial_capital = backtest_config.get("initial_capital_usd", 100000)

    def run(self):
        """Run complete backtest."""
        print("=" * 70)
        print(f"BACKTEST ENGINE - {self.symbol}")
        print("=" * 70)

        print("\n[Step 1] Loading data...")
        self._load_data()

        print("\n[Step 2] Aggregating timeframes...")
        self._aggregate_timeframes()

        print("\n[Step 3] Instantiating strategy...")
        self._instantiate_strategy()

        print("\n[Step 4] Generating signals...")
        self._generate_signals()

        print("\n[Step 5] Building trades...")
        self._build_trades()

        print("\n[Step 6] Calculating metrics...")
        self._calculate_metrics()

        print("\n✅ Backtest complete!")
        print("=" * 70)

        return {
            'trades'   : self.trades,
            'metrics'  : self.metrics,
            'signals'  : self.signals,
            'data_dict': self.data_dict,
        }

    def _load_data(self):
        """Load 1M data from CSV."""
        loader       = DataLoader(self.csv_path)
        self.data_1m = loader.load_data()

        if self.data_1m is None:
            raise ValueError("Failed to load data from CSV")

        loader.validate_format()
        self.data_1m = loader.filter_by_date_range(self.start_date, self.end_date)

        if self.data_1m is None or len(self.data_1m) == 0:
            raise ValueError("No data available for specified date range")

        loader.validate_data_continuity()

    def _aggregate_timeframes(self):
        """
        Aggregate 1M data to ALL standard timeframes.
        Strategy picks what it needs from data_dict internally.
        Avoids accessing @property on uninstantiated class.
        """
        aggregator = DataAggregator(self.data_1m)

        # Always aggregate all standard timeframes
        # Strategy will use whichever it needs via self.data_dict.get(tf)
        timeframe_map = {
            '1M'   : aggregator.get_1m_data,
            '5M'   : aggregator.get_5m_data,
            '15M'  : aggregator.get_15m_data,
            '30M'  : aggregator.get_30m_data,
            '1H'   : aggregator.get_1h_data,
            '4H'   : aggregator.get_4h_data,
            'Daily': aggregator.get_daily_data,
        }

        for tf, getter in timeframe_map.items():
            try:
                data = getter()
                if data is not None and len(data) > 0:
                    self.data_dict[tf] = data
                    print(f"✅ Aggregated to {tf}: {len(data)} candles")
                    aggregator.validate_continuity(data, tf)
                else:
                    print(f"⚠️  {tf}: No data available")
            except Exception as e:
                print(f"⚠️  {tf}: Aggregation failed — {e}")

    def _instantiate_strategy(self):
        """Instantiate strategy with data_dict and params."""
        self.strategy = self.strategy_class(
            self.data_dict, self.lot_size, **self.strategy_params
        )
        print(f"✅ Strategy instantiated: {self.strategy_class.__name__} "
              f"with params {self.strategy_params}")

    def _generate_signals(self):
        """
        Generate signals from strategy.
        Strategy reads all data from self.data_dict internally.
        No data passed as argument — strategy manages its own timeframe selection.
        """
        self.signals = self.strategy.generate_signals()
        print(f"✅ Generated {len(self.signals)} signals")

    def _build_trades(self):
        """Build trades from signals."""
        builder = TradeBuilder(
            size_qty       = self.lot_size,
            initial_capital= self.initial_capital,
            charges_config = charges_config,
            margin_config  = margin_config,
        )
        self.trades = builder.build_trades(self.signals)
        print(f"✅ Built {len(self.trades)} trades")

    def _calculate_metrics(self):
        """Calculate backtest metrics."""
        calculator = MetricsCalculator(
            trades         = self.trades,
            initial_capital= self.initial_capital,
        )
        self.metrics = calculator.calculate_all_metrics()
        print(f"✅ Calculated metrics")


def run_backtest(strategy_class, symbol, lot_size, start_date, end_date,
                 csv_path, strategy_params=None):
    """Main function to run backtest."""
    engine = BacktestEngine(
        strategy_class, symbol, lot_size,
        start_date, end_date, csv_path, strategy_params
    )
    return engine.run()
