# Fix run_optimization.py
content = open('run_optimization.py').read()
lines = content.split('\n')
new_lines = []
for i, line in enumerate(lines):
    if '"renko_box":' in line and 'values' in line and 'renko_box_pct' not in line:
        new_line = '        "renko_box_pct":   {"values": [0.0010, 0.0015, 0.0020, 0.0025, 0.0030, 0.0035, 0.0040]}'
        new_lines.append(new_line)
        print(f'run_optimization.py Line {i+1}: renko_box -> renko_box_pct DONE')
    else:
        new_lines.append(line)
open('run_optimization.py', 'w').write('\n'.join(new_lines))

# Fix engine/optimizer.py
content = open('engine/optimizer.py').read()
lines = content.split('\n')
new_lines = []
for i, line in enumerate(lines):
    if "'renko_box': 'renko_box'" in line and 'renko_box_pct' not in line:
        print(f'engine/optimizer.py Line {i+1}: renko_box entry removed DONE')
        continue
    new_lines.append(line)
open('engine/optimizer.py', 'w').write('\n'.join(new_lines))

# Verify run_optimization.py
content = open('run_optimization.py').read()
print('\nrun_optimization.py verification:')
print(f'  renko_box_pct present: {"renko_box_pct" in content}  (expected True)')
print(f'  old renko_box present: {chr(34)+"renko_box"+chr(34)+":       {" in content}  (expected False)')

# Verify optimizer.py
content = open('engine/optimizer.py').read()
print('\nengine/optimizer.py verification:')
print(f'  renko_box_pct present: {"renko_box_pct" in content}  (expected True)')
print(f'  old renko_box entry:   {"renko_box\x27: \x27renko_box\x27" in content}  (expected False)')
