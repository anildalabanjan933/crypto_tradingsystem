with open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'r') as f:
    src = f.read()

old_op = "'smiio_longlen': {'default': 20, 'min': 10, 'max': 40, 'step': 5}}"
new_op = ("'smiio_longlen': {'default': 20, 'min': 10, 'max': 40, 'step': 5},\n"
          "            'crossover_distance':      {'default': 0.1, 'min': 0.1, 'max': 2.5, 'step': 0.1},\n"
          "            'crossover_count_limit':   {'default': 1,   'min': 1,   'max': 3,   'step': 1},\n"
          "            'smiio_avoid_entry_above': {'default': 0.2, 'min': 0.2, 'max': 0.6, 'step': 0.1},\n"
          "        }")
src = src.replace(old_op, new_op)

old_long = 'elif side == "long" and r_dir == 1:'
new_long = ('elif side == "long" and r_dir == 1'
            ' and (self.crossover_distance == 0.0 or abs(smi[i] - sig[i]) >= self.crossover_distance)'
            ' and (self.smiio_avoid_entry_above == 0.0 or abs(smi[i]) <= self.smiio_avoid_entry_above):')
src = src.replace(old_long, new_long)

old_short = 'elif side == "short" and r_dir == -1:'
new_short = ('elif side == "short" and r_dir == -1'
             ' and (self.crossover_distance == 0.0 or abs(smi[i] - sig[i]) >= self.crossover_distance)'
             ' and (self.smiio_avoid_entry_above == 0.0 or abs(smi[i]) <= self.smiio_avoid_entry_above):')
src = src.replace(old_short, new_short)

with open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'w') as f:
    f.write(src)

print("Fix applied successfully")
