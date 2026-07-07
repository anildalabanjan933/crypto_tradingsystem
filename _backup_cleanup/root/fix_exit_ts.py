filepath = 'strategies/backtest/renko_smiio_supertrend_strategy.py'
with open(filepath, 'r') as f:
    content = f.read()

old = '        last_exit_bar = -1'
new = '        last_exit_bar = -1\n        last_exit_ts = None'
content = content.replace(old, new)

old = '                    last_exit_bar = i\n            elif current_direction == "short":'
new = '                    last_exit_bar = i\n                    last_exit_ts = ts\n            elif current_direction == "short":'
content = content.replace(old, new)

old = '                    last_exit_bar = i\n            if current_direction is None'
new = '                    last_exit_bar = i\n                    last_exit_ts = ts\n            if current_direction is None'
content = content.replace(old, new)

old = '            if current_direction is None and i > last_exit_bar + 1 and last_exit_bar != i:'
new = '            if current_direction is None and i > last_exit_bar + 1 and ts != last_exit_ts:'
content = content.replace(old, new)

old = '            if pending is not None and current_direction is None and i > last_exit_bar + 1 and last_exit_bar != i:'
new = '            if pending is not None and current_direction is None and i > last_exit_bar + 1 and ts != last_exit_ts:'
content = content.replace(old, new)

with open(filepath, 'w') as f:
    f.write(content)

print('Fix applied')
for line in content.split('\n'):
    if 'last_exit' in line:
        print(repr(line))
