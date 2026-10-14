#!/bin/bash
REPO=/home/anildalabanjan933/crypto_trading_system
cd "$REPO"
OUT="$REPO/logs/live_verification_watch.log"

tail -F -n0 logs/renko_state_engine.log logs/confirmation_lag_events.csv logs/issue_tracker_trades.csv logs/maintenance.log 2>/dev/null | \
grep --line-buffered -iE "candle closed|critical_covered|REST reconcile|ENTRY|EXIT|CONFIRMATION_LAG|FLIP_FIRE|heartbeat STALE|Started signal_generator" | \
while read -r line; do
    echo "[$(date -u +%Y-%m-%dT%H:%M:%S)] $line" >> "$OUT"
done
