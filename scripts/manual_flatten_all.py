#!/usr/bin/env python3
"""
manual_flatten_all.py - EMERGENCY MANUAL FLATTEN
Closes all open positions across S4, S4V2, S4V3 using existing
OrderManager.close_position() logic. Requires typed confirmation.
Does NOT touch SL orders, signal CSVs, or engine state - position
close only. Added 05-Oct-2026 per Claude go-live report Section 3(g).
"""
import os, sys
sys.path.insert(0, "/home/anildalabanjan7/crypto_tradingsystem")
os.chdir("/home/anildalabanjan7/crypto_tradingsystem")
from dotenv import load_dotenv
load_dotenv()
from engine.order_manager import OrderManager
from scripts.cts_env import IS_TESTNET

BOTS = [
    {"name": "S4",   "api_key": os.getenv("S4_API_KEY", ""),   "api_secret": os.getenv("S4_API_SECRET", "")},
    {"name": "S4V2", "api_key": os.getenv("S4V2_API_KEY", ""), "api_secret": os.getenv("S4V2_API_SECRET", "")},
    {"name": "S4V3", "api_key": os.getenv("S4V3_API_KEY", ""), "api_secret": os.getenv("S4V3_API_SECRET", "")},
]

def main():
    env_label = "TESTNET" if IS_TESTNET else "PRODUCTION (REAL MONEY)"
    print(f"=== MANUAL FLATTEN ALL - environment: {env_label} ===")
    print("This will CLOSE ALL OPEN POSITIONS for S4, S4V2, S4V3.")
    confirm = input("Type FLATTEN to confirm: ").strip()
    if confirm != "FLATTEN":
        print("Aborted - no action taken.")
        return

    for bot in BOTS:
        if not bot["api_key"] or not bot["api_secret"]:
            print(f"[{bot['name']}] SKIPPED - missing API key/secret")
            continue
        om = OrderManager(bot["api_key"], bot["api_secret"], testnet=IS_TESTNET)
        pos = om.get_position()
        if not pos.get("success"):
            print(f"[{bot['name']}] get_position FAILED: {pos.get('error')}")
            continue
        size = pos.get("size", 0)
        direction = pos.get("direction", "FLAT")
        if size == 0 or direction == "FLAT":
            print(f"[{bot['name']}] Already FLAT - nothing to close")
            continue
        close_side = "sell" if direction == "LONG" else "buy"
        print(f"[{bot['name']}] Position: {direction} size={size} - closing with side={close_side}...")
        result = om.close_position(size=abs(size), side=close_side)
        if result.get("success"):
            print(f"[{bot['name']}] CLOSED successfully at avg_fill_price={result.get('avg_fill_price')}")
        else:
            print(f"[{bot['name']}] CLOSE FAILED: {result.get('error')} - MANUAL INTERVENTION REQUIRED")

if __name__ == "__main__":
    main()
