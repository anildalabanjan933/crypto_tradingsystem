import re

FILE = "dashboard/streamlit_app.py"
with open(FILE) as f:
    lines = f.readlines()

TABS = {
    "AUDIT":    (1459, 1467),
    "MONITOR":  (1468, 3344),
    "TRADING":  (3345, 4244),
    "BACKTEST": (4245, 5678),
    "ANALYSIS": (5679, 8561),
    "TODAY":    (8562, len(lines)),
}

risky_patterns = [
    (r'requests\.(get|post)\((?![^)]*timeout)', "HTTP call with NO timeout"),
    (r'time\.sleep\(', "blocking sleep()"),
    (r'while\s+True', "while True loop"),
    (r'get_position\(', "live position API call"),
    (r'get_fills\(|/v2/fills', "live fills API call"),
    (r'get_current_price\(', "live price fetch"),
]

print(f"{'TAB':10} {'LINES':15} ISSUES")
print("-"*70)
for tab, (start, end) in TABS.items():
    block = "".join(lines[start-1:end])
    hits = []
    for pat, desc in risky_patterns:
        for m in re.finditer(pat, block):
            ln = start + block[:m.start()].count("\n")
            hits.append(f"L{ln}:{desc}")
    print(f"{tab:10} {start}-{end:<10} {len(hits)} issue(s)")
    for h in hits:
        print(f"    -> {h}")
