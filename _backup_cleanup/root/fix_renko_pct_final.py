path = 'strategies/backtest/renko_smiio_supertrend_strategy.py'
lines = open(path, 'r').read().split('\n')
new_lines = []
changed = []

for i, line in enumerate(lines):
    lineno = i + 1

    # FIX 1: __init__ renko_box → renko_box_pct
    if 'self.renko_box' in line and 'kwargs.get' in line:
        new_line = "        self.renko_box_pct = kwargs.get('renko_box_pct', 0.0020)"
        new_lines.append(new_line)
        changed.append(f'Line {lineno}: __init__ renko_box -> renko_box_pct')
        continue

    # FIX 2: optimization_params renko_box entry
    if "'renko_box'" in line and 'default' in line and 'min' in line:
        new_line = "            'renko_box_pct': {'default': 0.0020, 'min': 0.0010, 'max': 0.0040, 'step': 0.0005},"
        new_lines.append(new_line)
        changed.append(f'Line {lineno}: optimization_params renko_box -> renko_box_pct')
        continue

    # FIX 3: _build_renko_df box_size = self.renko_box
    if 'box_size = self.renko_box' in line:
        indent = len(line) - len(line.lstrip())
        pad = ' ' * indent
        new_line = f"{pad}current_price = df['close'].iloc[-1]"
        new_lines.append(new_line)
        new_lines.append(f"{pad}box_size = max(1, round(current_price * self.renko_box_pct))")
        changed.append(f'Line {lineno}: _build_renko_df box_size -> percentage calc')
        continue

    # FIX 4: generate_signals box = self.renko_box
    if 'box = self.renko_box' in line:
        indent = len(line) - len(line.lstrip())
        pad = ' ' * indent
        new_line = f"{pad}current_price = df['close'].iloc[-1]"
        new_lines.append(new_line)
        new_lines.append(f"{pad}box = max(1, round(current_price * self.renko_box_pct))")
        changed.append(f'Line {lineno}: generate_signals box -> percentage calc')
        continue

    new_lines.append(line)

open(path, 'w').write('\n'.join(new_lines))

print(f'Changes made: {len(changed)}')
for c in changed:
    print(f'  DONE: {c}')

# Verify
content2 = open(path).read()
lines2 = content2.split('\n')
pct_count = sum(1 for l in lines2 if 'renko_box_pct' in l)
box_count  = sum(1 for l in lines2 if 'renko_box' in l and 'renko_box_pct' not in l)
print(f'\nVerification:')
print(f'  renko_box_pct occurrences: {pct_count}  (expected 4+)')
print(f'  renko_box only occurrences: {box_count}  (expected 0)')
