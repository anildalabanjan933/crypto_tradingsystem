f = open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'r')
lines = f.read().split('\n')
f.close()

new_lines = []
for i, line in enumerate(lines):
    if line.strip() == 'if (smi_cross_up or smi_cross_down):':
        continue
    if line.strip() == 'else:':
        continue
    new_lines.append(line)

f = open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'w')
f.write('\n'.join(new_lines))
f.close()
print('Fix done')
