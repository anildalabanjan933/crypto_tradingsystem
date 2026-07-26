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

# Trim large log files before start
for log in logs/live_trading_testmember1_s2.log logs/live_trading_testmember1_s4.log logs/live_trading_s2.log logs/live_trading_s4.log; do
    if [ -f "$log" ] && [ $(du -m "$log" | cut -f1) -gt 50 ]; then
        tail -2000 "$log" > "$log.tmp" && mv "$log.tmp" "$log"
        echo "Trimmed $log"
    fi
done

# Kill ALL existing screens
screen -S signal_generator -X quit 2>/dev/null
screen -S renko_engine -X quit 2>/dev/null
screen -S live_s2 -X quit 2>/dev/null
screen -S live_s4 -X quit 2>/dev/null
screen -S dashboard -X quit 2>/dev/null
screen -S testmember1_s2 -X quit 2>/dev/null
screen -S testmember1_s4 -X quit 2>/dev/null
sleep 2

# Start fresh screens using venv python directly
screen -dmS signal_generator bash -c "cd $REPO && set -a && source $REPO/.env && set +a && $REPO/.venv/bin/python3 scripts/renko_state_engine.py >> logs/renko_state_engine.log 2>&1"
screen -dmS live_s2 bash -c "cd $REPO && set -a && source $REPO/.env && set +a && $REPO/.venv/bin/python3 scripts/signal_replay_s2.py"
screen -dmS live_s4 bash -c "cd $REPO && set -a && source $REPO/.env && set +a && $REPO/.venv/bin/python3 scripts/signal_replay_s4.py"

echo "S2 and S4 started"
screen -dmS testmember1_s2 bash -c "cd $REPO && set -a && source $REPO/.env && set +a && $REPO/.venv/bin/python3 scripts/signal_replay_testmember1_s2.py"
screen -dmS testmember1_s4 bash -c "cd $REPO && set -a && source $REPO/.env && set +a && $REPO/.venv/bin/python3 scripts/signal_replay_testmember1_s4.py"
screen -S dashboard -dm bash -c "cd $REPO && $REPO/.venv/bin/python -m streamlit run dashboard/streamlit_app.py --server.port 8501 --server.address 0.0.0.0 >> logs/dashboard.log 2>&1"
screen -S today_trades -dm bash -c "cd $REPO && $REPO/.venv/bin/python -m streamlit run dashboard/today_trades_app.py --server.port 8502 --server.address 0.0.0.0 >> logs/today_trades.log 2>&1" 
screen -ls
