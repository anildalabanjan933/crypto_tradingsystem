path1 = 'run_optimization.py'
path2 = 'engine/optimizer.py'
path3 = 'strategies/backtest/renko_smiio_supertrend_strategy.py'

# --- Revert run_optimization.py ---
content = open(path1).read()
content = content.replace(
    "'renko_box': [100, 150, 200, 250, 300, 350, 400]",
    "'renko_box_pct': [0.0010, 0.0015, 0.0020, 0.0025, 0.0030, 0.0035, 0.0040]"
)
open(path1, 'w').write(content)
print('DONE: run_optimization.py reverted')

# --- Revert engine/optimizer.py ---
content = open(path2).read()
content = content.replace(
    "'renko_box': 'renko_box'",
    "'renko_box_pct': 'renko_box_pct'"
)
open(path2, 'w').write(content)
print('DONE: engine/optimizer.py reverted')

# --- Revert strategy file ---
content = open(path3).read()
content = content.replace(
    "self.renko_box = kwargs.get('renko_box', 100)",
    "self.renko_box_pct = kwargs.get('renko_box_pct', 0.0020)"
)
open(path3, 'w').write(content)
print('DONE: strategy file reverted')

print('All 3 reverts complete')
