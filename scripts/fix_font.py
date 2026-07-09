content = open('dashboard/streamlit_app.py').read()
old = '.stApp { background-color: #ffffff; }'
new = '.stApp { background-color: #ffffff; }\n[data-testid="stMetricValue"] { font-size: 16px !important; }\n[data-testid="stMetricLabel"] { font-size: 12px !important; }'
content = content.replace(old, new)
open('dashboard/streamlit_app.py', 'w').write(content)
print('FONT SIZE FIXED')
