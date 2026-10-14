"""
Shared helper for bot replay scripts to check exchange maintenance status
before taking a new ENTRY. Written by scripts/maintenance_watcher.py.

Fails OPEN (returns False / allow entry) on any read error, per design
decision - a flag-file read glitch must never itself block trading.
This must be used ONLY on ENTRY branches, never on EXIT/close branches.
"""
import os

FLAG_FILE = "logs/maintenance_active.txt"


def check_maintenance_flag() -> bool:
    """
    Returns True if maintenance is currently active (entries should be
    skipped), False otherwise - including on any error (fail-open).
    """
    try:
        return os.path.exists(FLAG_FILE)
    except Exception:
        return False
