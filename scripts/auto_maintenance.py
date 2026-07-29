#!/usr/bin/env python3
"""
auto_maintenance.py
Runs automatically - no manual action needed ever.
1. Clean pycache if > 5MB or monthly
2. Trim logs if > 10MB each
3. Clean old output reports (keep last 5 per type)
4. Disk alert if > 70%
"""
import os, glob, shutil, time, logging
from datetime import datetime, timezone

BASE = '/home/anildalabanjan933/crypto_trading_system'
LOG  = os.path.join(BASE, 'logs', 'maintenance.log')

logging.basicConfig(
    filename=LOG,
    level=logging.INFO,
    format='%(asctime)s %(message)s'
)

def log(msg):
    logging.info(msg)
    print(msg)

def get_size_mb(path):
    total = 0
    if os.path.isfile(path):
        return os.path.getsize(path) / 1024 / 1024
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except:
                pass
    return total / 1024 / 1024

# ── 1. PYCACHE CLEAN ─────────────────────────────────────────
def clean_pycache():
    pycache_dirs = []
    for root, dirs, files in os.walk(BASE):
        if '.venv' in root:
            continue
        for d in dirs:
            if d == '__pycache__':
                pycache_dirs.append(os.path.join(root, d))

    total_mb = sum(get_size_mb(d) for d in pycache_dirs)

    # Clean if > 5MB or if last clean was > 30 days ago
    marker = os.path.join(BASE, 'logs', 'last_pycache_clean.txt')
    last_clean = 0
    if os.path.exists(marker):
        try:
            last_clean = float(open(marker).read().strip())
        except:
            pass

    days_since = (time.time() - last_clean) / 86400
    should_clean = total_mb > 5 or days_since > 30

    if should_clean:
        cleaned = 0
        for d in pycache_dirs:
            try:
                shutil.rmtree(d)
                cleaned += 1
            except:
                pass
        open(marker, 'w').write(str(time.time()))
        log(f"[MAINTENANCE] Pycache cleaned: {cleaned} dirs | {total_mb:.2f}MB freed | days_since={days_since:.0f}")
    else:
        log(f"[MAINTENANCE] Pycache OK: {total_mb:.2f}MB | {days_since:.0f} days since last clean")

# ── 2. LOG TRIM ───────────────────────────────────────────────
def trim_logs():
    log_files = glob.glob(os.path.join(BASE, 'logs', '*.log'))
    for lf in log_files:
        size_mb = get_size_mb(lf)
        if size_mb > 10:
            # Keep last 5000 lines
            lines = open(lf).readlines()
            kept = lines[-5000:]
            open(lf, 'w').writelines(kept)
            log(f"[MAINTENANCE] Log trimmed: {os.path.basename(lf)} | {size_mb:.1f}MB → kept last 5000 lines")
        else:
            log(f"[MAINTENANCE] Log OK: {os.path.basename(lf)} | {size_mb:.2f}MB")

# ── 3. OUTPUT CLEANUP ─────────────────────────────────────────
def clean_system_journals():
    """Clean systemd journal logs keeping only 100MB"""
    try:
        import subprocess
        result = subprocess.run(
            ['sudo', 'journalctl', '--vacuum-size=100M'],
            capture_output=True, text=True, timeout=30
        )
        log(f"[MAINTENANCE] Journal cleanup: {result.stderr.strip().split(chr(10))[-1]}")
    except Exception as e:
        log(f"[MAINTENANCE] Journal cleanup failed: {e}")

def clean_junk_files():
    """Remove .bak* and .lock files from repo permanently."""
    import glob
    patterns = ['**/*.bak*', '**/*.lock', '*.bak*', '*.lock']
    removed = 0
    for pattern in patterns:
        for f in glob.glob(os.path.join(BASE, pattern), recursive=True):
            # Never delete log files or .env
            if '.env' in f or 'logs/' in f:
                continue
            try:
                os.remove(f)
                removed += 1
            except:
                pass
    if removed > 0:
        log(f"[MAINTENANCE] Junk files cleaned: {removed} .bak/.lock files removed")
    else:
        log(f"[MAINTENANCE] Junk files: clean")

