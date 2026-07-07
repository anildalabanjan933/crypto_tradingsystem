content = open('engine/optimizer.py', 'r').read()
old = """    PARAM_NAME_MAP = {
        'atr_length': 'st_atr_length',
        'factor': 'st_factor',
        # SMIIO
        'smiio_length': 'smiio_longlen',
        'smiio_signal': 'smiio_siglen',
        'smiio_avoid_entry_above': 'smiio_avoid_entry_above',
        # Renko — ADD THESE (were missing, caused identical RENKO results too)
        'renko_timeframe': 'renko_timeframe',
        'renko_box_pct': 'renko_box_pct',
        'renko_box': 'renko_box',"""
new = """    PARAM_NAME_MAP = {
        'st_atr_length': 'st_atr_length',
        'st_factor': 'st_factor',
        'smiio_shortlen': 'smiio_shortlen',
        'smiio_siglen': 'smiio_siglen',
        'renko_timeframe': 'renko_timeframe',
        'renko_box': 'renko_box',"""
open('engine/optimizer.py', 'w').write(content.replace(old, new))
print('DONE' if 'st_atr_length' in open('engine/optimizer.py').read() else 'FAILED')
