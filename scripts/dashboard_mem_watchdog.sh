#!/bin/bash
# dashboard_mem_watchdog.sh - restart dashboard screen session if RSS exceeds 1GB
# or if total system swap usage exceeds 1GB
cd ~/crypto_tradingsystem
THRESHOLD_KB=1048576        # 1GB in KB (RSS)
SWAP_THRESHOLD_KB=1048576   # 1GB in KB (used swap)
while true; do
    screen -wipe > /dev/null 2>&1

    PID=$(pgrep -f "streamlit run dashboard/streamlit_app.py")
    RESTART=0
    REASON=""

    if [ -n "$PID" ]; then
        RSS=$(ps -o rss= -p "$PID" 2>/dev/null | tr -d ' ')
        if [ -n "$RSS" ] && [ "$RSS" -gt "$THRESHOLD_KB" ]; then
            RESTART=1
            REASON="RSS=${RSS}KB exceeds 1GB"
        fi
    fi

    SWAP_USED_KB=$(free | awk '/^Swap:/ {print $3}')
    if [ -n "$SWAP_USED_KB" ] && [ "$SWAP_USED_KB" -gt "$SWAP_THRESHOLD_KB" ] && [ -n "$PID" ]; then
        RESTART=1
        REASON="${REASON:+$REASON, }SwapUsed=${SWAP_USED_KB}KB exceeds 1GB"
    fi

    if [ "$RESTART" -eq 1 ]; then
        echo "$(date -u +%Y-%m-%dT%H:%M:%S) $REASON - restarting dashboard" >> logs/dashboard_mem_watchdog.log
        screen -S dashboard -X quit
        sleep 2
        screen -dmS dashboard bash -c 'set -a && source .env && set +a && export PYTHONPATH=$(pwd) && .venv/bin/python -m streamlit run dashboard/streamlit_app.py >> logs/dashboard.log 2>&1'
    fi
    sleep 300
done
