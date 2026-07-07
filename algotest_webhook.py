import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

WEBHOOKS = {
    "S2": {
        "BUY":  {"entry": os.getenv("ALGOTEST_WEBHOOK_S2_BUY_ENTRY"),  "exit": os.getenv("ALGOTEST_WEBHOOK_S2_BUY_EXIT")},
        "SELL": {"entry": os.getenv("ALGOTEST_WEBHOOK_S2_SELL_ENTRY"), "exit": os.getenv("ALGOTEST_WEBHOOK_S2_SELL_EXIT")},
    },
    "S4": {
        "BUY":  {"entry": os.getenv("ALGOTEST_WEBHOOK_S4_BUY_ENTRY"),  "exit": os.getenv("ALGOTEST_WEBHOOK_S4_BUY_EXIT")},
        "SELL": {"entry": os.getenv("ALGOTEST_WEBHOOK_S4_SELL_ENTRY"), "exit": os.getenv("ALGOTEST_WEBHOOK_S4_SELL_EXIT")},
    },
}

def post_signal(strategy, direction, signal_type):
    """
    strategy: 'S2' or 'S4'
    direction: 'BUY' or 'SELL'
    signal_type: 'entry' or 'exit'
    """
    try:
        url = WEBHOOKS[strategy][direction][signal_type]
        if not url:
            print(f"[ALGOTEST] WARNING: No URL configured for {strategy} {direction} {signal_type}")
            return
        payload = {
            "access_token": "n7FJcMHANHN4F8HdqbU5QMDJn5JO79K9",
            "alert_name": "Entry" if signal_type == "entry" else "Exit"
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=10)
        print(f"[ALGOTEST] {strategy} {direction} {signal_type.upper()} posted | Status: {response.status_code} | Response: {response.text}")
    except Exception as e:
        print(f"[ALGOTEST] ERROR posting {strategy} {direction} {signal_type}: {e}")
