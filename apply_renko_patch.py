import sys
from ast import parse

PATH = "scripts/renko_state_engine.py"
with open(PATH, "r") as f:
    content = f.read()

lines = content.split("\n")

def find_line(substr, start=0):
    for i in range(start, len(lines)):
        if substr in lines[i]:
            return i
    return -1

def indent_of(line):
    return line[:len(line) - len(line.lstrip(" "))]

anchor_idx = find_line('_ws_state={"last_s2_tf"')
if anchor_idx == -1:
    print("ABORT: _ws_state anchor not found. No file written.")
    sys.exit(1)

base_indent = indent_of(lines[anchor_idx])
helper_lines = [
    base_indent + "def _throttled_download(_min_gap=20):",
    base_indent + "    _now_dl = time.time()",
    base_indent + "    if _now_dl - _ws_state.get(\"last_dl\", 0) >= _min_gap:",
    base_indent + "        update_market_data()",
    base_indent + "        _ws_state[\"last_dl\"] = _now_dl",
    base_indent + "        return True",
    base_indent + "    return False",
]
lines[anchor_idx+1:anchor_idx+1] = helper_lines
print(f"Helper inserted after line {anchor_idx+1} (0-indexed), indent len={len(base_indent)}")

def patch_retry_block(var, label, tf_minutes):
    unique_log = f"[ENGINE] {label} data not caught up yet"
    log_idx = find_line(unique_log)
    if log_idx == -1:
        print(f"ABORT: log marker not found for {label}. No file written.")
        sys.exit(1)
    start_idx = -1
    for i in range(log_idx, max(log_idx-15, -1), -1):
        if "for _retry in range(6):" in lines[i]:
            start_idx = i
            break
    if start_idx == -1:
        print(f"ABORT: start marker not found for {label}. No file written.")
        sys.exit(1)
    end_idx = -1
    for i in range(log_idx, log_idx+4):
        if "time.sleep([2,5,10,20,30,60][_retry])" in lines[i]:
            end_idx = i
            break
    if end_idx == -1:
        print(f"ABORT: end marker not found for {label}. No file written.")
        sys.exit(1)
    ind = indent_of(lines[start_idx])
    cap_sec = tf_minutes*60 - 300
    new_block = [
        f"{ind}_start_{var} = time.time()",
        f"{ind}_cap_sec_{var} = {cap_sec}",
        f"{ind}_fixed_waits_{var} = [2,5,10,20,30,60]",
        f"{ind}_i_{var} = 0",
        f"{ind}_caught_up = False",
        f"{ind}while time.time() - _start_{var} < _cap_sec_{var}:",
        f"{ind}    _caught_up = {var}.last_1m_ts is not None and {var}.last_1m_ts.to_pydatetime().replace(tzinfo=None) >= _dt - __import__('datetime').timedelta(minutes=1)",
        f"{ind}    if _caught_up:",
        f"{ind}        break",
        f"{ind}    if _throttled_download():",
        f"{ind}        append_new_candles({var})",
        f"{ind}        _caught_up = {var}.last_1m_ts is not None and {var}.last_1m_ts.to_pydatetime().replace(tzinfo=None) >= _dt - __import__('datetime').timedelta(minutes=1)",
        f"{ind}        if _caught_up:",
        f"{ind}            break",
        f"{ind}    _wait_{var} = _fixed_waits_{var}[_i_{var}] if _i_{var} < len(_fixed_waits_{var}) else 30",
        f"{ind}    _i_{var} += 1",
        f'{ind}    log.info(f"[ENGINE] {label} data not caught up yet, retry {{_i_{var}}} (elapsed={{int(time.time()-_start_{var})}}s)")',
        f"{ind}    time.sleep(_wait_{var})",
        f"{ind}if not _caught_up:",
        f'{ind}    log.critical(f"[ENGINE] {label} boundary {{_dt}} STILL not caught up after {cap_sec}s safety cap - firing on best-available data")',
    ]
    lines[start_idx:end_idx+1] = new_block
    print(f"{label} retry block patched: lines {start_idx}-{end_idx} replaced with {len(new_block)} new lines (cap={cap_sec}s)")

patch_retry_block("s4", "S4", 120)
patch_retry_block("s4v2", "S4V2", 30)
patch_retry_block("s4v3", "S4V3", 240)

new_content = "\n".join(lines)
try:
    parse(new_content)
except SyntaxError as e:
    print(f"ABORT: syntax error after patch: {e}. No file written.")
    sys.exit(1)

with open(PATH, "w") as f:
    f.write(new_content)

print("OK: helper inserted + 3 retry blocks patched. Syntax verified. File written.")
