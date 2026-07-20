#!/bin/bash
REPO=/home/anildalabanjan933/crypto_trading_system
cd $REPO

# Activate venv
source .venv/bin/activate

# Ensure dependencies installed
pip install -r requirements.txt -q

# Ensure logs folder exists
mkdir -p logs

# Load API keys from .env
set -a; source .env; set +a

# Kill ALL existing screens
screen -S live_s2 -X quit 2>/dev/null
screen -S live_s4 -X quit 2>/dev/null
screen -S dashboard -X quit 2>/dev/null
screen -S testmember1_s2 -X quit 2>/dev/null
screen -S testmember1_s4 -X quit 2>/dev/null
sleep 2

# Start fresh screens using venv python directly
screen -dmS live_s2 bash -c "cd $REPO && set -a && source $REPO/.env && set +a && $REPO/.venv/bin/python3 scripts/signal_replay_s2.py >> logs/live_trading_s2.log 2>&1"
screen -dmS live_s4 bash -c "cd $REPO && set -a && source $REPO/.env && set +a && $REPO/.venv/bin/python3 scripts/signal_replay_s4.py >> logs/live_trading_s4.log 2>&1"

echo "S2 and S4 started"
screen -dmS testmember1_s2 bash -c "cd $REPO && set -a && source $REPO/.env && set +a && $REPO/.venv/bin/python3 scripts/signal_replay_testmember1_s2.py >> logs/live_trading_testmember1_s2.log 2>&1"
screen -dmS testmember1_s4 bash -c "cd $REPO && set -a && source $REPO/.env && set +a && $REPO/.venv/bin/python3 scripts/signal_replay_testmember1_s4.py >> logs/live_trading_testmember1_s4.log 2>&1"
screen -S dashboard -dm bash -c "cd $REPO && $REPO/.venv/bin/python -m streamlit run dashboard/streamlit_app.py --server.port 8501 --server.address 0.0.0.0 >> logs/dashboard.log 2>&1" 
screen -ls
