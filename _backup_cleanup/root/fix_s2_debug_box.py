import pathlib

fpath = r'D:\crypto_trading_system\strategies\backtest\renko_reversal_strategy.py'
src = pathlib.Path(fpath).read_text()

# FIX: replace self.renko_box in debug section
src = src.replace("box_temp = self.renko_box", "current_price_tmp = self._data['2h']['close'].iloc[-1]\n        box_temp = max(1, round(current_price_tmp * self.renko_box_pct))")

pathlib.Path(fpath).write_text(src)
print("Fix applied")

src2 = pathlib.Path(fpath).read_text()
print("self.renko_box remaining:", src2.count("self.renko_box"))
