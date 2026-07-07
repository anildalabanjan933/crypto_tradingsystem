f = open('engine/optimizer.py', 'r')
content = f.read()
f.close()

old = "        'renko_box_pct': 'renko_box_pct',"
new = "        'renko_box_pct': 'renko_box_pct',\n        'renko_box': 'renko_box',"

content = content.replace(old, new)
f = open('engine/optimizer.py', 'w')
f.write(content)
f.close()
print('Fix done')
