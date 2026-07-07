content = open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'r').read()
old = """        builder = RenkoBuilder(box_size=self.renko_box)"""
new = """        current_price = closes[0] if len(closes) > 0 else 100000.0
        box_size = max(1, round(current_price * self.renko_box_pct))
        builder = RenkoBuilder(box_size=box_size)"""
open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'w').write(content.replace(old, new))
print('Fix 4 DONE' if 'renko_box_pct' in open('strategies/backtest/renko_smiio_supertrend_strategy.py').read() else 'Fix 4 FAILED')
