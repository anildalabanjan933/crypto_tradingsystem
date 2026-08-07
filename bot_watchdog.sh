#!/bin/bash
export HOME=/home/anildalabanjan933
export USER=anildalabanjan933
export LOGNAME=anildalabanjan933
export XDG_RUNTIME_DIR=/run/user/$(id -u anildalabanjan933)
export SCREENDIR=/run/screen/S-anildalabanjan933
export TERM=xterm
cd /home/anildalabanjan933/crypto_trading_system

REPO=/home/anildalabanjan933/crypto_trading_system
ALERT_FILE=$REPO/logs/watchdog_alert_sent.txt

send_telegram() {
    local msg=$1
    local token=$(grep TELEGRAM_BOT_TOKEN $REPO/.env | cut -d= -f2)
    local chat=$(grep TELEGRAM_CHAT_ID $REPO/.env | cut -d= -f2)
    if [ -n "$token" ] && [ -n "$chat" ]; then
        curl -s -X POST "https://api.telegram.org/bot${token}/sendMessage"             -d "chat_id=${chat}"             -d "text=${msg}"             -d "parse_mode=HTML" > /dev/null 2>&1
    fi
}

check_and_start() {
    local name=$1
    local script=$2
    local log=$3
    local alert_key=$REPO/logs/watchdog_down_${name}.txt
    if ! /usr/bin/screen -list 2>/dev/null | grep -q "$name"; then
        # Send Telegram alert only once per 30 minutes per screen
        local alert_ts_file=$REPO/logs/watchdog_alert_${name}.txt
        local now_ts=$(date +%s)
        local last_alert=0
        [ -f "$alert_ts_file" ] && last_alert=$(cat "$alert_ts_file")
        local diff=$((now_ts - last_alert))
        if [ $diff -gt 1800 ]; then
            local msg="⚠️ CTS WATCHDOG ALERT%0A━━━━━━━━━━━━━━━━━━%0AScreen : ${name}%0AScript : ${script}%0AStatus : DOWN - restarting now%0ATime   : $(date -u +%Y-%m-%dT%H:%M:%S) UTC%0A━━━━━━━━━━━━━━━━━━"
            send_telegram "$msg"
            echo "$now_ts" > "$alert_ts_file"
            echo "[$(date -u +%Y-%m-%dT%H:%M:%S)] DOWN alert sent for $name" >> logs/maintenance.log
        fi
        /usr/bin/screen -dmS "$name" /bin/bash -c "cd /home/anildalabanjan933/crypto_trading_system && .venv/bin/python3 $script >> $log 2>&1"
        echo "[$(date -u +%Y-%m-%dT%H:%M:%S)] Started $name" >> logs/maintenance.log
    fi
}

check_and_start live_s4v2 scripts/signal_replay_s4v2.py logs/live_trading_s4v2.log
check_and_start live_s4 scripts/signal_replay_s4.py logs/live_trading_s4.log
check_and_start testmember1_s4v2 scripts/signal_replay_testmember1_s4v2.py logs/live_trading_testmember1_s4v2.log
check_and_start testmember1_s4 scripts/signal_replay_testmember1_s4.py logs/live_trading_testmember1_s4.log
check_and_start signal_generator scripts/renko_state_engine.py logs/renko_state_engine.log
check_and_start boundary_watcher scripts/boundary_watcher.py logs/boundary_watcher.log
