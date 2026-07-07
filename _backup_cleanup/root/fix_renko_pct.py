import re

# Fix 1: run_optimization.py — change renko_box values to percentages
content = open('run_optimization.py', 'r').read()
old = """    "renko": {
        "renko_timeframe": {"values": ["1m", "5m", "15m", "30m", "1h", "2h"]},
        "renko_box":      {"values": [100, 150, 200, 250, 300, 350, 400]}
    }"""
new = """    "renko": {
        "renko_timeframe": {"values": ["1m", "5m", "15m", "30m", "1h", "2h"]},
        "renko_box_pct":   {"values": [0.0010, 0.0015, 0.0020, 0.0025, 0.0030, 0.0035, 0.0040]}
    }"""
result = content.replace(old, new)
open('run_optimization.py', 'w').write(result)
print('Fix 1 DONE' if 'renko_box_pct' in open('run_optimization.py').read() else 'Fix 1 FAILED')

# Fix 2: engine/optimizer.py — add renko_box_pct to PARAM_NAME_MAP
content = open('engine/optimizer.py', 'r').read()
old = """    PARAM_NAME_MAP = {
        'st_atr_length': 'st_atr_length',
        'st_factor': 'st_factor',
        'smiio_shortlen': 'smiio_shortlen',
        'smiio_siglen': 'smiio_siglen',
        'renko_timeframe': 'renko_timeframe',
        'renko_box': 'renko_box',
    }"""
new = """    PARAM_NAME_MAP = {
        'st_atr_length': 'st_atr_length',
        'st_factor': 'st_factor',
        'smiio_shortlen': 'smiio_shortlen',
        'smiio_siglen': 'smiio_siglen',
        'renko_timeframe': 'renko_timeframe',
        'renko_box': 'renko_box',
        'renko_box_pct': 'renko_box_pct',
    }"""
result = content.replace(old, new)
open('engine/optimizer.py', 'w').write(result)
print('Fix 2 DONE' if 'renko_box_pct' in open('engine/optimizer.py').read() else 'Fix 2 FAILED')
