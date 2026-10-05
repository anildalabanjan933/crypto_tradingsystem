# engine/order_manager.py
# Responsibility: Place, close, and query orders on Delta Exchange
# Uses Delta Exchange REST API (testnet or live)

import hashlib
import hmac
import time
import threading
import requests
import json
import logging
import os
import fcntl
from engine.telegram_alert import send_alert
from scripts.cts_env import PRODUCT_ID as _CTS_PRODUCT_ID, IS_TESTNET as _CTS_IS_TESTNET
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
    PRODUCT_ID     = _CTS_PRODUCT_ID   # resolved via CTS_ENV (scripts/cts_env.py)
    _ENTRY_BAND_TIERS = [250.0, 250.0, 500.0, 500.0, 750.0]
    _ALERT_COOLDOWN_SEC = 300  # 5 min - prevents Telegram flood on repeated API failures
    _ALERT_STATE_FILE = "logs/api_fail_alert_state.json"
    _alert_file_lock = threading.Lock()

    def __init__(self, api_key: str, api_secret: str, testnet: bool = _CTS_IS_TESTNET):
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

    def _throttled_alert(self, key: str, message: str):
        """Send CTS API FAIL alert max once per _ALERT_COOLDOWN_SEC per key,
        across all processes (file-based lock, prevents Telegram flood).
        Tracks failure count since last sent alert so a throttled alert
        still reports flapping failures (no extra Telegram messages added)."""
        now = time.time()
        send_now = True
        fail_count = 1
        with self._alert_file_lock:
            try:
                state = {}
                if os.path.exists(self._ALERT_STATE_FILE):
                    with open(self._ALERT_STATE_FILE, "r") as f:
                        fcntl.flock(f, fcntl.LOCK_SH)
                        try:
                            state = json.load(f)
                        except Exception:
                            state = {}
                        fcntl.flock(f, fcntl.LOCK_UN)
                entry = state.get(key, {"last_alert": 0, "count": 0})
                if not isinstance(entry, dict):
                    entry = {"last_alert": entry, "count": 0}
                entry["count"] = entry.get("count", 0) + 1
                last = entry.get("last_alert", 0)
                send_now = (now - last >= self._ALERT_COOLDOWN_SEC)
                if send_now:
                    fail_count = entry["count"]
                    entry["last_alert"] = now
                    entry["count"] = 0
                state[key] = entry
                os.makedirs(os.path.dirname(self._ALERT_STATE_FILE) or ".", exist_ok=True)
                with open(self._ALERT_STATE_FILE, "w") as f:
                    fcntl.flock(f, fcntl.LOCK_EX)
                    json.dump(state, f)
                    fcntl.flock(f, fcntl.LOCK_UN)
            except Exception as e:
                logging.warning(f"[OrderManager] alert throttle check failed: {e}")
        if not send_now:
            return
        send_alert(f"{message}\nFailures in last {self._ALERT_COOLDOWN_SEC // 60} min: {fail_count}")

    def _post(self, path: str, payload: dict, retries: int = 3) -> dict:
        body    = json.dumps(payload)
        url     = self.base_url + path
        for attempt in range(1, retries + 1):
            try:
                headers = self._sign("POST", path, "", body)
                resp = self.session.post(url, data=body, headers=headers, timeout=(3, 27))
                try:
                    return resp.json()
                except Exception as je:
                    logging.warning(f"[OrderManager] POST attempt {attempt}/{retries} JSON parse failed: {je} | status={resp.status_code} body={resp.text[:200]!r}")
                    raise
            except Exception as e:
                logging.warning(f"[OrderManager] POST attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    time.sleep(2 * attempt)
        logging.error(f"[OrderManager] POST failed after {retries} attempts: {path}")
        self._throttled_alert(f"POST:{path}", f"CTS API FAIL\nPOST failed after {retries} attempts\nPath: {path}\nCheck Delta API status")
        return {"success": False, "error": "max_retries_exceeded"}

    def _delete(self, path: str, payload: dict) -> dict:
        body    = json.dumps(payload)
        headers = self._sign("DELETE", path, "", body)
        url     = self.base_url + path
        resp    = self.session.delete(url, data=body, headers=headers, timeout=(3, 27))
        return resp.json()

    def _get_order_by_client_id(self, client_order_id: str):
        try:
            resp = self._get(f"/v2/orders/client_order_id/{client_order_id}", {}, retries=2)
            if resp.get("success"):
                result = resp.get("result")
                if result and result.get("id"):
                    return result
        except Exception as e:
            logging.warning(f"[OrderManager] _get_order_by_client_id failed for cid={client_order_id}: {e}")
        return None

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
                try:
                    return resp.json()
                except Exception as je:
                    logging.warning(f"[OrderManager] GET attempt {attempt}/{retries} JSON parse failed: {je} | status={resp.status_code} body={resp.text[:200]!r}")
                    raise
            except Exception as e:
                logging.warning(f"[OrderManager] GET attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    time.sleep(2 * attempt)
        logging.error(f"[OrderManager] GET failed after {retries} attempts: {path}")
        self._throttled_alert(f"GET:{path}", f"CTS API FAIL\nGET failed after {retries} attempts\nPath: {path}\nCheck Delta API status")
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

    def _get_order_commission(self, order_id: int) -> float:
        """Fetch total commission paid for an order from /v2/fills.
        Standalone read-only method - does not modify _get_avg_fill_price
        or any existing order logic. Returns 0.0 on any failure (safe default)."""
        try:
            resp = self._get("/v2/fills", {"product_ids": str(self.PRODUCT_ID), "page_size": 50})
            if resp.get("success"):
                fills = [f for f in resp.get("result", []) if str(f.get("order_id")) == str(order_id)]
                if fills:
                    return sum(float(f.get("commission", 0.0)) for f in fills)
        except Exception as _e:
            logging.warning(f"[OrderManager] _get_order_commission failed for order_id={order_id}: {_e}")
        return 0.0

    def place_limit_order_ioc(self, side: str, size: int, ref_price: float, band: float = 8.0, client_order_id: str = None) -> dict:
        """Place IOC limit order banded around ref_price to cap slippage.
        Buy: limit = ref_price + band (won't pay more than that)
        Sell: limit = ref_price - band (won't sell for less than that)
        If price has moved beyond band, order is skipped (unfilled) instead
        of chasing market price - caps worst-case slippage."""
        limit_price = round(ref_price + band, 1) if side == 'buy' else round(ref_price - band, 1)
        payload = {
            "product_symbol": self.PRODUCT_SYMBOL,
            "product_id":     self.PRODUCT_ID,
            "side":           side,
            "size":           size,
            "order_type":     "limit_order",
            "limit_price":    str(limit_price),
            "time_in_force":  "ioc"
        }
        if client_order_id:
            payload["client_order_id"] = client_order_id[:32]
        logging.info(f"[OrderManager] Placing {side.upper()} IOC limit | size={size} lots | ref={ref_price} band={band} limit={limit_price}")
        resp = self._post("/v2/orders", payload)
        if resp.get("success"):
            result = resp["result"]
            unfilled = int(result.get("unfilled_size", size))
            filled = size - unfilled
            if filled == 0:
                logging.warning(f"[OrderManager] IOC order id={result.get(chr(105)+chr(100))} FULLY UNFILLED - price moved beyond band, skipped")
                return {"success": False, "skipped": True, "reason": "unfilled_beyond_band", "order_id": result.get("id")}
            logging.info(f"[OrderManager] IOC order id={result.get(chr(105)+chr(100))} filled={filled}/{size}")
            _avg = self._get_avg_fill_price(result["id"])
            return {
                "success": True,
                "order_id": result["id"],
                "state": result["state"],
                "filled_size": filled,
                "unfilled_size": unfilled,
                "avg_fill_price": _avg
            }
        return {"success": False, "error": resp.get("error", resp)}

    def place_market_order(self, side: str, size: int, client_order_id: str = None, attempt: int = 0) -> dict:
        """
        Place a market order, protected by a $250 price-sanity ceiling.

        Uses an IOC limit order banded at ref_price +/- $250 instead of a
        raw market order. This band exists ONLY to block catastrophic thin-
        liquidity fills (e.g. $73,000 vs $64,000 mark) - normal fills
        ($1-50 slippage per your trade data) are never affected, since they
        sit well inside a $250 ceiling. Fires and fills in the same 1-3s
        window as a plain market order - no retry loop, no added delay.
        """
        _ref_price = self.get_current_price()
        if _ref_price <= 0:
            logging.error(f"[OrderManager] ENTRY BLOCKED - no reference price available (get_current_price returned {_ref_price})")
            send_alert(f"CTS ENTRY BLOCKED\nSide: {side.upper()}\nReason: Could not fetch reference price - order skipped to avoid firing blind")
            return {"success": False, "error": "no_reference_price"}

        if client_order_id:
            client_order_id = client_order_id[:32]
            _base_cid = client_order_id.rsplit('_a', 1)[0]
            for _prior_attempt in range(attempt + 1):
                _prior_cid = f"{_base_cid}_a{_prior_attempt}"[:32]
                _existing_p = self._get_order_by_client_id(_prior_cid)
                if _existing_p:
                    _unfilled_p = int(_existing_p.get("unfilled_size", size))
                    _filled_p = int(_existing_p.get("size", size)) - _unfilled_p
                    if _filled_p > 0:
                        logging.warning(f"[OrderManager] Prior attempt cid={_prior_cid} DID fill (id={_existing_p.get('id')}) - reusing, blocking duplicate retry")
                        _avg_p = self._get_avg_fill_price(_existing_p["id"])
                        _comm_p = self._get_order_commission(_existing_p["id"])
                        return {"success": True, "order_id": _existing_p["id"], "state": _existing_p.get("state"),
                                "side": _existing_p.get("side"), "size": _filled_p,
                                "filled_price": _existing_p.get("limit_price", "market"),
                                "avg_fill_price": float(_avg_p) if _avg_p else 0.0,
                                "commission": float(_comm_p) if _comm_p else 0.0}
            _existing = self._get_order_by_client_id(client_order_id)
            if _existing:
                logging.warning(f"[OrderManager] client_order_id={client_order_id} ALREADY EXISTS (id={_existing.get('id')}) - reusing, NOT placing new order")
                _unfilled_e = int(_existing.get("unfilled_size", size))
                _filled_e = int(_existing.get("size", size)) - _unfilled_e
                if _filled_e == 0:
                    return {"success": False, "error": "unfilled_beyond_band", "order_id": _existing.get("id")}
                _avg_e = self._get_avg_fill_price(_existing["id"])
                _comm_e = self._get_order_commission(_existing["id"])
                return {
                    "success": True, "order_id": _existing["id"], "state": _existing.get("state"),
                    "side": _existing.get("side"), "size": _filled_e,
                    "filled_price": _existing.get("limit_price", "market"),
                    "avg_fill_price": float(_avg_e) if _avg_e else 0.0,
                    "commission": float(_comm_e) if _comm_e else 0.0,
                }

        _band = self._ENTRY_BAND_TIERS[min(attempt, len(self._ENTRY_BAND_TIERS) - 1)]
        _limit_price = round(_ref_price + _band, 1) if side == "buy" else round(_ref_price - _band, 1)
        payload = {
            "product_symbol": self.PRODUCT_SYMBOL,
            "product_id":     self.PRODUCT_ID,
            "side":           side,
            "size":           size,
            "order_type":     "limit_order",
            "limit_price":    str(_limit_price),
            "time_in_force":  "ioc"
        }
        if client_order_id:
            payload["client_order_id"] = client_order_id

        logging.info(f"[OrderManager] Placing {side.upper()} banded order | size={size} lots | ref_price={_ref_price} | band=${_band} | limit={_limit_price} | cid={client_order_id}")
        resp = self._post("/v2/orders", payload, retries=1)

        if not resp.get("success") and client_order_id:
            logging.warning(f"[OrderManager] Initial POST failed for cid={client_order_id} - verifying before resubmit")
            _existing2 = self._get_order_by_client_id(client_order_id)
            if _existing2:
                logging.warning(f"[OrderManager] Order DID reach exchange (cid={client_order_id}, id={_existing2.get('id')}) - using it")
                resp = {"success": True, "result": _existing2}
            else:
                resp = self._post("/v2/orders", payload, retries=1)

        if resp.get("success"):
            result = resp["result"]
            _unfilled = int(result.get("unfilled_size", size))
            _filled   = size - _unfilled

            if _filled == 0:
                logging.error(f"[OrderManager] ENTRY UNFILLED - nothing filled within ${_band:.0f} band (attempt {attempt+1}) | ref_price={_ref_price} limit={_limit_price}")
                self._log_book_on_miss(side, size, _ref_price, _limit_price, "ENTRY")
                send_alert(f"CTS ENTRY UNFILLED\nSide: {side.upper()}\nRef price: ${_ref_price:,.1f}\nBand limit: ${_limit_price:,.1f}\nNo fill within ${_band:.0f} band (attempt {attempt+1}) - order skipped")
                return {"success": False, "error": "unfilled_beyond_band", "order_id": result.get("id")}

            logging.info(f"[OrderManager] Order filled | id={result['id']} state={result['state']} filled={_filled}/{size}")
            _avg = self._get_avg_fill_price(result["id"])

            if _avg and _ref_price > 0:
                _dev = abs(_avg - _ref_price)
                if _dev > _band:
                    logging.critical(f"[OrderManager] BAD FILL DESPITE BAND: ref_price={_ref_price} avg_fill={_avg} dev=${_dev:.1f} - auto-closing")
                    send_alert(f"CTS BAD FILL DESPITE BAND - AUTO-CLOSING\nSide: {side.upper()}\nRef price: ${_ref_price:,.1f}\nFilled at: ${_avg:,.1f}\nDeviation: ${_dev:.1f}")
                    _close_side = "sell" if side == "buy" else "buy"
                    self.close_position(size=_filled, side=_close_side)

            _comm = self._get_order_commission(result["id"])
            return {
                "success":      True,
                "order_id":     result["id"],
                "state":        result["state"],
                "side":         result["side"],
                "size":         _filled,
                "filled_price": result.get("limit_price", "market"),
                "avg_fill_price": float(_avg) if _avg else 0.0,
                "commission": float(_comm) if _comm else 0.0
            }
        else:
            logging.error(f"[OrderManager] Order FAILED: {resp.get('error')}")
            return {"success": False, "error": resp.get("error")}

    def _get_close_retry_state_path(self):
        key_hash = hashlib.md5(self.api_key.encode()).hexdigest()[:12]
        return f"logs/close_retry_state_{key_hash}.json"

    def _load_close_retry_state(self):
        path = self._get_close_retry_state_path()
        try:
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
        except Exception as e:
            logging.warning(f"[OrderManager] Could not load close_retry_state: {e}")
        return {}

    def _save_close_retry_state(self, state):
        path = self._get_close_retry_state_path()
        try:
            with open(path, "w") as f:
                json.dump(state, f)
        except Exception as e:
            logging.warning(f"[OrderManager] Could not save close_retry_state: {e}")

    def _clear_close_retry_state(self):
        path = self._get_close_retry_state_path()
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    def close_position(self, size: int, side: str, client_order_id: str = None,
                        max_attempts: int = 8, retry_delay: float = 1.5) -> dict:
        """
        Close an open position using reduce_only orders, RETRYING UNTIL THE
        POSITION IS CONFIRMED FLAT via get_position().

        THIN-LIQUIDITY PROTECTION (final, 3-mechanism design):
        1. Price-source fallback: /v2/positions mark_price used if /v2/tickers fails.
        2. Wall-clock cap persisted across repeated EXTERNAL calls (file-based,
           per-api_key-hash) - NOT just attempts within one call:
             0-15s  : IOC limit, $150 band
             15-60s : IOC limit, escalating $100 steps, capped $500
        3. >=60s  : LOSS-CAPPED FINAL STAGE - a RESTING (GTC) reduce-only limit
           order at a fixed $1000 max deviation (never higher, never a market
           order), polled for up to 10s per attempt to give the book time to
           trade into it, then cancelled and retried if unfilled. This improves
           fill probability over IOC at the IDENTICAL bounded price - it cannot
           ever produce a worse fill than IOC would have.

        NOTE (accepted, documented tradeoff): a bounded-price order can only fill
        if a counterparty exists within that band. True 100% avoidance of Tier 0
        is not mathematically possible without an uncapped price walk, which is
        explicitly disallowed (reintroduces the Aug 12-13 / Aug 20-21 failure
        patterns). If NO counterparty appears within $1000 of last-known price
        for the entire window, this IS operationally equivalent to a market/
        system-level failure, and Tier 0 (10%, resting independently on the
        exchange since entry) is the correct, intentional final backstop for
        exactly that residual case only.
        """
        last_resp = None
        last_avg_fill = 0.0
        last_commission = 0.0
        last_order_id = None

        _retry_state = self._load_close_retry_state()
        _now_wall = time.time()
        _STALE_STATE_SEC = 6 * 3600
        _IDLE_RESET_SEC = 600  # Bug3 fix: 10min gap since last actual close attempt means new incident
        if _retry_state.get("last_attempt_ts") and (_now_wall - _retry_state["last_attempt_ts"]) > _IDLE_RESET_SEC:
            logging.warning(f"[OrderManager] close_retry_state idle (>{_IDLE_RESET_SEC}s since last attempt) - resetting as new incident")
            _retry_state = {}
        elif _retry_state.get("first_failure_ts") and (_now_wall - _retry_state["first_failure_ts"]) > _STALE_STATE_SEC:
            logging.warning(f"[OrderManager] close_retry_state stale (>{_STALE_STATE_SEC}s old) - resetting as new incident")
            _retry_state = {}
        if _retry_state.get("side") != side or _retry_state.get("size") != size:
            logging.warning(f"[OrderManager] close_retry_state belongs to a different trade (saved side={_retry_state.get('side')} size={_retry_state.get('size')} vs this close side={side} size={size}) - resetting as new incident")
            _retry_state = {}
        if not _retry_state.get("first_failure_ts"):
            _retry_state["first_failure_ts"] = _now_wall
            _retry_state["side"] = side
            _retry_state["size"] = size
        _retry_state["last_attempt_ts"] = _now_wall
        self._save_close_retry_state(_retry_state)
        _elapsed_total = _now_wall - _retry_state["first_failure_ts"]

        _BAND_STEP_SEC   = 15.0
        _BASE_BAND       = 150.0
        _ESCALATED_MAX   = 500.0
        _TIME_CAP_SEC    = 60.0
        _LOSS_CAP_BAND   = 1000.0
        _REST_POLL_SEC   = 0.5
        _REST_POLLS      = 20

        _ZERO_FILL_PACE_SEC = 5.0   # spacing after a zero-fill IOC: gives the book time to refill; cap tier lands ~33s, not 9s
        for attempt in range(1, max_attempts + 1):
            _zero_fill = False
            _now_wall = time.time()
            _retry_state["last_attempt_ts"] = _now_wall
            self._save_close_retry_state(_retry_state)
            _elapsed_total = _now_wall - _retry_state["first_failure_ts"]
            _final_cap_active = _elapsed_total >= _TIME_CAP_SEC or attempt >= 7
            if _final_cap_active:
                _current_band = _LOSS_CAP_BAND
                logging.critical(f"[OrderManager] CLOSE ESCALATION - attempt={attempt}/{max_attempts} elapsed={_elapsed_total:.0f}s - "
                                  f"using LOSS-CAPPED RESTING order (${_LOSS_CAP_BAND:.0f} max, never a raw market order)")
            else:
                _escalation_steps = max(int(_elapsed_total // _BAND_STEP_SEC), (attempt - 1) // 3)
                _current_band = min(_BASE_BAND + _escalation_steps * 100.0, _ESCALATED_MAX)
            pos_check = self.get_position()
            current_size = abs(pos_check.get("size", 0)) if pos_check.get("success") else None
            pos_mark_price = pos_check.get("exit_price", 0.0) if pos_check.get("success") else 0.0

            if pos_check.get("success") and current_size == 0:
                logging.info(f"[OrderManager] Close CONFIRMED FLAT | attempt={attempt} | last_order_id={last_order_id}")
                self._clear_close_retry_state()
                try:
                    _cleanup = self._delete("/orders/all", {"product_id": self.PRODUCT_ID, "cancel_stop_orders": "true"})
                    if not _cleanup.get("success"):
                        logging.warning(f"[OrderManager] Stop order cleanup failed (non-critical): {_cleanup.get('error')}")
                except Exception as _ce:
                    logging.warning(f"[OrderManager] Stop order cleanup exception (non-critical): {_ce}")
                return {
                    "success": True, "order_id": last_order_id, "state": "closed",
                    "avg_fill_price": last_avg_fill, "attempts": attempt, "commission": last_commission
                }

            close_size = current_size if current_size else size

            ref_price = 0.0
            for _pf in range(3):
                ref_price = self.get_current_price()
                if ref_price and ref_price > 0:
                    break
                time.sleep(0.3)
            if not ref_price or ref_price <= 0:
                if pos_mark_price and pos_mark_price > 0:
                    ref_price = pos_mark_price
                    logging.warning(f"[OrderManager] Close attempt {attempt}/{max_attempts} - ticker failed, using /v2/positions mark_price={ref_price} as fallback")

            if not ref_price or ref_price <= 0:
                logging.warning(f"[OrderManager] Close attempt {attempt}/{max_attempts} SKIPPED - both price sources failed | elapsed={_elapsed_total:.0f}s")
                try:
                    send_alert(f"CTS WARNING - {self.PRODUCT_SYMBOL}\nBoth price sources failed on close attempt {attempt}/{max_attempts}\nElapsed: {_elapsed_total:.0f}s\nSide: {side.upper()} | Size: {close_size} lots\nTier 0 emergency SL remains the active backstop")
                except Exception:
                    pass
                if attempt < max_attempts:
                    time.sleep(retry_delay)
                continue

            limit_price = round(ref_price - _current_band, 1) if side == "sell" else round(ref_price + _current_band, 1)

            if _final_cap_active:
                payload = {
                    "product_symbol": self.PRODUCT_SYMBOL,
                    "product_id":     self.PRODUCT_ID,
                    "side":           side,
                    "size":           close_size,
                    "order_type":     "limit_order",
                    "limit_price":    str(limit_price),
                    "reduce_only":    "true"
                }
                if client_order_id:
                    payload["client_order_id"] = f"{client_order_id[:24]}_a{attempt}"
                logging.critical(f"[OrderManager] Close attempt {attempt}/{max_attempts} | LOSS-CAPPED RESTING order | {side.upper()} {close_size} lots @ {limit_price} (band=${_current_band:.0f}, elapsed={_elapsed_total:.0f}s)")
                resp = self._post("/v2/orders", payload)
                last_resp = resp

                if resp.get("success"):
                    _rest_id = resp["result"]["id"]
                    last_order_id = _rest_id
                    _filled_this_order = False
                    for _poll in range(_REST_POLLS):
                        time.sleep(_REST_POLL_SEC)
                        _chk = self._get(f"/v2/orders/{_rest_id}", {})
                        if _chk.get("success"):
                            _state = _chk.get("result", {}).get("state")
                            if _state == "closed":
                                _filled_this_order = True
                                break
                            if _state == "cancelled":
                                break
                    if _filled_this_order:
                        _avg = self._get_avg_fill_price(_rest_id)
                        if _avg:
                            last_avg_fill = float(_avg)
                        _comm = self._get_order_commission(_rest_id)
                        if _comm:
                            last_commission += float(_comm)
                        logging.info(f"[OrderManager] LOSS-CAPPED resting order FILLED | id={_rest_id} avg_fill={last_avg_fill}")
                    else:
                        try:
                            self._delete("/v2/orders", {"id": _rest_id, "product_id": self.PRODUCT_ID})
                        except Exception as _cane:
                            logging.warning(f"[OrderManager] Cancel of unfilled resting order failed: {_cane}")
                        logging.warning(f"[OrderManager] LOSS-CAPPED resting order id={_rest_id} did NOT fill within {_REST_POLLS*_REST_POLL_SEC:.0f}s - cancelled, retrying")
                else:
                    logging.error(f"[OrderManager] LOSS-CAPPED resting order placement FAILED | attempt={attempt}/{max_attempts} | error={resp.get('error')}")
            else:
                payload = {
                    "product_symbol": self.PRODUCT_SYMBOL,
                    "product_id":     self.PRODUCT_ID,
                    "side":           side,
                    "size":           close_size,
                    "order_type":     "limit_order",
                    "limit_price":    str(limit_price),
                    "time_in_force":  "ioc",
                    "reduce_only":    "true"
                }
                if client_order_id:
                    payload["client_order_id"] = f"{client_order_id[:24]}_a{attempt}"
                logging.info(f"[OrderManager] Close using IOC-banded limit | ref_price={ref_price} limit_price={limit_price} band=${_current_band:.0f} (elapsed={_elapsed_total:.0f}s)")
                resp = self._post("/v2/orders", payload)
                last_resp = resp

                if resp.get("success"):
                    result = resp["result"]
                    last_order_id = result["id"]
                    logging.info(f"[OrderManager] Close order placed | attempt={attempt} id={result['id']} state={result['state']}")
                    _unf_c = result.get("unfilled_size")
                    _zero_fill = (result.get("state") == "cancelled" and _unf_c is not None and int(_unf_c) >= int(close_size))
                    if _zero_fill:
                        logging.warning(f"[OrderManager] Close attempt {attempt} IOC cancelled with ZERO fill (band=${_current_band:.0f}) - skipping fill lookup, escalating")
                        self._log_book_on_miss(side, close_size, ref_price, limit_price, "CLOSE")
                        _avg = 0.0
                    else:
                        _avg = self._get_avg_fill_price(result["id"])
                    if _avg:
                        last_avg_fill = float(_avg)
                        try:
                            _post_close_ref = self.get_current_price()
                            if _post_close_ref and abs(last_avg_fill - _post_close_ref) > 250:
                                logging.critical(f"[OrderManager] CLOSE FILL FAR FROM MARK: fill={last_avg_fill} ref={_post_close_ref} dev=${abs(last_avg_fill-_post_close_ref):.1f}")
                                send_alert(f"CTS WARNING - Close fill deviated ${abs(last_avg_fill-_post_close_ref):.1f} from mark\nFill: ${last_avg_fill:,.1f}\nMark: ${_post_close_ref:,.1f}")
                        except Exception as _dce:
                            logging.warning(f"[OrderManager] Close-fill deviation check failed (non-critical): {_dce}")
                    if not _zero_fill:
                        _comm = self._get_order_commission(result["id"])
                        if _comm:
                            last_commission += float(_comm)
                else:
                    logging.error(f"[OrderManager] Close order FAILED | attempt={attempt}/{max_attempts} | error={resp.get('error')}")

            if attempt < max_attempts:
                time.sleep(max(retry_delay, _ZERO_FILL_PACE_SEC) if _zero_fill else retry_delay)

        final_check = self.get_position()
        final_size = abs(final_check.get("size", 0)) if final_check.get("success") else None

        if final_check.get("success") and final_size == 0:
            logging.info(f"[OrderManager] Close CONFIRMED FLAT on final check | total_attempts={max_attempts}")
            self._clear_close_retry_state()
            return {"success": True, "order_id": last_order_id, "state": "closed",
                    "avg_fill_price": last_avg_fill, "attempts": max_attempts}

        _pos_desc = f"size={final_size}" if final_check.get("success") else "UNKNOWN (position API check failed)"
        logging.critical(f"[OrderManager] CLOSE FAILED AFTER {max_attempts} ATTEMPTS - position still open ({_pos_desc}) - elapsed={_elapsed_total:.0f}s - MANUAL INTERVENTION REQUIRED")
        send_alert(
            f"CTS CRITICAL - CLOSE FAILED AFTER {max_attempts} ATTEMPTS\n"
            f"Side requested : {side.upper()}\n"
            f"Target size    : {size}\n"
            f"Position now   : {_pos_desc}\n"
            f"Elapsed        : {_elapsed_total:.0f}s since first failure\n"
            f"Last error     : {last_resp.get('error') if last_resp else 'N/A'}\n"
            f"ACTION REQUIRED: Close manually on Delta Exchange immediately.\n"
            f"$1000 loss-capped resting order also failed to fill - genuine extreme "
            f"illiquidity or platform-level issue. Tier 0 (10%) is the only remaining "
            f"automated protection."
        )
        return {"success": False, "error": "close_failed_after_max_attempts",
                "last_error": last_resp.get("error") if last_resp else None,
                "attempts": max_attempts, "position_still_open": True}

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
            _err = str(resp.get("error", ""))
            logging.error("[OrderManager] get_position FAILED - raw_error=%r full_resp=%r" % (_err, resp))
            if "invalid_api_key" in _err.lower() or "InvalidApiKey" in _err:
                try:
                    send_alert(f"CTS CRITICAL: invalid_api_key\nBot cannot trade - API key rejected\nCheck key immediately")
                except Exception:
                    pass
            return {"success": False, "size": 0, "entry_price": 0.0, "direction": "UNKNOWN"}

    def get_current_price(self) -> float:
        """Fetch current mark price via public ticker endpoint - used as
        ref_price for IOC-banded limit orders (caps slippage vs raw market)."""
        resp = self._get(f"/v2/tickers/{self.PRODUCT_SYMBOL}", {})
        if resp.get("success"):
            result = resp.get("result", {})
            mark = result.get("mark_price") or result.get("close") or 0
            return float(mark) if mark else 0.0
        return 0.0

    def _book_walk(self, side: str, size: float, depth: int = 20):
        """Read-only L2 snapshot. side = ORDER side ('buy' consumes asks).
        Returns dict or None on ANY problem (callers must treat None as unknown)."""
        try:
            resp = self._get(f"/v2/l2orderbook/{self.PRODUCT_SYMBOL}", {"depth": depth}, retries=1)
            if not resp.get("success"):
                return None
            res = resp.get("result", {}) or {}
            lv = res.get("sell" if side == "buy" else "buy", []) or []
            lv = sorted(((float(l["price"]), float(l["size"])) for l in lv), reverse=(side == "sell"))
            if not lv:
                return {"best": None, "worst": None, "avg": None, "unfilled": float(size), "levels": 0}
            rem, cost, worst = float(size), 0.0, None
            for px, sz in lv:
                take = min(sz, rem)
                cost += px * take
                rem -= take
                worst = px
                if rem <= 0:
                    break
            got = float(size) - rem
            return {"best": lv[0][0], "worst": worst, "avg": (cost / got) if got > 0 else None,
                    "unfilled": rem, "levels": len(lv)}
        except Exception as _e:
            logging.warning(f"[OrderManager] _book_walk failed (non-critical): {_e}")
            return None

    def _log_book_on_miss(self, side, size, ref_price, limit_price, tag):
        """Diagnostic only - runs ONLY after an IOC miss, never on the fill path.
        Never raises, never changes order behaviour."""
        try:
            b = self._book_walk(side, size)
            if b is None:
                logging.warning(f"[BOOK-MISS][{tag}] book unavailable | ref={ref_price} limit={limit_price}")
                return
            if b["best"] is None:
                logging.warning(f"[BOOK-MISS][{tag}] opposite side of book EMPTY | ref={ref_price} limit={limit_price}")
                return
            sgn = 1.0 if side == "buy" else -1.0
            d_best = (b["best"] - ref_price) * sgn
            d_worst = (b["worst"] - ref_price) * sgn if b["worst"] is not None else None
            logging.warning(
                f"[BOOK-MISS][{tag}] side={side} size={size} ref={ref_price:.1f} limit={limit_price} "
                f"best_touch={b['best']:.1f} (${d_best:+.0f} vs mark) "
                f"walk_worst={b['worst']} (${d_worst if d_worst is None else round(d_worst)} vs mark) "
                f"walk_avg={b['avg']} unfilled_in_top_levels={b['unfilled']:.0f} levels={b['levels']}")
        except Exception as _e:
            logging.warning(f"[BOOK-MISS][{tag}] logging failed (non-critical): {_e}")

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


    def place_stop_loss_order(self, direction: str, entry_price: float, sl_pct: float = 10.0,
                               max_attempts: int = 5, retry_delay: float = 2.0) -> dict:
        """
        Place a stop market order as SL on an open position, RETRYING UNTIL
        CONFIRMED PRESENT on exchange - not just until a single placement
        call returns success=True.
        Works AFTER position is open - no bracket_order_immediate_execution issue.
        direction    : "long" or "short"
        entry_price  : actual fill price from get_position()
        sl_pct       : stop loss % from entry (default 1.5% - capped near 2.5x backtest 4000 INR ceiling)
        max_attempts : max placement attempts before escalating (default 5)
        retry_delay  : seconds between attempts (default 2.0s)

        LOCK: file lock keyed per api_key ensures only one process (bot OR
        monitor) can place/check SL for this subaccount at a time - prevents
        duplicate-SL race condition when both retry around the same moment.
        """
        if entry_price <= 0:
            logging.error(f"[OrderManager] SL skipped - invalid entry_price={entry_price}")
            return {"success": False, "error": "invalid_entry_price"}

        _lock_key = hashlib.md5(self.api_key.encode()).hexdigest()[:12]
        _lock_path = f"/tmp/cts_sl_lock_{_lock_key}.lock"
        _lock_fh = open(_lock_path, "a")
        logging.info(f"[OrderManager] Acquiring SL lock for account (waiting if held by other process)")
        fcntl.flock(_lock_fh, fcntl.LOCK_EX)
        try:
            return self._place_stop_loss_order_locked(direction, entry_price, sl_pct, max_attempts, retry_delay)
        finally:
            fcntl.flock(_lock_fh, fcntl.LOCK_UN)
            _lock_fh.close()

    def _save_active_sl_id(self, order_id):
        """Persist the confirmed-live SL order_id to a per-account state file,
        so sl_safety_monitor.py can check this EXACT order later instead of
        guessing by price/side (which fails when stale same-side orders exist)."""
        try:
            key_hash = hashlib.md5(self.api_key.encode()).hexdigest()[:12]
            path = f"logs/active_sl_id_{key_hash}.txt"
            with open(path, "w") as f:
                f.write(str(order_id))
        except Exception as e:
            logging.warning(f"[OrderManager] Could not save active_sl_id: {e}")

    def _get_confirmed_sl_via_id_file(self, expected_side):
        """Check the specific SL order_id saved from last successful placement -
        avoids side-only matching which can wrongly pick a stale order when
        multiple same-side stop orders still exist on exchange."""
        try:
            key_hash = hashlib.md5(self.api_key.encode()).hexdigest()[:12]
            id_file = f"logs/active_sl_id_{key_hash}.txt"
            if not os.path.exists(id_file):
                return None
            with open(id_file) as f:
                saved_id = f.read().strip()
            if not saved_id:
                return None
            chk = self._get(f"/v2/orders/{saved_id}", {})
            if chk.get("success"):
                o = chk.get("result", {})
                if (o.get("stop_order_type") == "stop_loss_order"
                        and o.get("side") == expected_side
                        and o.get("state") in ("open", "pending")):
                    return o
        except Exception as e:
            logging.warning(f"[OrderManager] id-file SL check failed: {e}")
        return None

    def _place_stop_loss_order_locked(self, direction: str, entry_price: float, sl_pct: float = 10.0,
                               max_attempts: int = 5, retry_delay: float = 2.0) -> dict:

        try:
            _fresh_pos = self.get_position()
            if _fresh_pos.get("success") and _fresh_pos.get("entry_price", 0) > 0:
                _fresh_entry = _fresh_pos["entry_price"]
                if entry_price <= 0 or abs(_fresh_entry - entry_price) > 50:
                    logging.warning(f"[OrderManager] SL entry_price mismatch: passed={entry_price} fresh={_fresh_entry} - using fresh value")
                    entry_price = _fresh_entry
        except Exception as _e:
            logging.warning(f"[OrderManager] Fresh entry_price check failed, using passed value: {_e}")

        if direction == "long":
            sl_price = round(entry_price * (1 - sl_pct / 100), 1)
            side = "sell"
        else:
            sl_price = round(entry_price * (1 + sl_pct / 100), 1)
            side = "buy"

        _sl_size = 100
        try:
            _pos = self.get_position()
            if _pos.get("success") and _pos.get("size", 0) != 0:
                _sl_size = abs(int(_pos["size"]))
        except Exception as _e:
            logging.error(f"[OrderManager] SL size fetch failed, using fallback 100: {_e}")

        last_resp = None
        last_sl_order_id = None

        for attempt in range(1, max_attempts + 1):
            _existing_sl = self._get_confirmed_sl_via_id_file(side)
            if _existing_sl:
                logging.info(f"[OrderManager] SL CONFIRMED PRESENT | attempt={attempt} order_id={_existing_sl.get('id')}")
                self._save_active_sl_id(_existing_sl.get("id"))
                return {"success": True, "sl_price": sl_price, "order_id": _existing_sl.get("id"), "attempts": attempt}

            limit_price = round(sl_price - 150, 1) if side == "sell" else round(sl_price + 150, 1)

            payload = {
                "product_symbol": self.PRODUCT_SYMBOL,
                "product_id":     self.PRODUCT_ID,
                "side":           side,
                "size":           _sl_size,
                "order_type":     "limit_order",
                "stop_order_type": "stop_loss_order",
                "stop_price":     str(sl_price),
                "limit_price":    str(limit_price),
                "reduce_only":    True,
                "close_on_trigger": True
            }

            logging.info(f"[OrderManager] SL placement attempt {attempt}/{max_attempts} | direction={direction} entry={entry_price} sl={sl_price} ({sl_pct}%)")
            resp = self._post("/v2/orders", payload)
            last_resp = resp

            if resp.get("success"):
                result = resp["result"]
                last_sl_order_id = result.get("id")
                logging.info(f"[OrderManager] Stop-limit SL placed | attempt={attempt} sl_price={sl_price} limit_price={limit_price} order_id={last_sl_order_id}")
                self._save_active_sl_id(last_sl_order_id)
                self._start_sl_gap_watchdog(last_sl_order_id, side, _sl_size, sl_price)
                return {"success": True, "sl_price": sl_price, "order_id": last_sl_order_id, "attempts": attempt}
            else:
                logging.error(f"[OrderManager] Stop SL placement FAILED | attempt={attempt}/{max_attempts} | error={resp.get('error')}")

            if attempt < max_attempts:
                time.sleep(retry_delay)

        _existing_sl = self._get_confirmed_sl_via_id_file(side)
        if _existing_sl:
            logging.info(f"[OrderManager] SL CONFIRMED PRESENT on final check | total_attempts={max_attempts}")
            self._save_active_sl_id(_existing_sl.get("id"))
            return {"success": True, "sl_price": sl_price, "order_id": _existing_sl.get("id"), "attempts": max_attempts}

        logging.critical(f"[OrderManager] SL PLACEMENT FAILED AFTER {max_attempts} ATTEMPTS - POSITION UNPROTECTED - MANUAL INTERVENTION REQUIRED")
        send_alert(
            f"CTS CRITICAL - SL PLACEMENT FAILED AFTER {max_attempts} ATTEMPTS\n"
            f"Direction: {direction.upper()}\n"
            f"Entry price: {entry_price}\n"
            f"Target SL price: {sl_price}\n"
            f"Last error: {last_resp.get('error') if last_resp else 'N/A'}\n"
            f"ACTION REQUIRED: Position is UNPROTECTED - place SL manually on Delta Exchange immediately"
        )
        logging.critical(f"[OrderManager] SL PLACEMENT FAILED AFTER {max_attempts} ATTEMPTS - initiating emergency close")
        try:
            _emergency = self.close_position(size=_sl_size, side=side, max_attempts=8, retry_delay=1.5)
            if _emergency.get("success"):
                send_alert(
                    f"CTS CRITICAL - SL FAILED, EMERGENCY CLOSE SUCCEEDED\n"
                    f"Direction: {direction.upper()}\n"
                    f"Entry: {entry_price}\n"
                    f"Closed at: {_emergency.get('avg_fill_price')}"
                )
            else:
                send_alert(
                    f"CTS CRITICAL - SL FAILED AND EMERGENCY CLOSE ALSO FAILED\n"
                    f"Direction: {direction.upper()}\n"
                    f"Entry: {entry_price}\n"
                    f"MANUAL INTERVENTION REQUIRED IMMEDIATELY - POSITION FULLY UNPROTECTED"
                )
        except Exception as _ee:
            logging.critical(f"[OrderManager] Emergency close exception: {_ee}")
            _emergency = {"success": False, "error": str(_ee)}

        return {"success": False, "error": "sl_placement_failed_emergency_closed", "attempts": max_attempts, "emergency_close": _emergency}

    def _start_sl_gap_watchdog(self, order_id, side, size, sl_price, timeout=45.0, poll_interval=5.0):
        _t = threading.Thread(
            target=self._sl_gap_watchdog_worker,
            args=(order_id, side, size, sl_price, timeout, poll_interval),
            daemon=True
        )
        _t.start()
        logging.info("[OrderManager] SL gap watchdog started | order_id=" + str(order_id) + " timeout=" + str(timeout) + "s poll=" + str(poll_interval) + "s")

    def _sl_gap_watchdog_worker(self, order_id, side, size, sl_price, timeout, poll_interval):
        elapsed = 0.0
        while elapsed < timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval
            try:
                resp = self._get("/v2/orders/" + str(order_id), {})
            except Exception as _e:
                logging.error("[OrderManager] SL gap watchdog GET failed | order_id=" + str(order_id) + " err=" + str(_e))
                continue

            if not resp.get("success"):
                logging.error("[OrderManager] SL gap watchdog GET error | order_id=" + str(order_id) + " error=" + str(resp.get("error")))
                continue

            result = resp.get("result", {})
            state = result.get("state")
            unfilled_size = result.get("unfilled_size", size)

            if state == "closed":
                logging.info("[OrderManager] SL gap watchdog | order_id=" + str(order_id) + " FILLED - watchdog exiting")
                return
            if state == "cancelled":
                logging.warning("[OrderManager] SL gap watchdog | order_id=" + str(order_id) + " CANCELLED externally - watchdog exiting")
                return
            if state == "pending":
                continue

        try:
            resp = self._get("/v2/orders/" + str(order_id), {})
            result = resp.get("result", {}) if resp.get("success") else {}
            state = result.get("state")
            unfilled_size = result.get("unfilled_size", size)
        except Exception as _e:
            logging.critical("[OrderManager] SL gap watchdog final check failed | order_id=" + str(order_id) + " err=" + str(_e))
            state = None
            unfilled_size = size

        if state == "open" and unfilled_size and unfilled_size > 0:  # FIX 24-Aug: removed "pending" - pending means SL never triggered, not stuck. Only force-close if truly triggered (open) but unfilled.
            logging.critical("[OrderManager] SL GAP DETECTED - order_id=" + str(order_id) + " stuck unfilled after " + str(timeout) + "s - forcing emergency close")
            try:
                _cancel = self._delete("/v2/orders", {"id": order_id, "product_id": self.PRODUCT_ID})
                logging.info("[OrderManager] SL gap watchdog cancel response: " + str(_cancel))
            except Exception as _e:
                logging.error("[OrderManager] SL gap watchdog cancel failed | order_id=" + str(order_id) + " err=" + str(_e))

            try:
                _emergency = self.close_position(size=unfilled_size, side=side, max_attempts=8, retry_delay=1.5)
                if _emergency.get("success"):
                    send_alert(
                        "CTS WARNING - SL GAP DETECTED, EMERGENCY MARKET CLOSE SUCCEEDED\n"
                        "order_id=" + str(order_id) + "\n"
                        "sl_price=" + str(sl_price) + "\n"
                        "Closed at: " + str(_emergency.get("avg_fill_price"))
                    )
                else:
                    send_alert(
                        "CTS CRITICAL - SL GAP DETECTED, EMERGENCY MARKET CLOSE FAILED\n"
                        "order_id=" + str(order_id) + "\n"
                        "sl_price=" + str(sl_price) + "\n"
                        "MANUAL INTERVENTION REQUIRED IMMEDIATELY"
                    )
            except Exception as _ee:
                logging.critical("[OrderManager] SL gap watchdog emergency close exception: " + str(_ee))
        else:
            logging.info("[OrderManager] SL gap watchdog | order_id=" + str(order_id) + " final state=" + str(state) + " unfilled=" + str(unfilled_size) + " - no action needed")
