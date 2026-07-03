# config/symbol_config.py
# Symbol-specific strategy configuration
# Box size defined as % of price for cross-symbol consistency

SYMBOL_BOX_PCT = {}  # Add per-coin exceptions here if needed in future

BOX_SIZE_PCT = 0.0031  # 0.31% default for ALL coins


def get_renko_box_size(symbol: str, current_price: float = None) -> float:
    """
    Returns renko box size for a symbol.
    - All coins: 0.31% of current price universally
    - Add exceptions to SYMBOL_BOX_PCT dict if needed
    """
    if symbol in SYMBOL_BOX_PCT:
        pct = SYMBOL_BOX_PCT[symbol]
        if current_price and current_price > 0:
            return round(current_price * pct)
        return 200

    if current_price and current_price > 0:
        calculated = round(current_price * BOX_SIZE_PCT)
        return max(calculated, 1)

    return 200  # safe fallback
