content = open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'r').read()

# Fix A: remove old box = self.renko_box line
content = content.replace("        box = self.renko_box\n", "")

# Fix B: update optimization_params renko_box to renko_box_pct
content = content.replace(
    "            'renko_box':      {'default': 200,  'min': 100,  'max': 500,  'step': 50},",
    "            'renko_box_pct':  {'default': 0.0020, 'min': 0.0010, 'max': 0.0040, 'step': 0.0005},"
)

# Fix C: remove unused import
content = content.replace("from config.symbol_config import get_renko_box_size\n", "")

open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'w').write(content)

remaining = open('strategies/backtest/renko_smiio_supertrend_strategy.py').read()
ok1 = 'box = self.renko_box' not in remaining
ok2 = 'renko_box_pct' in remaining
ok3 = 'get_renko_box_size' not in remaining
print('Fix A DONE' if ok1 else 'Fix A FAILED')
print('Fix B DONE' if ok2 else 'Fix B FAILED')
print('Fix C DONE' if ok3 else 'Fix C FAILED')
