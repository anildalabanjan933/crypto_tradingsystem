f = open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'r')
lines = f.read().split('\n')
f.close()

new_lines = []
for i, line in enumerate(lines):
    if 'smiio_avoid_entry_above' in line and 'skip entry' in line:
        continue
    if 'crossover_distance' in line and 'min gap' in line:
        continue
    if 'crossover_count_limit' in line and 'block entry' in line:
        continue
    if 'self.smiio_avoid_entry_above' in line and 'kwargs.get' in line:
        continue
    if 'self.crossover_distance' in line and 'kwargs.get' in line:
        continue
    if 'self.crossover_count_limit' in line and 'kwargs.get' in line:
        continue
    if 'smiio_avoid_entry_above' in line and 'default' in line:
        continue
    if 'crossover_distance' in line and 'default' in line:
        continue
    if 'crossover_count_limit' in line and 'default' in line:
        continue
    if 'small_cross_count' in line:
        continue
    if 'elif side ==' in line and 'long' in line and 'crossover_distance' in line:
        line = '                elif side == "long" and r_dir == 1:'
    if 'elif side ==' in line and 'short' in line and 'crossover_distance' in line:
        line = '                elif side == "short" and r_dir == -1:'
    new_lines.append(line)

f = open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'w')
f.write('\n'.join(new_lines))
f.close()
print('Distance filter removed successfully')
