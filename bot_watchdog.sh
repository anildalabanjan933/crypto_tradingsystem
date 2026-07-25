#!/bin/bash
export HOME=/home/anildalabanjan933
export USER=anildalabanjan933
export LOGNAME=anildalabanjan933
export XDG_RUNTIME_DIR=/run/user/$(id -u anildalabanjan933)
export SCREENDIR=/run/screen/S-anildalabanjan933
export TERM=xterm
cd /home/anildalabanjan933/crypto_trading_system

check_and_start() {
    local name=$1
    local script=$2
    local log=$3
    if ! /usr/bin/screen -list 2>/dev/null | grep -q "$name"; then
        /usr/bin/screen -dmS "$name" /bin/bash -c "cd /home/anildalabanjan933/crypto_trading_system && .venv/bin/python3 $script >> $log 2>&1"
        echo "[$(date -u +%Y-%m-%dT%H:%M:%S)] Started $name" >> logs/maintenance.log
    fi
}

check_and_start live_s2 scripts/signal_replay_s2.py logs/live_trading_s2.log
check_and_start live_s4 scripts/signal_replay_s4.py logs/live_trading_s4.log
check_and_start testmember1_s2 scripts/signal_replay_testmember1_s2.py logs/live_trading_testmember1_s2.log
check_and_start testmember1_s4 scripts/signal_replay_testmember1_s4.py logs/live_trading_testmember1_s4.log
check_and_start signal_generator scripts/renko_state_engine.py logs/renko_state_engine.log
