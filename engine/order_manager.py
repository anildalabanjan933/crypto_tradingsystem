# engine/order_manager.py
# Responsibility: Place, close, and query orders on Delta Exchange
# Uses Delta Exchange REST API (testnet or live)

import hashlib
import hmac
import time
import requests
import json
from datetime import datetime


class OrderManager:
    """
    Handles all order operations on Delta Exchange.

    Supports:
    - Place market orders (buy/sell)
    - Close position (reduce_only market order)
    - Get current position
    - Cancel all open orders for a product
    - Query order status by ID
    """

    PRODUCT_SYMBOL = "BTCUSD"
    PRODUCT_ID     = 84          # BTCUSD perpetual on Delta Exchange Testnet

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """
        Parameters
        ----------
        api_key    : str   Delta Exchange API key
        api_secret : str   Delta Exchange API secret
        testnet    : bool  True = demo testnet, False = live
        """
        self.api_key    = api_key
        self.api_secret = api_secret

        if testnet:
            self.base_url = "https://cdn-ind.testnet.deltaex.org"
        else:
            self.base_url = "https://api.india.delta.exchange"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent":   "python-rest-client"
        })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sign(self, method: str, path: str, query: str, body: str) -> dict:
        """Build signed request headers."""
        timestamp = str(int(time.time()))
        message   = method + timestamp + path + query + body
        signature = hmac.new(
            bytes(self.api_secret, "utf-8"),
            bytes(message,         "utf-8"),
            hashlib.sha256
        ).hexdigest()
        return {
            "api-key":      self.api_key,
            "timestamp":    timestamp,
            "signature":    signature,
            "Content-Type": "application/json",
            "User-Agent":   "python-rest-client"
        }

    def _post(self, path: str, payload: dict) -> dict:
        body    = json.dumps(payload)
        headers = self._sign("POST", path, "", body)
        url     = self.base_url + path
        resp    = self.session.post(url, data=body, headers=headers, timeout=(3, 27))
        return resp.json()

    def _delete(self, path: str, payload: dict) -> dict:
        body    = json.dumps(payload)
        headers = self._sign("DELETE", path, "", body)
        url     = self.base_url + path
        resp    = self.session.delete(url, data=body, headers=headers, timeout=(3, 27))
        return resp.json()

    def _get(self, path: str, params: dict = None) -> dict:
        params     = params or {}
        query_str  = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        query_part = ("?" + query_str) if query_str else ""
        headers    = self._sign("GET", path, query_part, "")
        url        = self.base_url + path
        resp       = self.session.get(url, params=params, headers=headers, timeout=(3, 27))
        return resp.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def place_market_order(self, side: str, size: int, client_order_id: str = None) -> dict:
        """
        Place a market order.

        Parameters
        ----------
        side            : "buy" or "sell"
        size            : number of lots (integer, e.g. 100)
        client_order_id : optional tag (max 32 chars)
        """
        payload = {
            "product_symbol": self.PRODUCT_SYMBOL,
            "product_id":     self.PRODUCT_ID,
            "side":           side,
            "size":           size,
            "order_type":     "market_order"
        }
        if client_order_id:
            payload["client_order_id"] = client_order_id[:32]

        print(f"[OrderManager] Placing {side.upper()} market order | size={size} lots")
        resp = self._post("/v2/orders", payload)

        if resp.get("success"):
            result = resp["result"]
            print(f"[OrderManager] Order placed | id={result['id']} state={result['state']}")
            return {
                "success":      True,
                "order_id":     result["id"],
                "state":        result["state"],
                "side":         result["side"],
                "size":         result["size"],
                "filled_price": result.get("limit_price", "market")
            }
        else:
            print(f"[OrderManager] Order FAILED: {resp.get('error')}")
            return {"success": False, "error": resp.get("error")}

    def close_position(self, size: int, side: str, client_order_id: str = None) -> dict:
        """
        Close an open position using a reduce_only market order.

        Parameters
        ----------
        size : lots to close (must equal open position size)
        side : "buy" to close a SHORT, "sell" to close a LONG
        """
        payload = {
            "product_symbol": self.PRODUCT_SYMBOL,
            "product_id":     self.PRODUCT_ID,
            "side":           side,
            "size":           size,
            "order_type":     "market_order",
            "reduce_only":    "true"
        }
        if client_order_id:
            payload["client_order_id"] = client_order_id[:32]

        print(f"[OrderManager] Closing position | {side.upper()} {size} lots (reduce_only)")
        resp = self._post("/v2/orders", payload)

        if resp.get("success"):
            result = resp["result"]
            print(f"[OrderManager] Close order placed | id={result['id']} state={result['state']}")
            return {
                "success":  True,
                "order_id": result["id"],
                "state":    result["state"]
            }
        else:
            print(f"[OrderManager] Close FAILED: {resp.get('error')}")
            return {"success": False, "error": resp.get("error")}

    def get_position(self) -> dict:
        """
        Get current BTCUSD position.

        Returns size (+ long / - short), entry_price, or size=0 if flat.
        """
        resp = self._get("/v2/positions", {"product_id": self.PRODUCT_ID})

        if resp.get("success"):
            result = resp.get("result", {})
            size   = result.get("size", 0)
            entry  = result.get("entry_price", "0")
            return {
                "success":     True,
                "size":        size,
                "entry_price": float(entry) if entry else 0.0,
                "direction":   "LONG" if size > 0 else ("SHORT" if size < 0 else "FLAT")
            }
        else:
            return {"success": True, "size": 0, "entry_price": 0.0, "direction": "FLAT"}

    def cancel_all_orders(self) -> dict:
        """Cancel all open orders for BTCUSD."""
        payload = {"product_id": self.PRODUCT_ID}
        print("[OrderManager] Cancelling all open orders for BTCUSD")
        resp = self._delete("/v2/orders/all", payload)
        if resp.get("success"):
            print("[OrderManager] All orders cancelled")
        else:
            print(f"[OrderManager] Cancel all failed: {resp.get('error')}")
        return resp

    def get_order_status(self, order_id: int) -> dict:
        """Get status of a specific order by ID."""
        resp = self._get(f"/v2/orders/{order_id}")
        if resp.get("success"):
            result = resp["result"]
            return {
                "success":       True,
                "order_id":      result["id"],
                "state":         result["state"],
                "filled_size":   result["size"] - result["unfilled_size"],
                "unfilled_size": result["unfilled_size"]
            }
        return {"success": False, "error": resp.get("error")}
