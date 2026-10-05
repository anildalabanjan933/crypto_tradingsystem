"""
CTS_ENV central config - single source of truth for environment switch.
Added 05-Oct-2026 - replaces scattered testnet=True / PRODUCT_ID=84 / LOT_SIZE=100.
"""
import os
from dotenv import load_dotenv

load_dotenv()

CTS_ENV = os.getenv("CTS_ENV", "testnet").strip().lower()
if CTS_ENV not in ("testnet", "production"):
    raise ValueError(f"CTS_ENV must be 'testnet' or 'production', got: {CTS_ENV}")

IS_TESTNET = (CTS_ENV == "testnet")

BASE_URL = (
    "https://cdn-ind.testnet.deltaex.org" if IS_TESTNET
    else "https://api.india.delta.exchange"
)

PRODUCT_ID = 84 if IS_TESTNET else 27   # BTCUSD, confirmed via Delta API 05-Oct-2026

LOT_SIZE = int(os.getenv("CTS_LOT_SIZE", "100"))
SL_FALLBACK_SIZE = LOT_SIZE
