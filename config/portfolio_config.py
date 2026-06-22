# config/portfolio_config.py
# Responsibility: Define predefined portfolios

portfolios = {
    "DE-Strangle Intraday": {
        "description": "Intraday option selling (3 strategies)",
        "strategies": [
            {"name": "de_strangle_9_20", "symbol": "BTCUSD"},
            {"name": "de_strangle_10_20", "symbol": "BTCUSD"},
            {"name": "de_strangle_11_20", "symbol": "BTCUSD"}
        ]
    },

    "DE-Strangle BTST": {
        "description": "BTST directional option strategies (4 strategies)",
        "strategies": [
            {"name": "de_strangle_btst_7_00", "symbol": "BTCUSD"},
            {"name": "de_strangle_btst_9_20", "symbol": "BTCUSD"},
            {"name": "de_strangle_btst_10_20", "symbol": "BTCUSD"},
            {"name": "de_strangle_btst_11_20", "symbol": "BTCUSD"}
        ]
    },

    "Monthly Positional": {
        "description": "Monthly positional option strategies (3 strategies)",
        "strategies": [
            {"name": "short_strangle", "symbol": "BTCUSD"},
            {"name": "ratio_calendar_spread", "symbol": "BTCUSD"},
            {"name": "triple_straddle", "symbol": "BTCUSD"}
        ]
    }
}
