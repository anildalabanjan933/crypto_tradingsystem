f = open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'r')
lines = f.read().split('\n')
f.close()

new_lines = []
for line in lines:
    if 'self.crossover_count_limit > 0' in line and 'self.crossover_distance > 0.0' in line:
        continue
    new_lines.append(line)

f = open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'w')
f.write('\n'.join(new_lines))
f.close()
print('Remaining line removed successfully')
