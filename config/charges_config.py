# config/charges_config.py
# Model: AlgoTest post-backtest method
# Confirmed rates: Delta Exchange /products API + AlgoTest screenshot analysis

charges_config = {
    # Trading fees (Delta Exchange confirmed)
    "taker_fee_rate": 0.0005,        # 0.05% per side
    "maker_fee_rate": 0.0002,        # 0.02% per side (informational only)

    # Slippage (conservative, AlgoTest matched)
    "slippage_rate": 0.05,           # 5% total on lot_notional_usd

    # Funding (Delta Exchange confirmed from /products API)
    "funding_rate_annual": 0.1095,   # 10.95% annualized
    "funding_interval_hours": 8,     # 8H interval per funding charge

    # Insurance fund (Delta Exchange: NOT charged to regular traders)
    "insurance_fund_rate": 0.0,      # Confirmed 0 — framework doc value (0.05) is WRONG

    # Tax (AlgoTest reverse-engineered from screenshots: 10% on net profit, winners only)
    "tax_rate": 0.10,                # Confirmed 10% — framework doc value (0.30) is WRONG

    # Currency conversion (for INR display per framework requirement)
    "usd_to_inr_rate": 84,           # 1 USD = 84 INR

    # Futures lot base (charge calculations use this, NOT full BTC notional)
    "lot_notional_usd": 100.0,       # Fixed 100 USD per lot

    # Contract specification (BTCUSD)
    "contract_value": 0.001,         # 0.001 BTC per contract
}
