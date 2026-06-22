# algotest_csv_generator.py
# Responsibility: Generate AlgoTest Signals Backtest compatible CSV format.
# ONE signal per row: Entry has Buy/Short, Exit has Sell/Cover

import csv
import os
from utils import round_price

# ─────────────────────────────────────────────
# ALGOTEST SIGNALS BACKTEST CSV SCHEMA
# ─────────────────────────────────────────────

ALGOTEST_COLUMNS = [
    "Trade #",
    "Type",
    "Signal",
    "Date and time",
    "Price INR",
]


def validate_algotest_header():
    """
    Validates AlgoTest CSV header schema.
    """
    expected = [
        "Trade #",
        "Type",
        "Signal",
        "Date and time",
        "Price INR",
    ]

    if len(ALGOTEST_COLUMNS) != len(expected):
        raise ValueError(
            f"Column count mismatch. "
            f"Expected {len(expected)}, got {len(ALGOTEST_COLUMNS)}."
        )

    for i, (actual, exp) in enumerate(zip(ALGOTEST_COLUMNS, expected)):
        if actual != exp:
            raise ValueError(
                f"Column mismatch at position {i}. "
                f"Expected '{exp}', got '{actual}'."
            )


def build_entry_row(record):
    """
    Builds Entry row for AlgoTest CSV.

    Parameters
    ----------
    record : dict
        Trade record from trade_builder.py

    Returns
    -------
    list — [Trade #, Type, Signal, Date and time, Price INR]
    """
    # Determine type based on entry_type
    if "long" in record["entry_type"].lower():
        trade_type = "Entry Long"
    else:
        trade_type = "Entry Short"

    return [
        record["trade_number"],
        trade_type,
        record["entry_signal"],  # Buy or Short
        record["entry_datetime"],
        round_price(record["entry_price"]),
    ]


def build_exit_row(record):
    """
    Builds Exit row for AlgoTest CSV.

    Parameters
    ----------
    record : dict
        Trade record from trade_builder.py

    Returns
    -------
    list — [Trade #, Type, Signal, Date and time, Price INR]
    """
    # Determine type based on exit_type
    if "long" in record["exit_type"].lower():
        trade_type = "Exit Long"
    else:
        trade_type = "Exit Short"

    return [
        record["trade_number"],
        trade_type,
        record["exit_signal"],  # Sell or Cover
        record["exit_datetime"],
        round_price(record["exit_price"]),
    ]


def generate_algotest_csv(trade_records, output_path):
    """
    Generate AlgoTest Signals Backtest compatible CSV.

    Format:
    - Entry row first (with Buy or Short signal)
    - Exit row second (with Sell or Cover signal)
    - One signal per row

    Parameters
    ----------
    trade_records : list of dict
        Completed trade records from trade_builder.py
    output_path : str
        Full file path for output CSV

    Raises
    ------
    ValueError if validation fails
    IOError if file cannot be written
    """
    # Validate header
    validate_algotest_header()

    # Validate trade records
    if not trade_records:
        raise ValueError("Trade record list is empty.")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Write CSV with quotes around all fields
    with open(output_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)

        # Write header
        writer.writerow(ALGOTEST_COLUMNS)

        # Write Entry row first, then Exit row for each trade
        for record in trade_records:
            writer.writerow(build_entry_row(record))
            writer.writerow(build_exit_row(record))

    print(f"AlgoTest CSV written successfully: {output_path}")
    print(f"Total trades written: {len(trade_records)}")
    print(f"Total rows written: {len(trade_records) * 2} (excluding header)")
