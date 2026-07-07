with open('run_optimization.py', 'r') as f:
    content = f.read()

old = '        "renko_box_pct":   {"values": [0.0010, 0.0015, 0.0020, 0.0025, 0.0030, 0.0035, 0.0040]}'
new = '        "renko_box":       {"values": [100, 150, 200, 250, 300, 350, 400]}'

if old in content:
    content = content.replace(old, new)
    with open('run_optimization.py', 'w') as f:
        f.write(content)
    print('FIXED: renko_box_pct replaced with renko_box')
else:
    print('NOT FOUND')
