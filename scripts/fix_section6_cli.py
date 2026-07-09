import re
content = open('dashboard/streamlit_app.py').read()
old = '"python", "run_single_strategy.py"'
new = '"python", "scripts/run_backtest_cli.py"'
fixed = content.replace(old, new)
open('dashboard/streamlit_app.py', 'w').write(fixed)
print('FIXED')
