#!/usr/bin/env python3
import shutil, datetime, py_compile, sys

FILE = "strategies/backtest/renko_smiio_supertrend_strategy.py"
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup = f"{FILE}.bak_bug8_{ts}"

with open(FILE, "r") as f:
    src = f.read()

def replace_once(src, old, new, label):
    count = src.count(old)
    if count != 1:
        print(f"ABORT: anchor '{label}' found {count} times (expected 1)")
        sys.exit(1)
    return src.replace(old, new, 1)

anchor1 = """        _idx_arr[_idx_arr > _max_idx] = _max_idx
        renko_raw['timestamp'] = _ts_values[_idx_arr]
        return renko_raw"""
new1 = """        _idx_arr[_idx_arr > _max_idx] = _max_idx
        renko_raw['timestamp'] = _ts_values[_idx_arr]
        renko_raw['real_close'] = closes[_idx_arr]
        return renko_raw"""
src = replace_once(src, anchor1, new1, "attach real_close")

anchor2 = """        closes    = df['renko_close'].values
        renko_dir = df['renko_dir'].values"""
new2 = """        closes    = df['renko_close'].values
        real_closes = df['real_close'].values
        renko_dir = df['renko_dir'].values"""
src = replace_once(src, anchor2, new2, "expose real_closes")

anchor3 = """                    'signal_type': 'EXIT',
                    'price':       self._apply_slippage(close, 'long', False),
                    'timestamp':   ts,
                    'sl_price':    close - box,"""
new3 = """                    'signal_type': 'EXIT',
                    'price':       self._apply_slippage(real_closes[i], 'long', False),
                    'timestamp':   ts,
                    'sl_price':    close - box,"""
src = replace_once(src, anchor3, new3, "EXIT long price")

anchor4 = """                    'signal_type': 'EXIT',
                    'price':       self._apply_slippage(close, 'short', False),
                    'timestamp':   ts,
                    'sl_price':    close + box,"""
new4 = """                    'signal_type': 'EXIT',
                    'price':       self._apply_slippage(real_closes[i], 'short', False),
                    'timestamp':   ts,
                    'sl_price':    close + box,"""
src = replace_once(src, anchor4, new4, "EXIT short price")

anchor5 = """                        'signal_type': 'ENTRY',
                        'price':       self._apply_slippage(close, 'long', True),
                        'timestamp':   ts,
                        'sl_price':    close - box * 2,"""
new5 = """                        'signal_type': 'ENTRY',
                        'price':       self._apply_slippage(real_closes[i], 'long', True),
                        'timestamp':   ts,
                        'sl_price':    close - box * 2,"""
src = replace_once(src, anchor5, new5, "ENTRY long price")

anchor6 = """                        'signal_type': 'ENTRY',
                        'price':       self._apply_slippage(close, 'short', True),
                        'timestamp':   ts,
                        'sl_price':    close + box * 2,"""
new6 = """                        'signal_type': 'ENTRY',
                        'price':       self._apply_slippage(real_closes[i], 'short', True),
                        'timestamp':   ts,
                        'sl_price':    close + box * 2,"""
src = replace_once(src, anchor6, new6, "ENTRY short price")

shutil.copy(FILE, backup)
with open(FILE, "w") as f:
    f.write(src)

py_compile.compile(FILE, doraise=True)
print(f"PATCHED OK. Backup: {backup}")
