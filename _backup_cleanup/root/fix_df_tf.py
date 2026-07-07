path = 'strategies/backtest/renko_smiio_supertrend_strategy.py'
lines = open(path, 'r').read().split('\n')
new_lines = []
changed = []

for i, line in enumerate(lines):
    lineno = i + 1
    # Fix _build_renko_df: df['close'] -> tf['close']
    if "current_price = df['close'].iloc[-1]" in line:
        indent = len(line) - len(line.lstrip())
        pad = ' ' * indent
        new_line = f"{pad}current_price = tf['close'].iloc[-1]"
        new_lines.append(new_line)
        changed.append(f'Line {lineno}: df -> tf in _build_renko_df DONE')
        continue
    new_lines.append(line)

open(path, 'w').write('\n'.join(new_lines))
print(f'Changes made: {len(changed)}')
for c in changed:
    print(f'  DONE: {c}')
