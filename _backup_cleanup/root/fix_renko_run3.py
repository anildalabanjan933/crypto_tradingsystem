f = open('run_optimization.py', 'r')
content = f.read()
f.close()

old = '"renko_box_pct": {"values": [0.0004, 0.0005, 0.0006, 0.0007, 0.0008, 0.0009, 0.0010, 0.0015, 0.0020, 0.0025]}'
new = '"renko_box": {"values": [100, 150, 200, 250, 300, 350, 400]}'

content = content.replace(old, new)
f = open('run_optimization.py', 'w')
f.write(content)
f.close()
print('Fix done')
