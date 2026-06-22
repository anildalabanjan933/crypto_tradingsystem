# utils.py
# Responsibility: Shared formatting and rounding utilities used by all modules

from datetime import datetime

# ─────────────────────────────────────────────
# SECTION 1: DATE UTILITIES
# ─────────────────────────────────────────────

DATE_FORMAT = "%Y-%m-%d %H:%M"


def format_date(dt):
    """
    Formats a datetime object or Unix timestamp to standard date string.
    Required format: YYYY-MM-DD HH:MM

    Parameters
    ----------
    dt : datetime or int/float
        A Python datetime object or Unix timestamp (seconds).

    Returns
    -------
    str — Formatted date string. Example: "2024-01-15 09:00"
    """
    if isinstance(dt, (int, float)):
        dt = datetime.fromtimestamp(dt)
    if not isinstance(dt, datetime):
        raise TypeError(
            f"format_date expects a datetime object or Unix timestamp. Got {type(dt)}."
        )
    return dt.strftime(DATE_FORMAT)


def parse_date(date_str):
    """
    Parses a date string to a datetime object.
    Required format: YYYY-MM-DD HH:MM

    Parameters
    ----------
    date_str : str — Date string in YYYY-MM-DD HH:MM format.

    Returns
    -------
    datetime — Python datetime object.

    Raises
    ------
    ValueError if the string does not match the required format.
    """
    try:
        return datetime.strptime(date_str, DATE_FORMAT)
    except ValueError:
        raise ValueError(
            f"parse_date: Invalid date string '{date_str}'. "
            f"Required format: YYYY-MM-DD HH:MM."
        )


# ─────────────────────────────────────────────
# SECTION 2: NUMERIC ROUNDING UTILITIES
# ─────────────────────────────────────────────

def round_price(value):
    """
    Rounds a price or PnL value to up to 2 decimal places.
    Removes trailing zeros (e.g., 4350.0 → 4350, 4263.5 → 4263.5).

    Parameters
    ----------
    value : float or int

    Returns
    -------
    float or int — Rounded numeric value.
    """
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def round_percent(value):
    """
    Rounds a percentage value to exactly 2 decimal places.
    ALWAYS returns a float — safe for all numeric calculations.

    Example: 5.0 → 5.0, -1.234 → -1.23, 0 → 0.0

    Parameters
    ----------
    value : float or int

    Returns
    -------
    float — Rounded percentage value (NOT a string).
    """
    return round(float(value), 2)


def format_percent(value):
    """
    Formats a percentage value as a string with exactly 2 decimal places.
    Use ONLY for display/reporting — NOT for calculations.

    Example: 5.0 → "5.00%", -1.234 → "-1.23%", 0 → "0.00%"

    Parameters
    ----------
    value : float or int

    Returns
    -------
    str — Formatted percentage string with % symbol.
    """
    return f"{round(float(value), 2):.2f}%"


# ─────────────────────────────────────────────
# SECTION 3: CURRENCY UTILITIES
# ─────────────────────────────────────────────

def format_number(value):
    """
    Formats a number with commas for thousands separator.
    Example: 1234567 → "1,234,567"

    Parameters
    ----------
    value : float or int

    Returns
    -------
    str — Formatted number with commas
    """
    return "{:,.0f}".format(float(value))


def format_currency(amount, symbol="₹"):
    """
    Formats amount as currency with symbol and commas.
    Example: 1234567 → "₹1,234,567"

    Parameters
    ----------
    amount : float or int
        Amount to format
    symbol : str
        Currency symbol (default: ₹)

    Returns
    -------
    str — Formatted currency string
    """
    formatted_number = format_number(amount)
    return f"{symbol}{formatted_number}"


def usd_to_inr(usd_amount, rate=84):
    """
    Converts USD to INR.
    Example: 100 → 8400

    Parameters
    ----------
    usd_amount : float or int
        Amount in USD
    rate : float
        Conversion rate (default: 84)

    Returns
    -------
    float — Amount in INR
    """
    return float(usd_amount) * rate


def inr_to_usd(inr_amount, rate=84):
    """
    Converts INR to USD.
    Example: 8400 → 100

    Parameters
    ----------
    inr_amount : float or int
        Amount in INR
    rate : float
        Conversion rate (default: 84)

    Returns
    -------
    float — Amount in USD
    """
    return float(inr_amount) / rate
