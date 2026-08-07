# strategies/backtest/renko_smiio_supertrend_v2_strategy.py
# S4V2 - Variant #5 (safer): 30m, ATR=5, Factor=1.5, SMIIO=10/3
# Subclass only - original renko_smiio_supertrend_strategy.py NEVER touched

from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy


class RenkoSMIIOSupertrendV2Strategy(RenkoSMIIOSupertrendStrategy):
    """
    S4V2 - Variant #5 (safer optimized params)
    TF=30m | ATR=5 | Factor=1.5 | SMIIO=10/3 | box_pct=0.001
    Backtest: 13,627 trades | Win 58.72% | Sharpe 7.67 | DD -0.18%
    """
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        kwargs.setdefault('renko_timeframe', '30m')
        kwargs.setdefault('renko_box_pct', 0.001)
        kwargs.setdefault('st_atr_length', 5)
        kwargs.setdefault('st_factor', 1.5)
        kwargs.setdefault('smiio_shortlen', 10)
        kwargs.setdefault('smiio_siglen', 3)
        super().__init__(data_dict=data_dict, lot_size=lot_size, **kwargs)
