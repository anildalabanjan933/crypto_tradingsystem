#!/bin/bash
cd /home/anildalabanjan933/crypto_trading_system
source .venv/bin/activate

# Kill existing screens if running
screen -S live_s2 -X quit 2>/dev/null
screen -S live_s4 -X quit 2>/dev/null

sleep 2

# Start fresh screens
screen -dmS live_s2 bash -c "cd /home/anildalabanjan933/crypto_trading_system && source .venv/bin/activate && python3 run_live_trading_s2.py > logs/live_trading_s2.log 2>&1"
screen -dmS live_s4 bash -c "cd /home/anildalabanjan933/crypto_trading_system && source .venv/bin/activate && python3 run_live_trading_s4.py > logs/live_trading_s4.log 2>&1"

echo "S2 and S4 started"
screen -ls
