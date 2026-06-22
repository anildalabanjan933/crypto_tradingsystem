"""
PnF Backtest Engine V2
Complete backtest with re-entry support
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
from indicators.pnf import PnFChartBuilder
from indicators.pnf_indicators import PnFIndicators
from strategies.pnf_bearish_variant_4b import PnFBearishVariant4BTest
from engine.pnf_trade_tracker import PnFTradeTracker


class PnFBacktestEngineV2:
    """
    Complete PnF backtest engine with:
    - PnF chart building
    - All PnF-based indicators
    - Entry/exit signal generation
    - Trade tracking with re-entry
    - Performance statistics
    """

    def __init__(self, data_file: str, strategy_type: str = 'bearish',
                 box_size_percent: float = 0.15,
                 adx_threshold: float = 20.0,
                 sma_channel_percent: float = 3.0):
        """
        Initialize backtest engine.

        Args:
            data_file: Path to 1H OHLCV CSV file
            strategy_type: 'bearish' or 'bullish'
            box_size_percent: PnF box size as %
            adx_threshold: ADX threshold
            sma_channel_percent: SMA channel width %
        """
        self.data_file = data_file
        self.strategy_type = strategy_type
        self.box_size_percent = box_size_percent
        self.adx_threshold = adx_threshold
        self.sma_channel_percent = sma_channel_percent

        # Components
        self.pnf_builder = PnFChartBuilder(box_size_percent, reverse_boxes=3)
        self.indicators = PnFIndicators(box_size_percent)
        self.strategy = PnFBearishVariant4BTest(box_size_percent, adx_threshold, sma_channel_percent)
        self.tracker = PnFTradeTracker()

        # Data
        self.df = None
        self.columns = []
        self.sma10_list = []
        self.sma20_list = []
        self.adx_list = []
        self.signals = []

    def load_data(self) -> pd.DataFrame:
        """Load 1H OHLCV data."""
        print(f"Loading data from {self.data_file}...")
        self.df = pd.read_csv(self.data_file, parse_dates=['timestamp'])
        self.df.set_index('timestamp', inplace=True)
        self.df.columns = self.df.columns.str.lower()
        print(f"Loaded {len(self.df)} candles")
        print(f"Date range: {self.df.index[0]} to {self.df.index[-1]}")
        return self.df

    def build_pnf_chart(self):
        """Build PnF chart from all data."""
        print("\nBuilding PnF chart...")
        self.columns = self.pnf_builder.build_pnf_chart(self.df)
        print(f"Built {len(self.columns)} PnF columns")

    def calculate_indicators(self):
        """Calculate all PnF-based indicators."""
        print("\nCalculating indicators...")

        self.sma10_list = self.indicators.calculate_sma10(self.columns)
        self.sma20_list = self.indicators.calculate_sma20(self.columns)
        self.adx_list = self.indicators.calculate_adx(self.columns, period=14)

        print(f"SMA10 values: {len([x for x in self.sma10_list if x is not None])}")
        print(f"SMA20 values: {len([x for x in self.sma20_list if x is not None])}")
        print(f"ADX values: {len([x for x in self.adx_list if x is not None])}")

    def generate_signals(self):
        """Generate entry and exit signals."""
        print("\nGenerating signals...")

        self.signals = self.strategy.generate_signals(
            self.columns, self.sma10_list, self.sma20_list, self.adx_list
        )

        entries = [s for s in self.signals if s['type'] == 'ENTRY']
        exits = [s for s in self.signals if s['type'] == 'EXIT']

        print(f"Total signals: {len(self.signals)}")
        print(f"Entry signals: {len(entries)}")
        print(f"Exit signals: {len(exits)}")

    def run_backtest(self) -> Dict:
        """
        Run complete backtest.

        Returns:
            Backtest results dictionary
        """
        print("\n" + "=" * 80)
        print("PnF BACKTEST ENGINE V2")
        print("=" * 80)

        # Step 1: Load data
        self.load_data()

        # Step 2: Build PnF chart
        self.build_pnf_chart()

        # Step 3: Calculate indicators
        self.calculate_indicators()

        # Step 4: Generate signals
        self.generate_signals()

        # Step 5: Get statistics
        stats = self.tracker.get_trade_stats()

        print("\n" + "=" * 80)
        print("BACKTEST RESULTS")
        print("=" * 80)
        print(f"Total Trades: {stats['total_trades']}")
        print(f"Winning Trades: {stats['winning_trades']}")
        print(f"Losing Trades: {stats['losing_trades']}")
        print(f"Win Rate: {stats['win_rate']:.2f}%")
        print(f"Total PnL: {stats['total_pnl']:.2f}")
        print(f"Avg PnL: {stats['avg_pnl']:.2f}")
        print(f"Max Win: {stats['max_win']:.2f}")
        print(f"Max Loss: {stats['max_loss']:.2f}")
        print("=" * 80)

        return {
            'columns': self.columns,
            'sma10': self.sma10_list,
            'sma20': self.sma20_list,
            'adx': self.adx_list,
            'signals': self.signals,
            'trades': self.tracker.closed_trades,
            'stats': stats,
        }

    def export_results(self, output_dir: str = 'output'):
        """Export backtest results to CSV."""
        import os

        os.makedirs(output_dir, exist_ok=True)

        # Export trades
        trades_df = self.tracker.to_dataframe()
        trades_df.to_csv(f'{output_dir}/pnf_trades.csv', index=False)
        print(f"\nTrades exported to {output_dir}/pnf_trades.csv")

        # Export signals
        signals_df = pd.DataFrame(self.signals)
        signals_df.to_csv(f'{output_dir}/pnf_signals.csv', index=False)
        print(f"Signals exported to {output_dir}/pnf_signals.csv")

        # Export columns
        columns_df = pd.DataFrame(self.columns)
        columns_df.to_csv(f'{output_dir}/pnf_columns.csv', index=False)
        print(f"Columns exported to {output_dir}/pnf_columns.csv")


# Main execution
if __name__ == "__main__":
    engine = PnFBacktestEngineV2(
        data_file='data/btc_1h_delta.csv',
        strategy_type='bearish',
        box_size_percent=0.15,
        adx_threshold=20.0,
        sma_channel_percent=3.0
    )

    results = engine.run_backtest()
    engine.export_results()
