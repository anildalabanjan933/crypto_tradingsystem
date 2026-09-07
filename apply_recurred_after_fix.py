import sys
from ast import parse

PATH = "scripts/issue_tracker.py"
with open(PATH, "r") as f:
    content = f.read()

lines = content.split("\n")

def find_line(substr, start=0):
    for i in range(start, len(lines)):
        if substr in lines[i]:
            return i
    return -1

# --- Patch 1: _ANOMALY_TAGS + new constant ---
anchor1 = find_line('_ANOMALY_TAGS = {"BOT_RESTART"')
if anchor1 == -1:
    print("ABORT: _ANOMALY_TAGS anchor not found. No file written.")
    sys.exit(1)

old_line1 = lines[anchor1]
if old_line1.strip() != '_ANOMALY_TAGS = {"BOT_RESTART", "ENGINE_RESTART", "CLOSE_LOSS_CAP_STAGE", "CLOSE_FAILED_MANUAL_REQUIRED", "CONFIRMATION_LAG"}':
    print("ABORT: _ANOMALY_TAGS line content does not match exactly. No file written.")
    print(f"Found: {old_line1!r}")
    sys.exit(1)

new_block1 = [
    'GATE_LOCKOUT_FIX_DEPLOYED_UTC = __import__("datetime").datetime(2026, 9, 7, 16, 3, 0)',
    '_ANOMALY_TAGS = {"BOT_RESTART", "ENGINE_RESTART", "CLOSE_LOSS_CAP_STAGE", "CLOSE_FAILED_MANUAL_REQUIRED", "CONFIRMATION_LAG", "RECURRED_AFTER_FIX"}',
]
lines[anchor1:anchor1+1] = new_block1
print(f"Patch 1 applied at line {anchor1}: _ANOMALY_TAGS updated + GATE_LOCKOUT_FIX_DEPLOYED_UTC added")

# --- Patch 2: conf_lag_flag block, independent RECURRED_AFTER_FIX check ---
anchor2 = find_line('if lag_min > TF_MIN.get(bot, 120) and abs(pnl_gap) > CONF_LAG_PNL_GAP_THRESHOLD:')
if anchor2 == -1:
    print("ABORT: conf_lag_flag anchor not found. No file written.")
    sys.exit(1)

next_line = lines[anchor2+1]
if 'conf_lag_flag = "CONFIRMATION_LAG"' not in next_line:
    print("ABORT: expected conf_lag_flag assignment line not found after anchor. No file written.")
    print(f"Found: {next_line!r}")
    sys.exit(1)

ind = lines[anchor2][:len(lines[anchor2]) - len(lines[anchor2].lstrip(" "))]
insert_after = anchor2 + 2  # after the conf_lag_flag = "CONFIRMATION_LAG" line

new_block2 = [
    f'{ind}_tf_ratio = lag_min / TF_MIN.get(bot, 120) if TF_MIN.get(bot, 120) else 0',
    f'{ind}_gate_lockout_sig = abs(_tf_ratio - round(_tf_ratio)) < 0.02 and round(_tf_ratio) >= 1',
    f'{ind}if _gate_lockout_sig and lv_exit_dt.to_pydatetime() >= GATE_LOCKOUT_FIX_DEPLOYED_UTC:',
    f'{ind}    conf_lag_flag = (conf_lag_flag + "|RECURRED_AFTER_FIX") if conf_lag_flag else "RECURRED_AFTER_FIX"',
    f'{ind}    _append_event(bot, "RECURRED_AFTER_FIX",',
    f'{ind}                   f"Gate-lockout lag signature recurred AFTER fix deploy "',
    f'{ind}                   f"({{GATE_LOCKOUT_FIX_DEPLOYED_UTC}}): entry_ts={{entry_ts}} "',
    f'{ind}                   f"exit_ts={{exit_ts}} lag_min={{lag_min:.1f}} ratio={{_tf_ratio:.3f}}")',
]
lines[insert_after:insert_after] = new_block2
print(f"Patch 2 applied after line {insert_after-1}: independent RECURRED_AFTER_FIX check inserted ({len(new_block2)} lines)")

new_content = "\n".join(lines)
try:
    parse(new_content)
except SyntaxError as e:
    print(f"ABORT: syntax error after patch: {e}. No file written.")
    sys.exit(1)

with open(PATH, "w") as f:
    f.write(new_content)

print("OK: both patches applied. Syntax verified. File written.")
