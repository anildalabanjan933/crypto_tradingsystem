#!/usr/bin/env python3
"""
Dedicated BT runner for S4V4 (RenkoSMIIOSupertrendV4Strategy)
Independent file - no shared state with S4/S4V2/S4V3 BT.
"""
import subprocess
import sys

STRATEGY = "RenkoSMIIOSupertrendV4Strategy"
START = "2024-01-01"
END = "2026-09-14"

cmd = [
    sys.executable, "scripts/run_backtest_cli.py",
    "--strategy", STRATEGY,
    "--start", START,
    "--end", END,
]

print(f"=== Running S4V4 Backtest: {STRATEGY} | {START} to {END} ===")
subprocess.run(cmd, check=True)
