filepath = 'run_optimization.py'
with open(filepath, 'r') as f:
    content = f.read()

old_dist  = '"crossover_distance":      {"values": [0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 2.5]},'
new_dist  = '"crossover_distance":      {"values": [1.0, 1.5, 2.0, 2.5, 3.0]},'

old_count = '"crossover_count_limit":   {"values": [1, 2, 3]},'
new_count = '"crossover_count_limit":   {"values": [2, 3, 4, 5]},'

old_avoid = '"smiio_avoid_entry_above": {"values": [0.2, 0.3, 0.4, 0.5, 0.6]}'
new_avoid = '"smiio_avoid_entry_above": {"values": [20.0, 30.0, 40.0, 50.0, 60.0]}'

content = content.replace(old_dist, new_dist)
content = content.replace(old_count, new_count)
content = content.replace(old_avoid, new_avoid)

with open(filepath, 'w') as f:
    f.write(content)

print('Fix applied successfully')
for line in content.split('\n'):
    if any(x in line for x in ['crossover_distance', 'crossover_count_limit', 'smiio_avoid_entry_above']):
        print(line.strip())
