# config/margin_config.py
# Responsibility: Define margin settings for backtests

margin_config = {
    "mode": "portfolio",  # "portfolio" or "isolated"

    "futures": {
        "leverage": 10,
        "initial_margin_percent": 0.10,  # 10%
        "maintenance_margin_percent": 0.05  # 5%
    },

    "options": {
        "long_call": {
            "leverage": 1,
            "margin_percent": 1.0  # 100% of premium
        },
        "long_put": {
            "leverage": 1,
            "margin_percent": 1.0  # 100% of premium
        },
        "short_call": {
            "leverage": 5,
            "margin_multiplier": 0.10,  # 10% of strike
            "maintenance_margin_percent": 0.75
        },
        "short_put": {
            "leverage": 5,
            "margin_multiplier": 0.10,  # 10% of strike
            "maintenance_margin_percent": 0.75
        }
    }
}
