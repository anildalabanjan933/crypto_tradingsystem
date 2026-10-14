#!/usr/bin/env python3
import shutil, time, py_compile, sys

TS = str(int(time.time()))

def replace_once(src, anchor, new, label, filename):
    count = src.count(anchor)
    if count != 1:
        print(f"ABORT [{filename}] - anchor '{label}' found {count} times (expected 1)")
        sys.exit(1)
    return src.replace(anchor, new)

def patch_file(filepath, patches):
    with open(filepath, 'r', encoding='utf-8') as f:
        src = f.read()
    backup_path = f"{filepath}.bak_bug8_{TS}"
    shutil.copy(filepath, backup_path)
    print(f"Backup created: {backup_path}")
    for anchor, new, label in patches:
        src = replace_once(src, anchor, new, label, filepath)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(src)
    try:
        py_compile.compile(filepath, doraise=True)
        print(f"py_compile OK: {filepath}")
    except py_compile.PyCompileError as e:
        print(f"PY_COMPILE FAILED: {filepath}\n{e}")
        sys.exit(1)

file1 = "strategies/backtest/renko_breakout_strategy.py"
file1_patches = [
    (
        "        renko_df['timestamp'] = renko_df['bar_index'].apply(\n            lambda idx: timestamps[idx] if idx < len(timestamps) else timestamps[-1]\n        )\n        renko_df = renko_df.reset_index(drop=True)",
        "        renko_df['timestamp'] = renko_df['bar_index'].apply(\n            lambda idx: timestamps[idx] if idx < len(timestamps) else timestamps[-1]\n        )\n        renko_df['real_close'] = renko_df['bar_index'].apply(\n            lambda idx: closes[idx] if idx < len(closes) else closes[-1]\n        )\n        renko_df = renko_df.reset_index(drop=True)",
        "attach real_close column (file1)"
    ),
    (
        "            row      = renko_df.iloc[i]\n            close    = row['renko_close']\n            bar_time = row['timestamp']",
        "            row      = renko_df.iloc[i]\n            close    = row['renko_close']\n            real_close = row['real_close']\n            bar_time = row['timestamp']",
        "expose real_close in loop (file1)"
    ),
    (
        "                        'exit_type'  : 'ST_FLIP_RED',\n                        'bar_index'  : i,\n                        'timestamp'  : bar_time,\n                        'price'      : close,",
        "                        'exit_type'  : 'ST_FLIP_RED',\n                        'bar_index'  : i,\n                        'timestamp'  : bar_time,\n                        'price'      : real_close,",
        "EXIT long price fix (file1)"
    ),
    (
        "                        'exit_type'  : 'ST_FLIP_GREEN',\n                        'bar_index'  : i,\n                        'timestamp'  : bar_time,\n                        'price'      : close,",
        "                        'exit_type'  : 'ST_FLIP_GREEN',\n                        'bar_index'  : i,\n                        'timestamp'  : bar_time,\n                        'price'      : real_close,",
        "EXIT short price fix (file1)"
    ),
    (
        "                            'entry_type'  : 'BUY_A',\n                            'bar_index'   : i,\n                            'timestamp'   : bar_time,\n                            'price'       : close,",
        "                            'entry_type'  : 'BUY_A',\n                            'bar_index'   : i,\n                            'timestamp'   : bar_time,\n                            'price'       : real_close,",
        "ENTRY long price fix (file1)"
    ),
    (
        "                                'entry_type'   : 'SELL_A',\n                                'bar_index'    : i,\n                                'timestamp'    : bar_time,\n                                'price'        : close,",
        "                                'entry_type'   : 'SELL_A',\n                                'bar_index'    : i,\n                                'timestamp'    : bar_time,\n                                'price'        : real_close,",
        "ENTRY short price fix (file1)"
    ),
]

