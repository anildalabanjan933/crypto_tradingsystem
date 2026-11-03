# S4V3 INVERSE: same entry/exit bars and size, only the side is flipped.
from strategies.backtest.renko_smiio_cross_v3_strategy import RenkoSMIIOCrossV3Strategy


class RenkoSMIIOCrossV3InverseStrategy(RenkoSMIIOCrossV3Strategy):
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
