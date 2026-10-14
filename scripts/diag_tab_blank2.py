import subprocess, time, os

PID = "303269"
PYSPY = os.path.expanduser("~/.local/bin/py-spy")

print(f"Target PID: {PID}")
print("="*70)
print("Dumping py-spy stack 6 times over next 18 seconds.")
print("NOW: click Trading tab, then Backtest, Analysis, Today - one after another.")
print("="*70)

for i in range(6):
    time.sleep(3)
    print(f"\n--- DUMP {i+1} at t={(i+1)*3}s ---")
    result = subprocess.run(["sudo", PYSPY, "dump", "--pid", PID], capture_output=True, text=True)
    print(result.stdout if result.stdout else result.stderr)
