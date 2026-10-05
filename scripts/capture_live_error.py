import subprocess, time, sys

print("Watching logs/dashboard.log for 20 seconds...")
print("NOW: go to browser and click Trading tab, then Backtest, Analysis, Today.")
print("-"*70)

proc = subprocess.Popen(
    ["tail", "-F", "-n", "0", "logs/dashboard.log"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)

start = time.time()
lines = []
while time.time() - start < 20:
    line = proc.stdout.readline()
    if line:
        lines.append(line)
proc.terminate()

print("="*70)
print("CAPTURED OUTPUT:")
print("="*70)
if lines:
    print("".join(lines))
else:
    print("No new log lines were written during this window.")

print("="*70)
print("ERROR/TRACEBACK LINES ONLY:")
print("="*70)
err_lines = [l for l in lines if "Error" in l or "Traceback" in l or "Uncaught" in l]
if err_lines:
    print("".join(err_lines))
else:
    print("No error/traceback lines found in this window.")
