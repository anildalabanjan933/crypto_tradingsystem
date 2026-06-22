# strategies/base_strategy.py

from abc import ABC, abstractmethod


class BaseStrategy(ABC):

    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        """
        data_dict: keys are timeframe strings (e.g. '1H', '1D'),
                   values are pandas DataFrames with OHLCV data.
        lot_size:  position size passed in by the backtest engine.
        """
        self._data = data_dict
        self.lot_size = lot_size
        self.signals = []

    def get_data(self, timeframe: str):
        if timeframe not in self._data:
            raise KeyError(f"Timeframe '{timeframe}' not found in data_dict. "
                           f"Available: {list(self._data.keys())}")
        return self._data[timeframe]

    @property
    @abstractmethod
    def required_timeframes(self) -> list:
        """Return list of timeframe strings this strategy needs, e.g. ['1H']"""
        pass

    @property
    @abstractmethod
    def optimization_params(self) -> dict:
        """Return dict of optimisable parameters with default/min/max/step."""
        pass

    @abstractmethod
    def generate_signals(self) -> list:
        """
        Run the strategy logic and populate self.signals.
        Must return a list of signal dicts.
        """
        pass
