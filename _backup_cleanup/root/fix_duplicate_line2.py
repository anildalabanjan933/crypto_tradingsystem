path = 'strategies/backtest/renko_smiio_supertrend_strategy.py'
lines = open(path, 'r').read().split('\n')
new_lines = []
changed = []

for i, line in enumerate(lines):
    lineno = i + 1
    if lineno == 165 and "current_price = tf['close'].iloc[-1]" in line:
        changed.append(f'Line {lineno}: duplicate current_price line removed')
        continue
    new_lines.append(line)

open(path, 'w').write('\n'.join(new_lines))
print(f'Changes made: {len(changed)}')
for c in changed:
    print(f'  DONE: {c}')
