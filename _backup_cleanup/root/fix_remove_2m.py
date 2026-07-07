f = open('run_optimization.py', 'r')
content = f.read()
f.close()

old = '        "renko_timeframe": {"values": ["1m", "2m", "5m", "15m", "30m", "1h", "2h"]},'
new = '        "renko_timeframe": {"values": ["1m", "5m", "15m", "30m", "1h", "2h"]},'

content = content.replace(old, new)
f = open('run_optimization.py', 'w')
f.write(content)
f.close()
print('Fix done')
