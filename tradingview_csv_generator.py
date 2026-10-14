# tradingview_csv_generator.py
# Responsibility: Generate TradingView-compatible trade log CSV from completed trade records.
# Receives a list of trade records from trade_builder.py and writes them to a CSV file
# in the exact TradingView column order required for AlgoTest import.

import csv
import os
from utils import format_date, round_price, round_percent

# ─────────────────────────────────────────────
# SECTION 1: CSV SCHEMA DEFINITION
# Exact 15-column TradingView trade log format.
# Column order is mandatory. Do not change.
# ─────────────────────────────────────────────

TV_COLUMNS = [
    "Trade number",
    "Type",
    "Date and time",
    "Signal",
    "Price",
    "Size (qty)",
    "Size (value)",
    "Net PnL",
    "Net PnL %",
    "Favorable excursion",
    "Favorable excursion %",
    "Adverse excursion",
    "Adverse excursion %",
    "Cumulative PnL",
    "Cumulative PnL %",
]

# ─────────────────────────────────────────────
# SECTION 2: VALID FIELD VALUES
# These are the only accepted values for Type and Signal fields.
# Any other value will cause AlgoTest to misread the trade.
# ─────────────────────────────────────────────

VALID_TYPES = {
    "Entry long",
    "Exit long",
    "Entry short",
    "Exit short",
}

VALID_SIGNALS = {
    "Buy",  # Entry long signal
    "Sell",  # Exit long signal
    "Short",  # Entry short signal
    "Cover",  # Exit short signal
}

# Maps Type to its expected Signal value.
# Used during row validation to catch mismatches.
TYPE_TO_SIGNAL = {
    "Entry long": "Buy",
    "Exit long": "Sell",
    "Entry short": "Short",
    "Exit short": "Cover",
}

# ─────────────────────────────────────────────
# SECTION 3: ROW ORDER RULE
# For each trade number, the Exit row must appear
# before the Entry row in the CSV output.
# This matches the TradingView standard confirmed
# from the reference file (200+ trade data block).
#
# Correct order:
#   1,Exit long,  ...
#   1,Entry long, ...
#
# Incorrect order (do not use):
#   1,Entry long, ...
#   1,Exit long,  ...
# ─────────────────────────────────────────────

ROW_ORDER = ["Exit long", "Exit short", "Entry long", "Entry short"]

# ─────────────────────────────────────────────
# SECTION 4: TRADE RECORD SCHEMA
# Each trade record passed to the generator must
# be a dict with the following keys and types.
#
# trade_number         : int
# entry_type           : str  — "Entry long" or "Entry short"
# exit_type            : str  — "Exit long" or "Exit short"
# entry_datetime       : str  — "YYYY-MM-DD HH:MM"
# exit_datetime        : str  — "YYYY-MM-DD HH:MM"
# entry_signal         : str  — "Buy" or "Short"
# exit_signal          : str  — "Sell" or "Cover"
# entry_price          : float
# exit_price           : float
# size_qty             : int
# size_value           : float
# net_pnl              : float
# net_pnl_pct          : float  — 2 decimal places
# favorable_excursion  : float
# favorable_excursion_pct : float  — 2 decimal places
# adverse_excursion    : float
# adverse_excursion_pct   : float  — 2 decimal places
# cumulative_pnl       : float
# cumulative_pnl_pct   : float  — 2 decimal places
# ─────────────────────────────────────────────

REQUIRED_TRADE_KEYS = [
    "trade_number",
    "entry_type",
    "exit_type",
    "entry_datetime",
    "exit_datetime",
    "entry_signal",
    "exit_signal",
    "entry_price",
    "exit_price",
    "size_qty",
    "size_value",
    "net_pnl",
    "net_pnl_pct",
    "favorable_excursion",
    "favorable_excursion_pct",
    "adverse_excursion",
    "adverse_excursion_pct",
    "cumulative_pnl",
    "cumulative_pnl_pct",
]


# ─────────────────────────────────────────────
# SECTION 5: HEADER VALIDATION
# Validates that TV_COLUMNS matches the exact
# TradingView 15-column header. Called once at
# startup. Raises immediately if schema drifts.
# ─────────────────────────────────────────────

def validate_header():
    """
    Validates the TV_COLUMNS list against the
    expected TradingView header definition.
    Raises ValueError if column count or any
    column name does not match exactly.
    """
    expected = [
        "Trade number",
        "Type",
        "Date and time",
        "Signal",
        "Price",
        "Size (qty)",
        "Size (value)",
        "Net PnL",
        "Net PnL %",
        "Favorable excursion",
        "Favorable excursion %",
        "Adverse excursion",
        "Adverse excursion %",
        "Cumulative PnL",
        "Cumulative PnL %",
    ]

    if len(TV_COLUMNS) != len(expected):
        raise ValueError(
            f"Column count mismatch. "
            f"Expected {len(expected)}, got {len(TV_COLUMNS)}."
        )

    for i, (actual, exp) in enumerate(zip(TV_COLUMNS, expected)):
        if actual != exp:
            raise ValueError(
                f"Column mismatch at position {i}. "
                f"Expected '{exp}', got '{actual}'."
            )


