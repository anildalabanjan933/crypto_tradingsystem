path = 'strategies/backtest/renko_reversal_strategy.py'
src = open(path, encoding='utf-8').read()
old = "self.st_factor     = kwargs.get('st_factor', 4.0)"
new = "self.st_factor     = kwargs.get('st_factor', 1.5)"
if old in src:
    src = src.replace(old, new)
    open(path, 'w', encoding='utf-8').write(src)
    print('FIXED: st_factor 4.0 -> 1.5')
else:
    print('NOT FOUND')
