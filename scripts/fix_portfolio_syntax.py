content = open('dashboard/streamlit_app.py').read()
content = content.replace('input="1\\n1\\n"', 'input="1\n1\n"')
open('dashboard/streamlit_app.py', 'w').write(content)
print('FIXED')
