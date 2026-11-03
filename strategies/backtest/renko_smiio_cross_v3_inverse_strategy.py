# S4V3 INVERSE (backtest only): same entry/exit bars and size, only the side is flipped.
from strategies.backtest.renko_smiio_cross_v3_strategy import RenkoSMIIOCrossV3Strategy


class RenkoSmiioCrossV3InverseStrategy(RenkoSMIIOCrossV3Strategy):
    def __init__(self, data_dict: dict, lot_size: float = 1.0, **kwargs):
        # S4V3 live-matched defaults (the dashboard CLI passes no params for this class)
        kwargs.setdefault('renko_box_pct', 0.001)
        kwargs.setdefault('renko_timeframe', '4h')
        kwargs.setdefault('smiio_shortlen', 5)
        kwargs.setdefault('smiio_longlen', 10)
        kwargs.setdefault('smiio_siglen', 3)
        super().__init__(data_dict=data_dict, lot_size=lot_size, **kwargs)

    def generate_signals(self) -> list:
        _slip = self.slippage_usd
        self.slippage_usd = 0.0
        try:
            sigs = super().generate_signals()
        finally:
            self.slippage_usd = _slip
        out = []
        for s in sigs:
            d = dict(s)
            raw = float(d['price'])
            new_dir = 'short' if d['direction'] == 'long' else 'long'
            is_entry = (d['signal_type'] == 'ENTRY')
            d['direction'] = new_dir
            d['price'] = self._apply_slippage(raw, new_dir, is_entry)
            d['sl_price'] = 2.0 * raw - float(d['sl_price'])
            out.append(d)
        return out
