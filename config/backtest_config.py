# config/backtest_config.py
# Responsibility: Define backtest settings

backtest_config = {
    # Capital
    "initial_capital_usd": 100000,

    # Default CSV path (1M base data from Delta Exchange)
    "default_csv_path": "data/btc_1m_delta.csv",

    # Date range presets
    "date_range_presets": {
        "1_month": {"days": 30},
        "3_months": {"days": 90},
        "6_months": {"days": 180},
        "1_year": {"days": 365}
    },

    # Timeframes
    "timeframes": ["1M", "5M", "15M", "30M", "1H", "4H", "Daily"],

    # Symbols
    "symbols": ["BTCUSD", "ETHUSD"],

    # Display settings
    "currency_display": "INR",
    "currency_symbol": "₹",
    "secondary_display": "percentage"
}
