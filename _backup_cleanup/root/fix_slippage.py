f = open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'r')
content = f.read()
f.close()

old = """        slip = self.slippage_usd
        if direction == 'long':
            return price + slip if is_entry else price - slip
            return price - slip if is_entry else price + slip"""

new = """        slip = self.slippage_usd
        if direction == 'long':
            return price + slip if is_entry else price - slip
        else:
            return price - slip if is_entry else price + slip"""

content = content.replace(old, new)
f = open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'w')
f.write(content)
f.close()
print('Fix done')
