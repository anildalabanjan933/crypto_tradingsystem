import re
content = open('scripts/run_backtest_cli.py').read()
old = 'if result:\n    print("Backtest complete")\n    metrics = result.get(\'metrics\', {})\n    for k, v in metrics.items():\n        print(f"{k}: {v}")'
new = 'if result:\n    print("Backtest complete")\n    metrics = result.get(\'metrics\', {})\n    skip_keys = [\'equity_curve\',\'equity_curve_inr\',\'drawdown_series\']\n    for k, v in metrics.items():\n        if k not in skip_keys:\n            print(f"{k}: {v}")'
open('scripts/run_backtest_cli.py','w').write(content.replace(old,new))
print('FIXED')