file2 = "strategies/backtest/renko_pattern_breakout_strategy.py"
file2_patches = [
    (
        "        renko_raw['timestamp'] = renko_raw['bar_index'].apply(\n            lambda idx: timestamps[idx] if idx < len(timestamps) else timestamps[-1]\n        )\n        return renko_raw",
        "        renko_raw['timestamp'] = renko_raw['bar_index'].apply(\n            lambda idx: timestamps[idx] if idx < len(timestamps) else timestamps[-1]\n        )\n        renko_raw['real_close'] = renko_raw['bar_index'].apply(\n            lambda idx: closes[idx] if idx < len(closes) else closes[-1]\n        )\n        return renko_raw",
        "attach real_close column (file2)"
    ),
    (
        "        closes     = df['renko_close'].values.astype(float)\n        renko_dir  = df['renko_dir'].values",
        "        closes     = df['renko_close'].values.astype(float)\n        real_closes = df['real_close'].values.astype(float)\n        renko_dir  = df['renko_dir'].values",
        "expose real_closes array (file2)"
    ),
    (
        "                open_positions.append({\n                    'direction':   'long',\n                    'entry_price': c,\n                    'entry_ts':    ts_pd,\n                    'entry_bar':   i,\n                })\n                entry_allowed_long = ts_pd + pd.Timedelta(hours=cooldown_hours)",
        "                open_positions.append({\n                    'direction':   'long',\n                    'entry_price': real_closes[i],\n                    'entry_ts':    ts_pd,\n                    'entry_bar':   i,\n                })\n                entry_allowed_long = ts_pd + pd.Timedelta(hours=cooldown_hours)",
        "LONG entry_price fix (file2)"
    ),
    (
        "                open_positions.append({\n                    'direction':   'short',\n                    'entry_price': c,\n                    'entry_ts':    ts_pd,\n                    'entry_bar':   i,\n                })\n                entry_allowed_short = ts_pd + pd.Timedelta(hours=cooldown_hours)",
        "                open_positions.append({\n                    'direction':   'short',\n                    'entry_price': real_closes[i],\n                    'entry_ts':    ts_pd,\n                    'entry_bar':   i,\n                })\n                entry_allowed_short = ts_pd + pd.Timedelta(hours=cooldown_hours)",
        "SHORT entry_price fix (file2)"
    ),
    (
        "                    trades.append({\n                        'timestamp':      pos['entry_ts'],\n                        'exit_timestamp': ts_pd,\n                        'signal_type':    'trade',\n                        'direction':      pos['direction'],\n                        'price':          pos['entry_price'],\n                        'exit_price':     c,\n                        'entry_type':     'PATTERN_BREAKOUT',\n                        'sl_price':       0.0,\n                        'exit_reason':    'ST_flip',\n                    })",
        "                    trades.append({\n                        'timestamp':      pos['entry_ts'],\n                        'exit_timestamp': ts_pd,\n                        'signal_type':    'trade',\n                        'direction':      pos['direction'],\n                        'price':          pos['entry_price'],\n                        'exit_price':     real_closes[i],\n                        'entry_type':     'PATTERN_BREAKOUT',\n                        'sl_price':       0.0,\n                        'exit_reason':    'ST_flip',\n                    })",
        "EXIT price fix mid-loop (file2)"
    ),
    (
        "            last_c  = closes[last_i]",
        "            last_c  = real_closes[last_i]",
        "end-of-data close fix (file2)"
    ),
]

file3 = "strategies/backtest/renko_reversal_strategy.py"
file3_patches = [
    (
        "        # Map timestamps\n        renko_raw['timestamp'] = renko_raw['bar_index'].apply(\n            lambda idx: timestamps[idx] if idx < len(timestamps) else timestamps[-1]\n        )\n\n        # Add Supertrend",
        "        # Map timestamps\n        renko_raw['timestamp'] = renko_raw['bar_index'].apply(\n            lambda idx: timestamps[idx] if idx < len(timestamps) else timestamps[-1]\n        )\n        renko_raw['real_close'] = renko_raw['bar_index'].apply(\n            lambda idx: closes[idx] if idx < len(closes) else closes[-1]\n        )\n\n        # Add Supertrend",
        "attach real_close column (file3)"
    ),
    (
        "        renko_close = df['renko_close'].values\n        renko_dir   = df['renko_dir'].values",
        "        assert 'real_close' in df.columns, \"BUG: real_close missing after Supertrend/Swing\"\n        renko_close = df['renko_close'].values\n        real_closes = df['real_close'].values\n        renko_dir   = df['renko_dir'].values",
        "expose real_closes array + survival check (file3)"
    ),
    (
        "            if current_direction == 'long' and prev_st == -1 and st == 1 and r_dir == -1:\n                exit_price = self._apply_slippage(close, 'long', is_entry=False)",
        "            if current_direction == 'long' and prev_st == -1 and st == 1 and r_dir == -1:\n                exit_price = self._apply_slippage(real_closes[i], 'long', is_entry=False)",
        "EXIT long slippage fix (file3)"
    ),
    (
        "            elif current_direction == 'short' and prev_st == 1 and st == -1 and r_dir == 1:\n                exit_price = self._apply_slippage(close, 'short', is_entry=False)",
        "            elif current_direction == 'short' and prev_st == 1 and st == -1 and r_dir == 1:\n                exit_price = self._apply_slippage(real_closes[i], 'short', is_entry=False)",
        "EXIT short slippage fix (file3)"
    ),
    (
        "            if buy_edge and current_direction != 'long':\n                entry_price = self._apply_slippage(close, 'long', is_entry=True)",
        "            if buy_edge and current_direction != 'long':\n                entry_price = self._apply_slippage(real_closes[i], 'long', is_entry=True)",
        "ENTRY long slippage fix (file3)"
    ),
    (
        "            elif sell_edge and current_direction != 'short':\n                entry_price = self._apply_slippage(close, 'short', is_entry=True)",
        "            elif sell_edge and current_direction != 'short':\n                entry_price = self._apply_slippage(real_closes[i], 'short', is_entry=True)",
        "ENTRY short slippage fix (file3)"
    ),
]

if __name__ == "__main__":
    patch_file(file1, file1_patches)
    patch_file(file2, file2_patches)
    patch_file(file3, file3_patches)
    print("ALL 3 FILES PATCHED SUCCESSFULLY.")
