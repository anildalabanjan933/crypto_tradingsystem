content = open('dashboard/streamlit_app.py').read()
old = '"python", "run_optimization.py"'
new = '"python", "scripts/run_optimization_cli.py"'
fixed = content.replace(old, new)
open('dashboard/streamlit_app.py', 'w').write(fixed)
print('FIXED')
