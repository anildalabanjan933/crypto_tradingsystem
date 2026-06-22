import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional

# --- Import your strategy and indicator classes ---
# Adjust these import paths if your file structure is different
from indicators.pnf import PnFChartBuilder
from indicators.pnf_indicators import PnFIndicators
from strategies.pnf_bearish_variant_4b import PnFBearishVariant4B

# --- Configuration for the diagnostic ---
DIAGNOSTIC_CONFIG = {
    'box_size_percent': 0.15,
    'adx_threshold': 20.0,
    'sma_channel_percent': 3.0,
    'lot_size': 100,  # Dummy lot size for signal generation
    'data_file': 'data/btc_1h_delta.csv',  # Path to your 1H OHLCV data
    'start_date': '2025-06-08',  # Start date for data loading
    'end_date': '2026-06-08',  # End date for data loading
    'target_timeframe': '1H'  # Timeframe the strategy expects
}


# --- Helper function to load and prepare data ---
def load_and_prepare_data(file_path: str, start_date: str, end_date: str, target_timeframe: str) -> pd.DataFrame:
    print(f"Loading data from {file_path}...")

    # --- CRITICAL FIX: Explicitly define column names and reorder operations ---
    column_names = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    df = pd.read_csv(file_path, header=None, names=column_names)

    # Convert Unix timestamp to datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', errors='coerce')

    # Drop rows where timestamp conversion failed BEFORE setting index
    df.dropna(subset=['timestamp'], inplace=True)

    # Now set the datetime column as the index
    df.set_index('timestamp', inplace=True)
    # --- END CRITICAL FIX ---

    # Ensure the index is sorted
    df.sort_index(inplace=True)

    # Convert start_date and end_date strings to datetime objects for robust filtering
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    # Filter by date range using the datetime index
    df = df.loc[start_dt:end_dt]

    print(f"Loaded {len(df)} candles for {target_timeframe} from {start_dt} to {end_dt}")

    if len(df) == 0:
        print(f"WARNING: No data found for the specified date range {start_dt} to {end_dt}.")
        if not df.empty:
            print(f"         Actual data range in file: {df.index.min()} to {df.index.max()}")
        else:
            # Try to load the full range to see what's in the file
            full_df = pd.read_csv(file_path, header=None, names=column_names)
            full_df['timestamp'] = pd.to_datetime(full_df['timestamp'], unit='s', errors='coerce')
            full_df.dropna(subset=['timestamp'], inplace=True)
            full_df.set_index('timestamp', inplace=True)
            if not full_df.empty:
                print(f"         Full data range in file: {full_df.index.min()} to {full_df.index.max()}")
            else:
                print(f"         CSV file '{file_path}' appears to be empty or contains no valid timestamps.")

    return df


