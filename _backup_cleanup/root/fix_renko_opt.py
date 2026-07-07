path = 'run_optimization.py'
content = open(path).read()
old = '"renko_box":       {"values": [100, 150, 200, 250, 300, 350, 400]}'
new = '"renko_box_pct":   {"values": [0.0010, 0.0015, 0.0020, 0.0025, 0.0030, 0.0035, 0.0040]}'
if old in content:
    content = content.replace(old, new)
    open(path, 'w').write(content)
    print('DONE: renko_box replaced with renko_box_pct')
else:
    print('NOT FOUND: check exact string')
