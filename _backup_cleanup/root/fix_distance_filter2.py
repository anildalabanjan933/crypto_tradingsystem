with open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'r') as f:
    src = f.read()

old = (
    "            # 'smiio_avoid_entry_above': {'default': 0.0, 'min': 0.2, 'max': 0.6, 'step': 0.1},\n"
    "            # 'crossover_distance':      {'default': 0.0, 'min': 0.1, 'max': 2.5, 'step': 0.1},\n"
    "            # 'crossover_count_limit':   {'default': 0,   'min': 1,   'max': 3,   'step': 1},"
)
new = (
    "            'smiio_avoid_entry_above': {'default': 0.2, 'min': 0.2, 'max': 0.6, 'step': 0.1},\n"
    "            'crossover_distance':      {'default': 0.1, 'min': 0.1, 'max': 2.5, 'step': 0.1},\n"
    "            'crossover_count_limit':   {'default': 1,   'min': 1,   'max': 3,   'step': 1},"
)

if old in src:
    src = src.replace(old, new)
    with open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'w') as f:
        f.write(src)
    print("Fix applied successfully")
else:
    print("ERROR: old string not found - no changes made")
