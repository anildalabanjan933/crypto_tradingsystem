src = open('strategies/backtest/renko_reversal_strategy.py', encoding='utf-8').read()
for i, line in enumerate(src.splitlines(), 1):
    if 'st_factor' in line:
        print(i, line)
