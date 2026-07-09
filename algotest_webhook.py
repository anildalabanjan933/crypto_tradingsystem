import os
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
    }
}

ACCESS_TOKEN = "n7FJcMHANHN4F8HdqbU5QMDJn5JO79K9"

def post_signal(strategy, direction, signal_type):
    try:
        url = WEBHOOKS[strategy][direction][signal_type]
        if not url:
            print(f"[ALGOTEST] WARNING: No URL for {strategy} {direction} {signal_type}")
            return
        alert_name = "Entry" if signal_type == "entry" else "Exit"
        payload = {"access_token": ACCESS_TOKEN, "alert_name": alert_name}
        response = requests.post(url, json=payload, timeout=10)
        print(f"[ALGOTEST] {strategy} {direction} {signal_type} | Status: {response.status_code} | Response: {response.text}")
    except Exception as e:
        print(f"[ALGOTEST] ERROR: {e}")

if __name__ == "__main__":
    post_signal("S2", "BUY", "entry")
    post_signal("S2", "BUY", "exit")
    post_signal("S4", "BUY", "entry")
    post_signal("S4", "BUY", "exit")