# ─────────────────────────────────────────────
# SECTION 6: ROW VALIDATION
# Validates a single trade record dict before
# writing to CSV. Checks all required keys,
# valid Type and Signal values, Type-to-Signal
# mapping, and date format.
# ─────────────────────────────────────────────

def validate_trade_record(record):
    """
    Validates a single trade record dict.
    Raises ValueError with a descriptive message
    on the first validation failure found.

    Parameters
    ----------
    record : dict
        A completed trade record from trade_builder.py.
    """
    trade_num = record.get("trade_number", "UNKNOWN")

    # Check all required keys are present
    for key in REQUIRED_TRADE_KEYS:
        if key not in record:
            raise ValueError(
                f"Trade {trade_num}: Missing required field '{key}'."
            )

    # Validate entry_type
    if record["entry_type"] not in VALID_TYPES:
        raise ValueError(
            f"Trade {trade_num}: Invalid entry_type '{record['entry_type']}'. "
            f"Must be one of {sorted(VALID_TYPES)}."
        )

    # Validate exit_type
    if record["exit_type"] not in VALID_TYPES:
        raise ValueError(
            f"Trade {trade_num}: Invalid exit_type '{record['exit_type']}'. "
            f"Must be one of {sorted(VALID_TYPES)}."
        )

    # Validate entry_signal
    if record["entry_signal"] not in VALID_SIGNALS:
        raise ValueError(
            f"Trade {trade_num}: Invalid entry_signal '{record['entry_signal']}'. "
            f"Must be one of {sorted(VALID_SIGNALS)}."
        )

    # Validate exit_signal
    if record["exit_signal"] not in VALID_SIGNALS:
        raise ValueError(
            f"Trade {trade_num}: Invalid exit_signal '{record['exit_signal']}'. "
            f"Must be one of {sorted(VALID_SIGNALS)}."
        )

    # Validate Type-to-Signal mapping for entry
    expected_entry_signal = TYPE_TO_SIGNAL.get(record["entry_type"])
    if record["entry_signal"] != expected_entry_signal:
        raise ValueError(
            f"Trade {trade_num}: entry_signal '{record['entry_signal']}' "
            f"does not match entry_type '{record['entry_type']}'. "
            f"Expected signal: '{expected_entry_signal}'."
        )

    # Validate Type-to-Signal mapping for exit
    expected_exit_signal = TYPE_TO_SIGNAL.get(record["exit_type"])
    if record["exit_signal"] != expected_exit_signal:
        raise ValueError(
            f"Trade {trade_num}: exit_signal '{record['exit_signal']}' "
            f"does not match exit_type '{record['exit_type']}'. "
            f"Expected signal: '{expected_exit_signal}'."
        )

    # Validate date format for entry
    _validate_date_format(record["entry_datetime"], trade_num, "entry_datetime")

    # Validate date format for exit
    _validate_date_format(record["exit_datetime"], trade_num, "exit_datetime")

    # Validate size_qty is a positive integer
    if not isinstance(record["size_qty"], int) or record["size_qty"] <= 0:
        raise ValueError(
            f"Trade {trade_num}: size_qty must be a positive integer. "
            f"Got '{record['size_qty']}'."
        )


