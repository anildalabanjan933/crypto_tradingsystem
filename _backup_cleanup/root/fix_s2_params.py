import pathlib

fpath = r'D:\crypto_trading_system\strategies\backtest\renko_reversal_strategy.py'
src = pathlib.Path(fpath).read_text()

src = src.replace("self.renko_box    = kwargs.get('renko_box', 200.0)", "self.renko_box_pct = kwargs.get('renko_box_pct', 0.0020)")
src = src.replace("self.max_tl_bars  = kwargs.get('max_tl_bars', 50)", "self.max_tl_bars  = kwargs.get('max_tl_bars', 50)\n        self.st_atr_length = kwargs.get('st_atr_length', 5)\n        self.st_factor     = kwargs.get('st_factor', 4.0)")
src = src.replace("st_indicator = SupertrendIndicator(atr_period=5, factor=4.0)", "st_indicator = SupertrendIndicator(atr_period=self.st_atr_length, factor=self.st_factor)")
src = src.replace("builder   = RenkoBuilder(box_size=self.renko_box)", "current_price = self._data['2h']['close'].iloc[-1]\n        box_size = max(1, round(current_price * self.renko_box_pct))\n        builder   = RenkoBuilder(box_size=box_size)")
src = src.replace("box      = self.renko_box", "current_price = self._data['2h']['close'].iloc[-1]\n        box      = max(1, round(current_price * self.renko_box_pct))")

pathlib.Path(fpath).write_text(src)
print("All 5 fixes applied")

src2 = pathlib.Path(fpath).read_text()
print("renko_box_pct count:", src2.count("renko_box_pct"))
print("renko_box only:", src2.count("self.renko_box ") + src2.count("self.renko_box,") + src2.count("self.renko_box)"))
print("st_atr_length count:", src2.count("st_atr_length"))
print("st_factor count:", src2.count("st_factor"))
print("hardcoded ST count:", src2.count("atr_period=5, factor=4.0"))