# --- Main diagnostic function ---
def run_pnf_diagnostic():
    print("======================================================")
    print("PnF STRATEGY DIAGNOSTIC TOOL")
    print("======================================================")

    # Load data
    data_df = load_and_prepare_data(
        DIAGNOSTIC_CONFIG['data_file'],
        DIAGNOSTIC_CONFIG['start_date'],
        DIAGNOSTIC_CONFIG['end_date'],
        DIAGNOSTIC_CONFIG['target_timeframe']
    )

    # Instantiate strategy
    # Note: BaseStrategy expects data_dict, lot_size, **kwargs
    # For diagnostic, we pass a dummy data_dict and lot_size
    strategy_instance = PnFBearishVariant4B(
        data_dict={'1H': data_df},  # Pass the 1H data in a dict as expected by BaseStrategy
        lot_size=DIAGNOSTIC_CONFIG['lot_size'],
        box_size_percent=DIAGNOSTIC_CONFIG['box_size_percent'],
        adx_threshold=DIAGNOSTIC_CONFIG['adx_threshold'],
        sma_channel_percent=DIAGNOSTIC_CONFIG['sma_channel_percent']
    )

    print("\n[Step 1] Building PnF Chart and Calculating Indicators...")
    # This part is usually done inside generate_signals, but we need access to columns and indicators
    # So we'll call them directly here for diagnostic purposes.
    strategy_instance.columns = strategy_instance.pnf_builder.build_pnf_chart(data_df)
    if len(strategy_instance.columns) < 20:
        print("Not enough PnF columns to calculate SMAs. Exiting diagnostic.")
        return

    strategy_instance.sma10_list = strategy_instance.indicators.calculate_sma10(strategy_instance.columns)
    strategy_instance.sma20_list = strategy_instance.indicators.calculate_sma20(strategy_instance.columns)
    strategy_instance.adx_list = strategy_instance.indicators.calculate_adx(strategy_instance.columns, period=14)
    print(f"Built {len(strategy_instance.columns)} PnF columns.")
    print(f"Calculated SMAs and ADX.")

    print("\n[Step 2] Tracing Strategy Logic (Column by Column)...")

    # --- Diagnostic State Variables ---
    in_position = False
    # in_trading_cycle = False # This local variable is redundant, use strategy_instance.in_trading_cycle directly
    entry_col_idx = None
    entry_price = None
    sl_price = None
    sl_activated = False
    sl_activation_col = None

    diagnostic_log = []

    for col_idx in range(len(strategy_instance.columns)):
        col = strategy_instance.columns[col_idx]
        current_sma10 = strategy_instance.sma10_list[col_idx]
        current_sma20 = strategy_instance.sma20_list[col_idx]
        current_adx = strategy_instance.adx_list[col_idx]
        current_price = col['end_level']

        log_entry = {
            'col_idx': col_idx,
            'timestamp': col['end_timestamp'],
            'type': col['type'],
            'price': current_price,
            'sma10': current_sma10,
            'sma20': current_sma20,
            'adx': current_adx,
            'in_position': in_position,
            'in_trading_cycle': strategy_instance.in_trading_cycle,  # Use strategy's state
            'event': 'NONE',
            'details': {}
        }

        # --- 1. HANDLE ACTIVE TRADE (EXIT LOGIC) ---
        if in_position:
            # Activate SL after next column closes
            if sl_activation_col is not None and col_idx >= sl_activation_col:  # >= to activate on the column after entry
                sl_activated = True

            exit_result = strategy_instance._check_exit_conditions(
                col_idx, entry_col_idx, entry_price, sl_price, sl_activated
            )

            if exit_result['exit_signal']:
                log_entry['event'] = 'EXIT'
                log_entry['details'] = {
                    'reason': exit_result['exit_reason'],
                    'exit_price': exit_result['exit_price'],
                    'entry_price': entry_price,
                    'sl_price': sl_price
                }

                in_position = False
                entry_col_idx = None
                entry_price = None
                sl_price = None
                sl_activated = False
                sl_activation_col = None

                # ===== RE-ENTRY STOP CONDITION (Ending the current trading cycle) =====
                # Bearish: If SMA10 >= SMA20, cycle ends
                if current_sma10 is not None and current_sma20 is not None and current_sma10 >= current_sma20:
                    strategy_instance.in_trading_cycle = False  # Update strategy's internal state
                    log_entry['details']['cycle_ended'] = True
                else:
                    log_entry['details']['cycle_continues'] = True

        # --- 2. HANDLE NEW ENTRY (FIRST ENTRY or RE-ENTRY) ---
        if not in_position:
            # --- CHECK FOR NEW FIRST ENTRY (if not in a cycle) ---
            if not strategy_instance.in_trading_cycle:  # Use strategy's state
                entry_result = strategy_instance._check_first_entry_conditions(col_idx)
                if entry_result['entry_signal']:
                    sl_price_calc = strategy_instance._calculate_sl(col_idx)

                    log_entry['event'] = 'FIRST_ENTRY'
                    log_entry['details'] = {
                        'entry_price': entry_result['price'],
                        'sl_calculated': sl_price_calc,
                        'conditions_met': strategy_instance._check_first_entry_conditions(col_idx)
                        # Re-run to get full details
                    }

                    in_position = True
                    entry_col_idx = col_idx
                    entry_price = entry_result['price']
                    sl_price = sl_price_calc
                    sl_activation_col = col_idx + 1  # SL activates after next column
                    strategy_instance.in_trading_cycle = True  # Start new cycle

            # --- CHECK FOR RE-ENTRY (if in a cycle) ---
            elif strategy_instance.in_trading_cycle:  # Means we are in a cycle, looking for re-entries
                # --- Bearish re-entry CONTINUATION condition: SMA10 < SMA20 ---
                if current_sma10 is not None and current_sma20 is not None and current_sma10 < current_sma20:
                    entry_result = strategy_instance._check_re_entry_conditions(col_idx)
                    if entry_result['entry_signal']:
                        sl_price_calc = strategy_instance._calculate_sl(col_idx)

                        log_entry['event'] = 'RE_ENTRY'
                        log_entry['details'] = {
                            'entry_price': entry_result['price'],
                            'sl_calculated': sl_price_calc,
                            'conditions_met': strategy_instance._check_re_entry_conditions(col_idx)
                            # Re-run to get full details
                        }

                        in_position = True
                        entry_col_idx = col_idx
                        entry_price = entry_result['price']
                        sl_price = sl_price_calc
                        sl_activation_col = col_idx + 1  # SL activates after next column
                else:
                    # Log why re-entry didn't happen (SMA condition not met)
                    log_entry['event'] = 'RE_ENTRY_BLOCKED'
                    log_entry['details'] = {'reason': 'SMA10 >= SMA20'}

        diagnostic_log.append(log_entry)

    # --- Print Diagnostic Log ---
    print("\n[Step 3] Diagnostic Log Output:")
    for entry in diagnostic_log:
        # Only print entries where something significant happened or state changed
        if entry['event'] != 'NONE' or entry['in_position'] != (
        diagnostic_log[entry['col_idx'] - 1]['in_position'] if entry['col_idx'] > 0 else False) or entry[
            'in_trading_cycle'] != (
        diagnostic_log[entry['col_idx'] - 1]['in_trading_cycle'] if entry['col_idx'] > 0 else False):
            print(f"\n--- Col {entry['col_idx']} @ {entry['timestamp']} ({entry['type']} {entry['price']}) ---")
            # Handle None values for indicators gracefully
            sma10_str = f"{entry['sma10']:.2f}" if entry['sma10'] is not None else "None"
            sma20_str = f"{entry['sma20']:.2f}" if entry['sma20'] is not None else "None"
            adx_str = f"{entry['adx']:.2f}" if entry['adx'] is not None else "None"
            print(f"  SMA10: {sma10_str}, SMA20: {sma20_str}, ADX: {adx_str}")
            print(f"  in_position: {entry['in_position']}, in_trading_cycle: {entry['in_trading_cycle']}")
            print(f"  Event: {entry['event']}")
            if entry['details']:
                for k, v in entry['details'].items():
                    if k == 'conditions_met' and isinstance(v, dict):
                        print(f"    Conditions:")
                        for cond_k, cond_v in v.items():
                            if cond_k != 'price':  # Avoid re-printing price
                                print(f"      - {cond_k}: {cond_v}")
                    else:
                        print(f"    {k}: {v}")


if __name__ == "__main__":
    run_pnf_diagnostic()
