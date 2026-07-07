filepath = 'strategies/backtest/renko_smiio_supertrend_strategy.py'
with open(filepath, 'r') as f:
    lines = f.readlines()

# Step 1: Add small_cross_count = 0 after last_exit_ts = None (line 171)
old_init = '        last_exit_ts = None\n'
new_init = '        last_exit_ts = None\n        small_cross_count = 0\n'

# Step 2: Add count logic after smi_cross_down line (line 179)
old_cross = '            smi_cross_down = smi[i] < sig[i] and smi[i-1] >= sig[i-1]\n'
new_cross = ('            smi_cross_down = smi[i] < sig[i] and smi[i-1] >= sig[i-1]\n'
             '            if (smi_cross_up or smi_cross_down):\n'
             '                if self.crossover_count_limit > 0 and self.crossover_distance > 0.0 and abs(smi[i] - sig[i]) < self.crossover_distance:\n'
             '                    small_cross_count += 1\n'
             '                else:\n'
             '                    small_cross_count = 0\n')

# Step 3: Add count check to LONG entry (line 206)
old_long = ('                elif side == "long" and r_dir == 1 and '
            '(self.crossover_distance == 0.0 or abs(smi[i] - sig[i]) >= self.crossover_distance) and '
            '(self.smiio_avoid_entry_above == 0.0 or abs(smi[i]) <= self.smiio_avoid_entry_above):\n')
new_long = ('                elif side == "long" and r_dir == 1 and '
            '(self.crossover_distance == 0.0 or abs(smi[i] - sig[i]) >= self.crossover_distance) and '
            '(self.smiio_avoid_entry_above == 0.0 or abs(smi[i]) <= self.smiio_avoid_entry_above) and '
            '(self.crossover_count_limit == 0 or small_cross_count < self.crossover_count_limit):\n')

# Step 4: Add count check to SHORT entry (line 210)
old_short = ('                elif side == "short" and r_dir == -1 and '
             '(self.crossover_distance == 0.0 or abs(smi[i] - sig[i]) >= self.crossover_distance) and '
             '(self.smiio_avoid_entry_above == 0.0 or abs(smi[i]) <= self.smiio_avoid_entry_above):\n')
new_short = ('                elif side == "short" and r_dir == -1 and '
             '(self.crossover_distance == 0.0 or abs(smi[i] - sig[i]) >= self.crossover_distance) and '
             '(self.smiio_avoid_entry_above == 0.0 or abs(smi[i]) <= self.smiio_avoid_entry_above) and '
             '(self.crossover_count_limit == 0 or small_cross_count < self.crossover_count_limit):\n')

content = ''.join(lines)
content = content.replace(old_init, new_init)
content = content.replace(old_cross, new_cross)
content = content.replace(old_long, new_long)
content = content.replace(old_short, new_short)

with open(filepath, 'w') as f:
    f.write(content)

print('Layer 2 wired successfully')
for line in content.split('\n'):
    if any(x in line for x in ['small_cross_count', 'crossover_count_limit']):
        print(line.strip())