def clean_output():
    output_dir = os.path.join(BASE, 'output')
    if not os.path.exists(output_dir):
        return

    # Group files by type prefix
    patterns = {
        'backtest_report_S2':     'backtest_report_RenkoReversal*.html',
        'backtest_report_S4':     'backtest_report_RenkoSMIIO*.html',
        'trade_log_S2':           'trade_log_RenkoReversal*.csv',
        'trade_log_S4':           'trade_log_RenkoSMIIO*.csv',
        'optimization_S2':        'optimization_results_RenkoReversal*.html',
        'optimization_S4':        'optimization_results_RenkoSMIIO*.html',
        'comparison_S2':          'comparison_report_S2_*.html',
        'comparison_S4':          'comparison_report_S4_*.html',
    }

    total_deleted = 0
    for label, pattern in patterns.items():
        files = sorted(glob.glob(os.path.join(output_dir, pattern)))
        if len(files) > 5:
            to_delete = files[:-5]  # keep last 5
            for f in to_delete:
                try:
                    os.remove(f)
                    total_deleted += 1
                except:
                    pass
            log(f"[MAINTENANCE] Output cleaned: {label} | deleted {len(to_delete)} old files | kept 5")

    output_mb = get_size_mb(output_dir)
    log(f"[MAINTENANCE] Output folder: {output_mb:.1f}MB | deleted {total_deleted} files total")

# ── 4. DISK CHECK ─────────────────────────────────────────────
def check_disk():
    import shutil
    total, used, free = shutil.disk_usage('/')
    pct = used / total * 100
    free_gb = free / 1024**3
    if pct > 80:
        log(f"[MAINTENANCE] DISK ERROR: {pct:.1f}% used | {free_gb:.1f}GB free - ACTION NEEDED")
    elif pct > 70:
        log(f"[MAINTENANCE] DISK WARNING: {pct:.1f}% used | {free_gb:.1f}GB free - monitor closely")
    else:
        log(f"[MAINTENANCE] Disk OK: {pct:.1f}% used | {free_gb:.1f}GB free")

# ── RUN ALL ───────────────────────────────────────────────────
log(f"[MAINTENANCE] Starting auto maintenance - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
clean_pycache()
clean_system_journals()
trim_logs()
clean_output()
clean_junk_files()
check_disk()
log(f"[MAINTENANCE] Auto maintenance complete")

# ── REGENERATE SIGNAL CSVs ────────────────────────────────────
log(f"[MAINTENANCE] Regenerating signal CSVs for S2 and S4...")
import subprocess, sys
result = subprocess.run(
    [sys.executable, "scripts/generate_signals.py"],
    timeout=300, capture_output=True, text=True
)
if result.returncode == 0:
    log(f"[MAINTENANCE] Signal CSVs regenerated successfully")
else:
    log(f"[MAINTENANCE] Signal CSV regeneration failed: {result.stderr[-200:]}")

# ── BOX_SIZE DRIFT CHECK ────────────────────────────────────
log(f"[MAINTENANCE] Checking box_size drift (engine vs backtest)...")
result2 = subprocess.run(
    [sys.executable, "scripts/check_box_drift.py"],
    timeout=120, capture_output=True, text=True
)
log(f"[MAINTENANCE] Box drift check output: {result2.stdout.strip()}")
if result2.returncode != 0:
    log(f"[MAINTENANCE] Box drift check FAILED: {result2.stderr[-200:]}")

# Auto restart bots after maintenance
import subprocess
subprocess.run(["/bin/bash", "/home/anildalabanjan933/crypto_trading_system/bot_watchdog.sh"])

