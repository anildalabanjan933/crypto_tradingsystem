content = open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'r').read()
old = """        self.renko_box = kwargs.get('renko_box') or get_renko_box_size(symbol, current_price)
        self.renko_timeframe = kwargs.get('renko_timeframe', '2h')  # ADD THIS LINE"""
new = """        self.renko_box_pct = kwargs.get('renko_box_pct', 0.0020)
        self.renko_timeframe = kwargs.get('renko_timeframe', '2h')"""
open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'w').write(content.replace(old, new))
print('Fix 3 DONE' if 'renko_box_pct' in open('strategies/backtest/renko_smiio_supertrend_strategy.py').read() else 'Fix 3 FAILED')
