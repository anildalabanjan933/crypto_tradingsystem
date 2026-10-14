#!/bin/bash
HB=/home/anildalabanjan7/crypto_tradingsystem/logs/watchdog_top_heartbeat.txt
NOW=$(date +%s)
LAST=$(cat "$HB" 2>/dev/null || echo 0)
AGE=$((NOW - LAST))
if [ "$AGE" -gt 180 ]; then
  echo "$(date): bot_watchdog.sh stale, age=${AGE}s" >> /home/anildalabanjan7/crypto_tradingsystem/logs/top_supervisor_alert.log
  systemctl restart cts-bots.service
fi
