#!/usr/bin/env python3
import sys, time, shutil, py_compile, collections

PATCHES = []

for fname, bot in [("scripts/signal_replay_s4.py","S4"),
                    ("scripts/signal_replay_s4v2.py","S4V2"),
                    ("scripts/signal_replay_s4v3.py","S4V3")]:
    old_a = f'CTS {bot} TRADE MISSED\\nWhat happened: Price band hit - testnet thin liquidity, expected fill price not reached\\n'
    new_a = 'TRADE SKIPPED (price band protection) - DELTA SIDE, no action needed\\nWhy: Bot tried to fill at expected price, but testnet market was too thin.\\n'
    PATCHES.append((fname, old_a, new_a, 3))

    old_b = 'Trade count reduced by 1\\nTime: {datetime.utcnow().isoformat()} UTC'
    new_b = 'Note: Trade count reduced by 1 - expected band-protection behavior, not a bug. For real price accuracy, check Production Fill table.\\nTime: {datetime.utcnow().isoformat()} UTC'
    PATCHES.append((fname, old_b, new_b, 3))

    old_c = f'CTS {bot} - Position Closed on Exchange\\n'
    new_c = 'TRADE ALREADY CLOSED - SYSTEM SIDE, no action needed\\nWhy: Exchange shows FLAT - NO TRADE OPEN. Closed outside bot logic (SL, manual, or exchange event). Bot updated its own records to match.\\n'
    PATCHES.append((fname, old_c, new_c, 1))

PATCHES.append(("engine/order_manager.py",
    'CTS BAD FILL DESPITE BAND - AUTO-CLOSING\\n',
    'TRADE CLOSED EARLY BY MISTAKE (bad-fill guard) - SYSTEM SIDE, fixed 9-Oct\\nWhy: Our own safety check wrongly thought a GOOD fill was bad and closed it.\\n',
    1))

PATCHES.append(("scripts/sl_safety_monitor.py",
    " RECOVERED - SL WAS MISSING, AUTO-PLACED SUCCESSFULLY\\n",
    " - STOP-LOSS FIXED BY ITSELF - SYSTEM SIDE, no action needed\\nWhy: Safety monitor found a missing stop-loss and placed it again.\\n",
    1))

PATCHES.append(("scripts/watchdog_capital.py",
    "big loss, unknown cause",
    "big balance drop - SYSTEM SIDE, action needed, please check dashboard",
    1))

PATCHES.append(("bot_watchdog.sh",
    "Status : DOWN - restarting now",
    "Status : Bot stopped, auto-restarting now - SYSTEM SIDE, no action needed",
    1))

PATCHES.append(("scripts/margin_monitor.py",
    "Action: Top up this subaccount before next signal fires",
    "ACCOUNT SIDE, action needed: Add funds to this subaccount before next trade fires",
    1))

PATCHES.append(("scripts/renko_state_engine.py",
    "times. Engine still running via polling. Check VM if alerts stop.",
    "times - SYSTEM SIDE, just watching. Engine still working fine using backup method. Only worry if alerts stop completely.",
    1))

by_file = collections.defaultdict(list)
for fname, old, new, expect_n in PATCHES:
    by_file[fname].append((old, new, expect_n))

for fname, items in by_file.items():
    s = open(fname).read()
    for old, new, expect_n in items:
        n = s.count(old)
        if n != expect_n:
            print(f"ABORT: {fname} - expected {expect_n}x, found {n}x for: {old[:50]!r}")
            sys.exit(1)

ts = time.strftime("%Y%m%d_%H%M%S")
for fname, items in by_file.items():
    shutil.copy(fname, f"{fname}.bak_wording_{ts}")
    s = open(fname).read()
    for old, new, _ in items:
        s = s.replace(old, new)
    open(fname, "w").write(s)
    if fname.endswith(".py"):
        py_compile.compile(fname, doraise=True)
    print(f"patched OK: {fname}")
print("DONE. Text-only changes. Restart bots to pick up new wording (safe anytime, no logic changed).")
