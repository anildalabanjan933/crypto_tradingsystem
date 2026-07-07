with open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'r') as f:
    content = f.read()

replacements = [
    (
        "self.renko_box_pct = kwargs.get('renko_box_pct', 0.0020)",
        "self.renko_box = kwargs.get('renko_box', 200)"
    ),
    (
        "'renko_box_pct':  {'default': 0.0020, 'min': 0.0010, 'max': 0.0040, 'step': 0.0005}",
        "'renko_box':      {'default': 200, 'min': 100, 'max': 400, 'step': 50}"
    ),
    (
        "box_size = max(1, round(current_price * self.renko_box_pct))",
        "box_size = self.renko_box"
    ),
    (
        "box = max(1, round(current_price * self.renko_box_pct))",
        "box = self.renko_box"
    ),
]

count = 0
for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        count += 1
        print(f'FIXED {count}: {old[:50]}')
    else:
        print(f'NOT FOUND: {old[:50]}')

with open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'w') as f:
    f.write(content)

print(f'Done: {count}/4 replacements applied')
