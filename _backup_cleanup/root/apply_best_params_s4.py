path = 'strategies/backtest/renko_smiio_supertrend_strategy.py'
content = open(path).read()

replacements = [
    ("self.renko_box = kwargs.get('renko_box', 0.0020)", "self.renko_box_pct = kwargs.get('renko_box_pct', 0.001)"),
    ("self.st_atr_length = kwargs.get('st_atr_length', 5)", "self.st_atr_length = kwargs.get('st_atr_length', 10)"),
    ("self.st_factor      = kwargs.get('st_factor',      2.0)", "self.st_factor      = kwargs.get('st_factor',      2.0)"),
    ("self.smiio_shortlen = kwargs.get('smiio_shortlen', 5)", "self.smiio_shortlen = kwargs.get('smiio_shortlen', 20)"),
    ("self.smiio_siglen   = kwargs.get('smiio_siglen',   5)", "self.smiio_siglen   = kwargs.get('smiio_siglen',   7)"),
]

changed = []
for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        changed.append(f'DONE: {old[:60]}')
    else:
        changed.append(f'NOT FOUND: {old[:60]}')

open(path, 'w').write(content)
for c in changed:
    print(c)
