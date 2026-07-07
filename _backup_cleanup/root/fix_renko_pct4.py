content = open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'r').read()
old = """        closes    = df['renko_close'].values
        renko_dir = df['renko_dir'].values"""
new = """        closes    = df['renko_close'].values
        renko_dir = df['renko_dir'].values
        current_price = closes[0] if len(closes) > 0 else 100000.0
        box = max(1, round(current_price * self.renko_box_pct))"""
open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'w').write(content.replace(old, new))
print('Fix 5 DONE' if 'box = max(1' in open('strategies/backtest/renko_smiio_supertrend_strategy.py').read() else 'Fix 5 FAILED')
