import subprocess, re, sys

print("="*70)
print("1. FULL TRACEBACK FROM LOG")
print("="*70)
try:
    with open("logs/dashboard.log") as f:
        content = f.read()
    blocks = re.findall(r"Traceback \(most recent call last\):.*?(?:Error|Exception)[^\n]*", content, re.DOTALL)
    if blocks:
        for b in blocks[-3:]:
            print(b)
            print("-"*70)
    else:
        print("No traceback blocks found.")
except Exception as e:
    print(f"Could not read log: {e}")

print("="*70)
print("2. SEARCH FOR 'import dashboard' / 'from dashboard' REFERENCES")
print("="*70)
try:
    result = subprocess.run(
        ["grep", "-n", "import dashboard\\|from dashboard", "dashboard/streamlit_app.py"],
        capture_output=True, text=True
    )
    print(result.stdout if result.stdout else "No matches found.")
except Exception as e:
    print(f"grep failed: {e}")

print("="*70)
print("3. PY_COMPILE CHECK")
print("="*70)
result = subprocess.run(
    [sys.executable, "-m", "py_compile", "dashboard/streamlit_app.py"],
    capture_output=True, text=True
)
if result.returncode == 0:
    print("OK: no syntax errors.")
else:
    print("COMPILE ERROR:")
    print(result.stderr)

print("="*70)
print("4. CHECK sys.path / cwd ASSUMPTIONS (os.getcwd, sys.path.insert, subprocess cwd=)")
print("="*70)
result = subprocess.run(
    ["grep", "-n", "sys.path.insert\\|subprocess.run(\\[.*dashboard\\|cwd=", "dashboard/streamlit_app.py"],
    capture_output=True, text=True
)
print(result.stdout if result.stdout else "No matches found.")
