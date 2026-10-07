#!/bin/bash
REPO="/home/anildalabanjan7/crypto_tradingsystem"
CSV="$REPO/data/orderbook_history.csv"
HTML="$REPO/reports/orderbook_report.html"
MAX_AGE=150

cd "$REPO" || exit 1
SCREEN_ALIVE=$(screen -ls | grep -c "orderbook_watch")

if [ "$SCREEN_ALIVE" -eq 0 ]; then
    echo "$(date -u +%FT%TZ) orderbook_watch screen not found, restarting"
    screen -dmS orderbook_watch bash -c "cd $REPO && python3 scripts/orderbook_watch.py"
    exit 0
fi

if [ -f "$CSV" ]; then
    NOW=$(date +%s)
    MTIME=$(stat -c %Y "$CSV")
    AGE=$((NOW - MTIME))
    if [ "$AGE" -gt "$MAX_AGE" ]; then
        echo "$(date -u +%FT%TZ) data stale (${AGE}s old), restarting orderbook_watch"
        screen -S orderbook_watch -X quit 2>/dev/null
        sleep 2
        screen -dmS orderbook_watch bash -c "cd $REPO && python3 scripts/orderbook_watch.py"
        if [ -f "$HTML" ]; then
            sed -i "/<\/style><\/head><body>/a <div style=\"background:#8b0000;color:white;padding:12px;font-weight:bold;\">STALE DATA DETECTED at $(date -u +%FT%TZ) \xe2\x80\x94 orderbook_watch was restarted. Figures above may be outdated.</div>" "$HTML"
        fi
    fi
fi
