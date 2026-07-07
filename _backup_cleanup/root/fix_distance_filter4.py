filepath = 'strategies/backtest/renko_smiio_supertrend_strategy.py'
with open(filepath, 'r') as f:
    content = f.read()

old_dist = "            'crossover_distance':      {'default': 0.1, 'min': 0.1, 'max': 2.5, 'step': 0.1},"
new_dist = "            'crossover_distance':      {'default': 4.0, 'min': 2.0, 'max': 10.0, 'step': 2.0},"
content = content.replace(old_dist, new_dist)

old_count = "            'crossover_count_limit':   {'default': 1,   'min': 1,   'max': 3,   'step': 1},"
new_count = "            'crossover_count_limit':   {'default': 2,   'min': 2,   'max': 5,   'step': 1},"
content = content.replace(old_count, new_count)

with open(filepath, 'w') as f:
    f.write(content)

print('Fix applied successfully')
for line in content.split('\n'):
    if any(x in line for x in ['crossover_distance', 'crossover_count_limit']):
        print(line.strip())
