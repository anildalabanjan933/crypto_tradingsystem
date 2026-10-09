#!/bin/bash
# dashboard_mem_watchdog.sh - restart dashboard screen session if RSS exceeds 1.5GB
cd ~/crypto_tradingsystem
THRESHOLD_KB=1572864  # 1.5GB in KB
while true; do
    PID=$(pgrep -f "streamlit run dashboard/streamlit_app.py")
    if [ -n "$PID" ]; then
        RSS=$(ps -o rss= -p "$PID" 2>/dev/null | tr -d ' ')
        if [ -n "$RSS" ] && [ "$RSS" -gt "$THRESHOLD_KB" ]; then
            echo "$(date -u +%Y-%m-%dT%H:%M:%S) RSS=${RSS}KB exceeds 1.5GB - restarting dashboard" >> logs/dashboard_mem_watchdog.log
            screen -S dashboard -X quit
            sleep 2
            screen -dmS dashboard bash -c 'set -a && source .env && set +a && export PYTHONPATH=$(pwd) && .venv/bin/python -m streamlit run dashboard/streamlit_app.py >> logs/dashboard.log 2>&1'
        fi
    fi
    sleep 300
done
