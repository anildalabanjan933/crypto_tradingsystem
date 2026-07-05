#!/bin/bash
cd /home/anildalabanjan933/crypto_tradingsystem
source .venv/bin/activate

# Kill existing screens if running
screen -S live_s2 -X quit 2>/dev/null
screen -S live_s4 -X quit 2>/dev/null

sleep 2

# Start fresh screens
screen -dmS live_s2 bash -c "cd /home/anildalabanjan933/crypto_tradingsystem && source .venv/bin/activate && python3 run_live_trading_s2.py"
screen -dmS live_s4 bash -c "cd /home/anildalabanjan933/crypto_tradingsystem && source .venv/bin/activate && python3 run_live_trading_s4.py"

echo "S2 and S4 started"
screen -ls
