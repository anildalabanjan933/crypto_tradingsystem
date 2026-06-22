# engine/margin_calculator.py
# Responsibility: Calculate margin requirements

from config.margin_config import margin_config


class MarginCalculator:
    """
    Calculates margin requirements for trades.
    """

    def __init__(self, config=None):
        """
        Initialize MarginCalculator.

        Parameters
        ----------
        config : dict
            Margin configuration
        """
        self.config = config or margin_config

    def calculate_futures_margin(self, lot_size, entry_price, leverage=None):
        """
        Calculate margin for futures trade.

        Parameters
        ----------
        lot_size : int
            Number of lots
        entry_price : float
            Entry price
        leverage : int
            Leverage (default from config)

        Returns
        -------
        float
            Margin required
        """
        if leverage is None:
            leverage = self.config['futures']['leverage']

        position_value = lot_size * entry_price
        margin_required = position_value / leverage
        return margin_required

    def calculate_option_margin(self, lot_size, premium, option_type):
        """
        Calculate margin for option trade.

        Parameters
        ----------
        lot_size : int
            Number of lots
        premium : float
            Option premium
        option_type : str
            'long_call', 'long_put', 'short_call', 'short_put'

        Returns
        -------
        float
            Margin required
        """
        option_config = self.config['options'].get(option_type, {})

        if 'long' in option_type:
            # Long options: margin = premium paid
            margin_required = lot_size * premium
        else:
            # Short options: margin = strike * multiplier / leverage
            leverage = option_config.get('leverage', 5)
            multiplier = option_config.get('margin_multiplier', 0.10)
            margin_required = (lot_size * premium * multiplier) / leverage

        return margin_required

    def validate_margin(self, margin_required, available_capital):
        """
        Validate if margin is available.

        Parameters
        ----------
        margin_required : float
            Margin required
        available_capital : float
            Available capital

        Returns
        -------
        bool
            True if margin available, False otherwise
        """
        return margin_required <= available_capital
