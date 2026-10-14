#!/usr/bin/env python3
"""Propose-only interface. renko_state_engine.py is the ONLY writer of logs/signals_*.csv."""
import os, re, csv, json, fcntl
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _label(csv_path):
    m = re.search(r"signals_(s[0-9a-z]+)\.csv$", os.path.basename(csv_path))
    return m.group(1) if m else None

def propose(csv_path, op):
    lab = _label(csv_path)
    if not lab:
        return False
    q = os.path.join(BASE, "logs", f"pending_patch_{lab}.jsonl")
    line = json.dumps(op, sort_keys=True, default=str)
    lk = open(q + ".lock", "a")
    fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
    try:
        if os.path.exists(q):
            with open(q) as f:
                if line in f.read().splitlines():
                    return True
        with open(q, "a") as f:
            f.write(line + "\n")
        return True
    finally:
        fcntl.flock(lk.fileno(), fcntl.LOCK_UN)
        lk.close()

def propose_diff(csv_path, rows):
    try:
        with open(csv_path) as f:
            have = {r[0] for r in csv.reader(f) if r}
    except FileNotFoundError:
        have = set()
    new = []
    for r in rows:
        r = list(r.values()) if isinstance(r, dict) else list(r)
        r = [str(x) for x in r]
        if r and r[0] not in have:
            new.append(r)
    if new:
        propose(csv_path, {"op": "append_closed", "rows": new})
    return len(new)
