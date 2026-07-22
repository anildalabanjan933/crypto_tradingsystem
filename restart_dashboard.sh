#!/bin/bash
cd /home/anildalabanjan933/crypto_trading_system
screen -S dashboard -X quit 2>/dev/null
sleep 1
screen -dmS dashboard bash -c "cd /home/anildalabanjan933/crypto_trading_system && .venv/bin/python3 -m streamlit run dashboard/streamlit_app.py --server.port 8501 --server.address 0.0.0.0"
echo "Dashboard restarted"
screen -list
