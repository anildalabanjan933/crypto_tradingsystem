with open('strategies/backtest/renko_smiio_supertrend_strategy.py', 'r') as f:
    content = f.read()

checks = [
    ('last_exit_ts (re-entry fix)', 'last_exit_ts'),
    ('pending_set_bar (re-entry fix)', 'pending_set_bar'),
    ('renko_box (not pct)', 'self.renko_box = kwargs.get'),
    ('renko_box_pct (should be gone)', 'renko_box_pct'),
]

for label, keyword in checks:
    found = keyword in content
    status = 'FOUND' if found else 'NOT FOUND'
    print(label + ': ' + status)