def _validate_date_format(date_str, trade_num, field_name):
    """
    Validates that a date string matches YYYY-MM-DD HH:MM format exactly.
    Raises ValueError if format does not match.

    Parameters
    ----------
    date_str   : str   — The date string to validate.
    trade_num  : int   — Trade number for error reporting.
    field_name : str   — Field name for error reporting.
    """
    from datetime import datetime
    try:
        datetime.strptime(date_str, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError(
            f"Trade {trade_num}: Invalid date format in '{field_name}': "
            f"'{date_str}'. Required format: YYYY-MM-DD HH:MM."
        )


# ─────────────────────────────────────────────
# SECTION 7: CSV FORMAT VALIDATION
# Validates a completed list of trade records
# before writing. Checks row count, trade number
# sequence, and Exit-before-Entry row order.
# ─────────────────────────────────────────────

def validate_trade_list(trade_records):
    """
    Validates the full list of trade records before
    writing to CSV.

    Checks:
    - List is not empty.
    - Trade numbers are sequential starting from 1.
    - No duplicate trade numbers.

    Parameters
    ----------
    trade_records : list of dict
        All completed trade records from trade_builder.py.

    Raises
    ------
    ValueError if any validation check fails.
    """
    if not trade_records:
        raise ValueError("Trade record list is empty. Nothing to write.")

    seen_numbers = []
    for record in trade_records:
        num = record.get("trade_number")
        if num is None:
            raise ValueError("A trade record is missing 'trade_number'.")
        if num in seen_numbers:
            raise ValueError(
                f"Duplicate trade_number {num} found in trade records."
            )
        seen_numbers.append(num)

    seen_numbers_sorted = sorted(seen_numbers)
    expected_sequence = list(range(1, len(seen_numbers_sorted) + 1))
    if seen_numbers_sorted != expected_sequence:
        raise ValueError(
            f"Trade numbers are not sequential starting from 1. "
            f"Found: {seen_numbers_sorted}"
        )


# ─────────────────────────────────────────────
# SECTION 8: CSV WRITER
# Builds Exit and Entry rows for each trade record
# in the correct order (Exit first, Entry second)
# and writes to the output CSV file.
# ─────────────────────────────────────────────

def build_exit_row(record):
    """
    Builds the Exit row for a trade record.
    Exit row appears first in the CSV for each trade number.

    CRITICAL: All percentage values are converted to strings with exactly 2 decimal places.

    Parameters
    ----------
    record : dict — Completed trade record.

    Returns
    -------
    list — Ordered field values matching TV_COLUMNS.
    """
    return [
        record["trade_number"],
        record["exit_type"],
        record["exit_datetime"],
        record["exit_signal"],
        round_price(record["exit_price"]),
        record["size_qty"],
        round_price(record["size_value"]),
        round_price(record["net_pnl"]),
        round_percent(record["net_pnl_pct"]),  # ← STRING with 2 decimals
        round_price(record["favorable_excursion"]),
        round_percent(record["favorable_excursion_pct"]),  # ← STRING with 2 decimals
        round_price(record["adverse_excursion"]),
        round_percent(record["adverse_excursion_pct"]),  # ← STRING with 2 decimals
        round_price(record["cumulative_pnl"]),
        round_percent(record["cumulative_pnl_pct"]),  # ← STRING with 2 decimals
    ]


def build_entry_row(record):
    """
    Builds the Entry row for a trade record.
    Entry row appears second in the CSV for each trade number.

    CRITICAL: All percentage values are converted to strings with exactly 2 decimal places.

    Parameters
    ----------
    record : dict — Completed trade record.

    Returns
    -------
    list — Ordered field values matching TV_COLUMNS.
    """
    return [
        record["trade_number"],
        record["entry_type"],
        record["entry_datetime"],
        record["entry_signal"],
        round_price(record["entry_price"]),
        record["size_qty"],
        round_price(record["size_value"]),
        round_price(record["net_pnl"]),
        round_percent(record["net_pnl_pct"]),  # ← STRING with 2 decimals
        round_price(record["favorable_excursion"]),
        round_percent(record["favorable_excursion_pct"]),  # ← STRING with 2 decimals
        round_price(record["adverse_excursion"]),
        round_percent(record["adverse_excursion_pct"]),  # ← STRING with 2 decimals
        round_price(record["cumulative_pnl"]),
        round_percent(record["cumulative_pnl_pct"]),  # ← STRING with 2 decimals
    ]


def generate_csv(trade_records, output_path):
    """
    Main entry point for CSV generation.

    Steps:
    1. Validates header schema.
    2. Validates full trade record list.
    3. Validates each individual trade record.
    4. Writes Exit row then Entry row per trade to CSV.

    Parameters
    ----------
    trade_records : list of dict
        Completed trade records from trade_builder.py.
    output_path : str
        Full file path for the output CSV file.
        Example: "output/futures/pnf_pullback_trades.csv"

    Raises
    ------
    ValueError if any validation fails.
    IOError if the output file cannot be written.
    """
    # Step 1: Validate header schema
    validate_header()

    # Step 2: Validate full trade list
    validate_trade_list(trade_records)

    # Step 3: Validate each record individually
    for record in trade_records:
        validate_trade_record(record)

    # Step 4: Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Step 5: Write CSV
    with open(output_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Write header
        writer.writerow(TV_COLUMNS)

        # Write Exit row first, then Entry row for each trade
        for record in trade_records:
            writer.writerow(build_exit_row(record))
            writer.writerow(build_entry_row(record))

    print(f"CSV written successfully: {output_path}")
    print(f"Total trades written: {len(trade_records)}")
    print(f"Total rows written: {len(trade_records) * 2} (excluding header)")
