filepath = 'strategies/backtest/renko_smiio_supertrend_strategy.py'
with open(filepath, 'r') as f:
    content = f.read()

old_dist = "            'crossover_distance':      {'default': 4.0, 'min': 2.0, 'max': 10.0, 'step': 2.0},"
new_dist = "            'crossover_distance':      {'default': 2.0, 'min': 1.0, 'max': 6.0, 'step': 1.0},"

content = content.replace(old_dist, new_dist)

with open(filepath, 'w') as f:
    f.write(content)

print('Fix applied successfully')
for line in content.split('\n'):
    if 'crossover_distance' in line and 'default' in line:
        print(line.strip())
