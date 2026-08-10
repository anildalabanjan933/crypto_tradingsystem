# engine/order_manager.py
# Responsibility: Place, close, and query orders on Delta Exchange
# Uses Delta Exchange REST API (testnet or live)

import hashlib
import hmac
import time
import requests
import json
import logging
from engine.telegram_alert import send_alert
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

    def _post(self, path: str, payload: dict, retries: int = 3) -> dict:
        body    = json.dumps(payload)
        url     = self.base_url + path
        for attempt in range(1, retries + 1):
            try:
                headers = self._sign("POST", path, "", body)
                resp = self.session.post(url, data=body, headers=headers, timeout=(3, 27))
                return resp.json()
            except Exception as e:
                logging.warning(f"[OrderManager] POST attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    time.sleep(2 * attempt)
        logging.error(f"[OrderManager] POST failed after {retries} attempts: {path}")
        send_alert(f"CTS API FAIL\nPOST failed after {retries} attempts\nPath: {path}\nCheck Delta API status")
        return {"success": False, "error": "max_retries_exceeded"}

    def _delete(self, path: str, payload: dict) -> dict:
        body    = json.dumps(payload)
        headers = self._sign("DELETE", path, "", body)
        url     = self.base_url + path
        resp    = self.session.delete(url, data=body, headers=headers, timeout=(3, 27))
        return resp.json()

    def _get(self, path: str, params: dict = None, retries: int = 3) -> dict:
        params     = params or {}
        sorted_items = sorted(params.items())
        query_str  = "&".join(f"{k}={v}" for k, v in sorted_items)
        query_part = ("?" + query_str) if query_str else ""
        url        = self.base_url + path + query_part
        for attempt in range(1, retries + 1):
            try:
                headers = self._sign("GET", path, query_part, "")
                resp = self.session.get(url, headers=headers, timeout=(3, 27))
                return resp.json()
            except Exception as e:
                logging.warning(f"[OrderManager] GET attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    time.sleep(2 * attempt)
        logging.error(f"[OrderManager] GET failed after {retries} attempts: {path}")
        send_alert(f"CTS API FAIL\nGET failed after {retries} attempts\nPath: {path}\nCheck Delta API status")
        return {"success": False, "error": "max_retries_exceeded"}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _get_avg_fill_price(self, order_id: int) -> float:
        """Fetch real fill price for an order from /v2/fills.
        The order-placement response has NO average_fill_price field
        (confirmed against official Delta API schema) - must query fills.
        Retries up to 3 times with short delay - fills endpoint can lag
        a few hundred ms behind order confirmation (race condition fix)."""
        import time as _t
        for _attempt in range(6):
            resp = self._get("/v2/fills", {"product_ids": str(self.PRODUCT_ID), "page_size": 50})
            if resp.get("success"):
                fills = [f for f in resp.get("result", []) if str(f.get("order_id")) == str(order_id)]
                if fills:
                    total_size = sum(float(f["size"]) for f in fills)
                    if total_size > 0:
                        weighted = sum(float(f["price"]) * float(f["size"]) for f in fills)
                        return weighted / total_size
            if _attempt < 5:
                _t.sleep(0.5 * (_attempt + 1))
        logging.warning(f"[OrderManager] avg_fill_price: no fills found for order_id={order_id} after 6 retries")
        return 0.0

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

        logging.info(f"[OrderManager] Placing {side.upper()} market order | size={size} lots")
        resp = self._post("/v2/orders", payload)

        if resp.get("success"):
            result = resp["result"]
            logging.info(f"[OrderManager] Order placed | id={result['id']} state={result['state']}")
            _avg = self._get_avg_fill_price(result["id"])
            return {
                "success":      True,
                "order_id":     result["id"],
                "state":        result["state"],
                "side":         result["side"],
                "size":         result["size"],
                "filled_price": result.get("limit_price", "market"),
                "avg_fill_price": float(_avg) if _avg else 0.0
            }
        else:
            logging.error(f"[OrderManager] Order FAILED: {resp.get('error')}")
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

        logging.info(f"[OrderManager] Closing position | {side.upper()} {size} lots (reduce_only)")
        resp = self._post("/v2/orders", payload)

        if resp.get("success"):
            result = resp["result"]
            logging.info(f"[OrderManager] Close order placed | id={result['id']} state={result['state']}")
            _avg2 = self._get_avg_fill_price(result["id"])
            return {
                "success":  True,
                "order_id": result["id"],
                "state":    result["state"],
                "avg_fill_price": float(_avg2) if _avg2 else 0.0
            }
        else:
            logging.error(f"[OrderManager] Close FAILED: {resp.get('error')}")
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
            mark   = result.get("mark_price", "0")
            return {
                "success":     True,
                "size":        size,
                "entry_price": float(entry) if entry else 0.0,
                "exit_price":  float(mark) if mark else 0.0,
                "direction":   "LONG" if size > 0 else ("SHORT" if size < 0 else "FLAT")
            }
        else:
            return {"success": False, "size": 0, "entry_price": 0.0, "direction": "UNKNOWN"}

    def cancel_all_orders(self) -> dict:
        """Cancel all open orders for BTCUSD."""
        payload = {"product_id": self.PRODUCT_ID}
        logging.info("[OrderManager] Cancelling all open orders for BTCUSD")
        resp = self._delete("/v2/orders/all", payload)
        if resp.get("success"):
            logging.info("[OrderManager] All orders cancelled")
        else:
            logging.error(f"[OrderManager] Cancel all failed: {resp.get('error')}")
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


    def place_stop_loss_order(self, direction: str, entry_price: float, sl_pct: float = 2.0) -> dict:
        """
        Place a stop market order as SL on an open position.
        Works AFTER position is open - no bracket_order_immediate_execution issue.
        direction  : "long" or "short"
        entry_price: actual fill price from get_position()
        sl_pct     : stop loss % from entry (default 5% - wide safety net only)
        """
        if entry_price <= 0:
            logging.error(f"[OrderManager] SL skipped - invalid entry_price={entry_price}")
            return {"success": False, "error": "invalid_entry_price"}

        if direction == "long":
            sl_price = round(entry_price * (1 - sl_pct / 100), 1)
            side = "sell"
        else:
            sl_price = round(entry_price * (1 + sl_pct / 100), 1)
            side = "buy"

        payload = {
            "product_symbol": self.PRODUCT_SYMBOL,
            "product_id":     self.PRODUCT_ID,
            "side":           side,
            "size":           100,
            "order_type":     "market_order",
            "stop_order_type": "stop_loss_order",
            "stop_price":     str(sl_price),
            "reduce_only":    True,
            "close_on_trigger": True
        }

        logging.info(f"[OrderManager] Placing stop SL | direction={direction} entry={entry_price} sl={sl_price} ({sl_pct}%)")
        resp = self._post("/v2/orders", payload)

        if resp.get("success"):
            result = resp["result"]
            logging.info(f"[OrderManager] Stop SL placed | sl_price={sl_price} order_id={result.get('id')}")
            return {"success": True, "sl_price": sl_price, "order_id": result.get("id")}
        else:
            logging.error(f"[OrderManager] Stop SL FAILED: {resp.get('error')}")
            return {"success": False, "error": resp.get("error")}
