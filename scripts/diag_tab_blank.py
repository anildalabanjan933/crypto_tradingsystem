import subprocess, time, os, sys

r = subprocess.run(["pgrep","-f","streamlit run dashboard/streamlit_app.py"], capture_output=True, text=True)
pids = [p for p in r.stdout.split() if p]
PID = None
for p in pids:
    try:
        with open(f"/proc/{p}/cmdline") as f:
            cmd = f.read()
        if "streamlit" in cmd and "python3" in cmd:
            PID = p
            break
    except Exception:
        continue

if not PID:
    print("Could not auto-detect streamlit PID.")
    sys.exit(1)

print(f"Target PID: {PID}")
print("="*70)
print("Dumping py-spy stack 6 times over next 18 seconds.")
print("NOW: click Trading tab, then Backtest, Analysis, Today - one after another.")
print("="*70)

for i in range(6):
    time.sleep(3)
    print(f"\n--- DUMP {i+1} at t={(i+1)*3}s ---")
    result = subprocess.run(["sudo","py-spy","dump","--pid",PID], capture_output=True, text=True)
    print(result.stdout if result.stdout else result.stderr)

print("="*70)
print("LOG FILE STATUS")
print("="*70)
log_path = "logs/dashboard.log"
if os.path.exists(log_path):
    st = os.stat(log_path)
    print(f"Size: {st.st_size} bytes, mtime: {time.ctime(st.st_mtime)}")

print("="*70)
print("LAST 20 LINES OF LOG (post-dump)")
print("="*70)
result = subprocess.run(["tail","-20",log_path], capture_output=True, text=True)
print(result.stdout)
