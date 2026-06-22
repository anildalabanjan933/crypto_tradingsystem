"""
PnF Diagnostic Tool
Analyzes PnF strategy signals and generates detailed diagnostic report
"""

import pandas as pd
import numpy as np
from indicators.pnf import PnFChartBuilder
import csv
from datetime import datetime


class PnFDiagnostic:
    """
    Diagnostic tool for PnF strategy analysis.
    Generates detailed CSV report showing all indicators and entry conditions for each PnF column.
    """

    def __init__(self, data_file, strategy_type='bearish', sma_channel_percent=3, adx_threshold=20):
        """
        Initialize diagnostic tool

        Args:
            data_file: Path to 1H OHLCV data CSV file
            strategy_type: 'bearish' or 'bullish'
            sma_channel_percent: SMA channel percentage (default 3%)
            adx_threshold: ADX threshold (default 20)
        """
        self.data_file = data_file
        self.strategy_type = strategy_type
        self.sma_channel_percent = sma_channel_percent
        self.adx_threshold = adx_threshold

        self.pnf_builder = PnFChartBuilder(box_size_percent=0.15, reverse_boxes=3)
        self.df = None
        self.columns = []
        self.sma10 = []
        self.sma20 = []
        self.adx = []
        self.last_trade_closed_timestamp = None  # <--- ADDED: Flag for re-entry logic in diagnostic

    def load_data(self):
        """Load 1H OHLCV data"""
        print(f"Loading data from {self.data_file}...")
        self.df = pd.read_csv(self.data_file, parse_dates=['timestamp'])
        self.df.set_index('timestamp', inplace=True)
        self.df.columns = self.df.columns.str.lower()
        print(f"Loaded {len(self.df)} candles")
        print(f"Date range: {self.df.index[0]} to {self.df.index[-1]}")

    def build_pnf_chart(self):
        """Build PnF chart from data"""
        print("\nBuilding PnF chart...")
        self.columns = self.pnf_builder.build_pnf_chart(self.df)
        print(f"Built {len(self.columns)} PnF columns")

    def calculate_indicators(self):
        """Calculate all indicators"""
        print("\nCalculating indicators...")
        self.sma10 = self.pnf_builder.calculate_sma(10)
        self.sma20 = self.pnf_builder.calculate_sma(20)
        self.adx = self.pnf_builder.calculate_adx(14)
        print(f"SMA10 values: {len(self.sma10)}")
        print(f"SMA20 values: {len(self.sma20)}")
        print(f"ADX values: {len(self.adx)}")

    def check_entry_conditions(self, col_idx) -> dict:  # <--- ADDED return type hint
        """
        Check all entry conditions for a specific column

        Returns:
            Dictionary with all condition results
        """
        if col_idx < 2:
            return None

        current_columns_slice = self.columns[:col_idx + 1]
        col = self.columns[col_idx]
        current_price = col['end_level']
        current_timestamp = col['end_timestamp']  # <--- ADDED: current_timestamp

        sma10_val = self.sma10[col_idx] if col_idx < len(self.sma10) else None
        sma20_val = self.sma20[col_idx] if col_idx < len(self.sma20) else None
        adx_val = self.adx[col_idx] if col_idx < len(self.adx) else None

        conditions = {
            'column_idx': col_idx,
            'column_type': col['type'],
            'column_end_level': current_price,
            'column_timestamp': str(col['end_timestamp']),
            'sma10': sma10_val,
            'sma20': sma20_val,
            'adx': adx_val,
        }

        # --- CRITICAL ADX CHECK ---
        # If ADX is None, no entry signal can be generated
        if adx_val is None:
            conditions['adx_check'] = False
            conditions['sma_check'] = False  # Default to False if ADX is None
            conditions['trendline_break'] = False
            conditions['higher_high'] = False
            conditions['lower_low'] = False
            conditions['trendline_or_higher_high'] = False
            conditions['trendline_or_lower_low'] = False
            conditions['pattern_detected'] = False
            conditions['entry_signal'] = False
            return conditions
        # --- END CRITICAL ADX CHECK ---

        # Condition 2: ADX > 20 (REQUIRED - not optional)
        adx_check = adx_val > self.adx_threshold
        conditions['adx_check'] = adx_check
        if not adx_check:
            conditions['sma_check'] = False
            conditions['trendline_break'] = False
            conditions['higher_high'] = False
            conditions['lower_low'] = False
            conditions['trendline_or_higher_high'] = False
            conditions['trendline_or_lower_low'] = False
            conditions['pattern_detected'] = False
            conditions['entry_signal'] = False
            return conditions

        # Condition 3: Price within ±3% of SMA10 or SMA20 (MODIFIED FOR RE-ENTRY)
        sma_check = False

        # Determine if it's a re-entry (simplified for diagnostic)
        # For diagnostic, we assume it's a re-entry if a trade was closed recently
        # This is a simplified representation for the diagnostic tool
        is_re_entry = False
        # In a real backtest, self.last_trade_closed_timestamp would be set by an exit.
        # For diagnostic, we can't easily simulate this state.
        # So, for diagnostic, let's assume strict SMA check always, or add a parameter.
        # For now, let's keep it strict in diagnostic to see all conditions.

        # Strict SMA check for initial entry (and for diagnostic simplicity)
        if sma10_val is not None:
            sma10_upper = sma10_val * (1 + self.sma_channel_percent / 100)
            sma10_lower = sma10_val * (1 - self.sma_channel_percent / 100)
            if sma10_lower <= current_price <= sma10_upper:
                sma_check = True

        if not sma_check and sma20_val is not None:
            sma20_upper = sma20_val * (1 + self.sma_channel_percent / 100)
            sma20_lower = sma20_val * (1 - self.sma_channel_percent / 100)
            if sma20_lower <= current_price <= sma20_upper:
                sma_check = True

        conditions['sma_check'] = sma_check
        if not sma_check:
            conditions['trendline_break'] = False
            conditions['higher_high'] = False
            conditions['lower_low'] = False
            conditions['trendline_or_higher_high'] = False
            conditions['trendline_or_lower_low'] = False
            conditions['pattern_detected'] = False
            conditions['entry_signal'] = False
            return conditions

        # Strategy-specific conditions
        if self.strategy_type == 'bearish':
            trendline_break = self.pnf_builder.detect_bullish_trendline(current_columns_slice)
            higher_high = self.pnf_builder.detect_higher_high(current_columns_slice)
            double_bottom, _ = self.pnf_builder.detect_double_bottom(current_columns_slice)

            conditions['trendline_break'] = trendline_break
            conditions['higher_high'] = higher_high
            conditions['trendline_or_higher_high'] = trendline_break or higher_high
            conditions['pattern_detected'] = double_bottom
            conditions['pattern_name'] = 'Double Bottom'

            # Overall entry signal
            entry_signal = conditions['trendline_or_higher_high'] and conditions['adx_check'] and conditions[
                'sma_check'] and double_bottom
            conditions['entry_signal'] = entry_signal

        else:  # bullish
            trendline_break = self.pnf_builder.detect_bearish_trendline(current_columns_slice)
            lower_low = self.pnf_builder.detect_lower_low(current_columns_slice)
            double_top, _ = self.pnf_builder.detect_double_top(current_columns_slice)

            conditions['trendline_break'] = trendline_break
            conditions['lower_low'] = lower_low
            conditions['trendline_or_lower_low'] = trendline_break or lower_low
            conditions['pattern_detected'] = double_top
            conditions['pattern_name'] = 'Double Top'

            # Overall entry signal
            entry_signal = conditions['trendline_or_lower_low'] and conditions['adx_check'] and conditions[
                'sma_check'] and double_top
            conditions['entry_signal'] = entry_signal

        return conditions

    def generate_diagnostic_report(self, output_file='diagnostic_report.csv'):
        """
        Generate detailed diagnostic report

        Args:
            output_file: Output CSV file name
        """
        print(f"\nGenerating diagnostic report: {output_file}...")

        rows = []
        entry_count = 0

        # Initialize last_trade_closed_timestamp for diagnostic's internal use
        # This is a simplified simulation for the diagnostic tool
        self.last_trade_closed_timestamp = None

        for col_idx in range(len(self.columns)):
            conditions = self.check_entry_conditions(col_idx)

            if conditions is None:
                continue

            row = {
                'Column_Index': conditions['column_idx'],
                'Column_Type': conditions['column_type'],
                'Column_End_Level': f"{conditions['column_end_level']:.2f}",
                'Timestamp': conditions['column_timestamp'],
                'SMA10': f"{conditions['sma10']:.2f}" if conditions['sma10'] else 'None',
                'SMA20': f"{conditions['sma20']:.2f}" if conditions['sma20'] else 'None',
                'ADX': f"{conditions['adx']:.2f}" if conditions['adx'] else 'None',
                'ADX_Check': conditions['adx_check'],
                'SMA_Check': conditions['sma_check'],
            }

            if self.strategy_type == 'bearish':
                row['Trendline_Break'] = conditions['trendline_break']
                row['Higher_High'] = conditions['higher_high']
                row['Trendline_or_HigherHigh'] = conditions['trendline_or_higher_high']  # <--- Corrected
                row['Double_Bottom'] = conditions['pattern_detected']
                row['Entry_Signal'] = conditions['entry_signal']
            else:
                row['Trendline_Break'] = conditions['trendline_break']
                row['Lower_Low'] = conditions['lower_low']
                row['Trendline_or_LowerLow'] = conditions['trendline_or_lower_low']  # <--- Corrected
                row['Double_Top'] = conditions['pattern_detected']
                row['Entry_Signal'] = conditions['entry_signal']

            rows.append(row)

            if conditions['entry_signal']:
                entry_count += 1
                print(
                    f"  Entry Signal #{entry_count} at {conditions['column_timestamp']} (Price: {conditions['column_end_level']:.2f})")
                # Simulate an entry, so next signal might be a re-entry
                # For diagnostic, we don't track exits, so this is a simplification
                # In a real backtest, last_trade_closed_timestamp would be set by an exit.
                # For diagnostic, we'll just reset it after an entry to simulate a new cycle.
                self.last_trade_closed_timestamp = conditions['column_timestamp']  # <--- Simplified for diagnostic

        # Write to CSV
        if rows:
            keys = rows[0].keys()
            with open(output_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(rows)

            print(f"\nDiagnostic report saved to {output_file}")
            print(f"Total columns analyzed: {len(rows)}")
            print(f"Total entry signals: {entry_count}")
        else:
            print("No data to write")

    def run(self, output_file='diagnostic_report.csv'):
        """Run complete diagnostic analysis"""
        print("=" * 80)
        print("PnF DIAGNOSTIC ANALYSIS")
        print("=" * 80)

        self.load_data()
        self.build_pnf_chart()
        self.calculate_indicators()
        self.generate_diagnostic_report(output_file)

        print("\n" + "=" * 80)
        print("DIAGNOSTIC ANALYSIS COMPLETE")
        print("=" * 80)


# Main execution
if __name__ == "__main__":
    import sys

    # Example usage
    strategy_type = sys.argv[1] if len(sys.argv) > 1 else 'bearish'
    data_file = sys.argv[2] if len(sys.argv) > 2 else 'data/btc_1h_delta.csv'
    output_file = sys.argv[3] if len(sys.argv) > 3 else f'diagnostic_report_{strategy_type}.csv'

    diagnostic = PnFDiagnostic(
        data_file=data_file,
        strategy_type=strategy_type,
        sma_channel_percent=3,
        adx_threshold=20
    )

    diagnostic.run(output_file)
