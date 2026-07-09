content = open('dashboard/streamlit_app.py', encoding='utf-8').read()
bad = 'input="1\n1\n"'
good = 'input="1\\n1\\n"'
fixed = content.replace(bad, good)
open('dashboard/streamlit_app.py', 'w', encoding='utf-8').write(fixed)
print('FIXED')
