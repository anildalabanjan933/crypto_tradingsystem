# run_live_trading_s2.py
# Responsibility: 24/7 live trading loop for BTC Renko + Reversal strategy (S2)
# Runs on Delta Exchange testnet (S2RenkoReversa sub-account)
#
# Strategy rules:
#   Entry : ST flip at S/R zone (horizontal OR trendline) + 1 green/red box close
#   Exit  : 1 Renko box close after Supertrend flip
#   Size  : LOT_MULTIPLIER x 10 lots (default 10x = 100 lots)
#   One active trade at a time; opposite signal closes + reopens immediately

import os
import sys
import time
import logging
import traceback
from datetime import datetime, timezone

import pandas as pd
import numpy as np

# ── Project modules ──────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from data.delta_exchange_fetcher import DeltaExchangeFetcher
from engine.order_manager        import OrderManager
from engine.signal_executor      import SignalExecutor
from indicators.renko            import RenkoBuilder, SupertrendIndicator
from strategies.renko_reversal_strategy import RenkoReversalStrategy

# =============================================================================
# CONFIGURATION  –  edit these before running
# =============================================================================

API_KEY        = "0VlikvAviBfapRqJN6pT5LvKVwWmq5"
API_SECRET     = "peCHX7snwrgdRkQAXgxPfBy0XjGGs43nf0HnUIq7deNlnRbEUmWz30jrw9Rs"
TESTNET        = True          # True = demo testnet | False = live account

# Position sizing
LOT_MULTIPLIER = 10            # 10x = 100 lots
BASE_LOTS      = 10
POSITION_SIZE  = LOT_MULTIPLIER * BASE_LOTS   # = 100 lots

# Renko settings
RENKO_BOX_SIZE = 200

# Supertrend settings
ST_ATR_LEN     = 5
ST_FACTOR      = 4.0

# Signal settings
SWING_L          = 2
SWING_R          = 2
SR_TOLERANCE     = 5.0
MIN_AGE_HORIZ    = 30
COOLDOWN_BOXES   = 20
ANCHOR_LOOKBACK  = 50

# Data fetch settings
WARMUP_CANDLES    = 500
POLL_INTERVAL_SEC = 60

# Logging
LOG_FILE = "logs/live_trading_s2.log"

# =============================================================================
# LOGGING SETUP
# =============================================================================

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("LiveTrading_S2")

# =============================================================================
# HELPER: Fetch and build 2H candles from 30M data
# =============================================================================

def fetch_recent_candles(fetcher: DeltaExchangeFetcher, n_30m: int = 2000) -> pd.DataFrame:
    end_ts   = int(time.time())
    start_ts = end_ts - (n_30m * 1800)

    PAGE_SIZE   = 200
    all_candles = []
    chunk_start = start_ts
    page        = 0

    while chunk_start < end_ts:
        chunk_end = min(chunk_start + (PAGE_SIZE * 1800), end_ts)
        log.info(f"[Fetch] Page {page} | start={chunk_start} end={chunk_end}")
        candles = fetcher._fetch_chunk(chunk_start, chunk_end)
        log.info(f"[Fetch] Page {page} returned {len(candles) if candles else 0} candles")
        if candles:
            all_candles.extend(candles)
        time.sleep(0.3)
        chunk_start = chunk_end
        page += 1

    if not all_candles:
        log.error("fetch_recent_candles: no data returned")
        return pd.DataFrame()

    df = pd.DataFrame(all_candles)
    df["datetime"] = pd.to_datetime(df["Date"] + " " + df["Time"])
    df = df.rename(columns={
        "Open": "open", "High": "high",
        "Low":  "low",  "Close": "close", "Volume": "volume"
    })
    df = df[["datetime", "open", "high", "low", "close", "volume"]]
    df = df.sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)

    df["bucket"] = df["datetime"].dt.floor("2h")
    df_2h = df.groupby("bucket").agg(
        open=("open",    "first"),
        high=("high",    "max"),
        low=("low",      "min"),
        close=("close",  "last"),
        volume=("volume","sum")
    ).reset_index().rename(columns={"bucket": "datetime"})

    df_2h = df_2h.reset_index(drop=True)

    log.info(f"Fetched {len(df_2h)} 2H candles "
             f"({df_2h['datetime'].iloc[0]} -> {df_2h['datetime'].iloc[-1]})")
    return df_2h

# =============================================================================
# HELPER: Build Renko boxes
# =============================================================================

def build_renko_boxes(df_2h: pd.DataFrame) -> pd.DataFrame:
    closes   = df_2h["close"].values
    builder  = RenkoBuilder(box_size=RENKO_BOX_SIZE)
    df_renko = builder.build(closes)

    if df_renko.empty:
        log.error("RenkoBuilder returned empty result")
        return pd.DataFrame()

    df_renko["box_idx"] = np.arange(len(df_renko))
    log.info(f"Built {len(df_renko)} Renko boxes | "
             f"last close={df_renko['renko_close'].iloc[-1]:.0f}")
    return df_renko

# =============================================================================
# HELPER: Compute Supertrend
# =============================================================================

def get_supertrend_bull(df_renko: pd.DataFrame) -> pd.Series:
    st_indicator = SupertrendIndicator(atr_period=ST_ATR_LEN, factor=ST_FACTOR)
    df_st        = st_indicator.calculate(df_renko)
    return df_st["st_dir"] == -1

# =============================================================================
# POSITION TRACKER
# =============================================================================

class PositionTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.active      = False
        self.direction   = None
        self.entry_price = 0.0
        self.entry_time  = None
        self.signal_type = None
        self.order_id    = None
        self.size        = 0

    def open_trade(self, direction, entry_price, signal_type, order_id, size):
        self.active      = True
        self.direction   = direction
        self.entry_price = entry_price
        self.signal_type = signal_type
        self.order_id    = order_id
        self.size        = size
        self.entry_time  = datetime.now(timezone.utc)
        log.info(f"[Position] OPENED {direction} | signal={signal_type} "
                 f"entry={entry_price:.0f} size={size} lots")

    def close_trade(self, exit_price, reason):
        if not self.active:
            return
        pnl_per_lot = (
            (exit_price - self.entry_price) if self.direction == "LONG"
            else (self.entry_price - exit_price)
        )
        pnl_usd = pnl_per_lot * self.size * 0.001
        log.info(f"[Position] CLOSED {self.direction} | reason={reason} "
                 f"entry={self.entry_price:.0f} exit={exit_price:.0f} "
                 f"pnl_usd={pnl_usd:.2f}")
        self.reset()

# =============================================================================
# MAIN LIVE TRADING LOOP
# =============================================================================

def run_live():
    log.info("=" * 60)
    log.info("S2 RenkoReversal Live Trading Bot STARTING")
    log.info(f"Mode      : {'TESTNET' if TESTNET else 'LIVE'}")
    log.info(f"Account   : S2RenkoReversa")
    log.info(f"Lots      : {POSITION_SIZE} ({LOT_MULTIPLIER}x multiplier)")
    log.info(f"Renko     : box={RENKO_BOX_SIZE}")
    log.info(f"ST        : ATR={ST_ATR_LEN} Factor={ST_FACTOR}")
    log.info(f"SR_TOL    : {SR_TOLERANCE}")
    log.info("=" * 60)

    fetcher  = DeltaExchangeFetcher()
    orders   = OrderManager(API_KEY, API_SECRET, testnet=TESTNET)
    # strategy = RenkoReversalStrategy()
    executor = SignalExecutor(
        swing_l        = SWING_L,
        swing_r        = SWING_R,
        sr_tolerance   = SR_TOLERANCE,
        min_age_horiz  = MIN_AGE_HORIZ,
        cooldown_boxes = COOLDOWN_BOXES,
        anchor_lookback= ANCHOR_LOOKBACK
    )
    tracker  = PositionTracker()

    pos = orders.get_position()
    if pos["success"] and pos["size"] != 0:
        log.warning(f"[Startup] Existing position: "
                    f"{pos['direction']} {abs(pos['size'])} lots "
                    f"@ {pos['entry_price']:.0f}")
        tracker.open_trade(
            direction  = pos["direction"],
            entry_price= pos["entry_price"],
            signal_type= "EXISTING",
            order_id   = None,
            size       = abs(pos["size"])
        )

    last_box_count = 0
    last_box_close = None

    log.info(f"[Loop] Starting poll loop every {POLL_INTERVAL_SEC}s ...")

    while True:
        try:
            df_2h = fetch_recent_candles(fetcher, n_30m=WARMUP_CANDLES)
            if df_2h.empty:
                log.warning("[Loop] Empty candle data, retrying in 60s")
                time.sleep(60)
                continue

            df_renko = build_renko_boxes(df_2h)
            if df_renko.empty:
                log.warning("[Loop] Empty Renko data, retrying in 60s")
                time.sleep(60)
                continue

            current_box_count = len(df_renko)
            current_box_close = df_renko["renko_close"].iloc[-1]

            new_box_closed = (
                current_box_count > last_box_count
                or (current_box_count == last_box_count
                    and current_box_close != last_box_close)
            )

            if not new_box_closed:
                log.debug(f"[Loop] No new box | boxes={current_box_count} "
                          f"last_close={current_box_close:.0f}")
                time.sleep(POLL_INTERVAL_SEC)
                continue

            log.info(f"[Loop] NEW BOX CLOSED | box #{current_box_count} "
                     f"close={current_box_close:.0f}")

            last_box_count = current_box_count
            last_box_close = current_box_close

            st_bull = get_supertrend_bull(df_renko)
            signals = executor.update(df_renko, st_bull)

            log.info(f"[Signals] BUY_A={signals['BUY_A']} "
                     f"BUY_B={signals['BUY_B']} "
                     f"SELL_A={signals['SELL_A']} "
                     f"SELL_B={signals['SELL_B']} | "
                     f"ST_flip_bull={signals['st_flip_bull']} "
                     f"ST_flip_bear={signals['st_flip_bear']}")

            # EXIT logic
            if tracker.active:
                exit_triggered = False
                exit_reason    = ""

                if tracker.direction == "LONG" and signals["st_flip_bear"]:
                    exit_triggered = True
                    exit_reason    = "ST_FLIP_RED"
                elif tracker.direction == "SHORT" and signals["st_flip_bull"]:
                    exit_triggered = True
                    exit_reason    = "ST_FLIP_GREEN"

                if exit_triggered:
                    close_side = "sell" if tracker.direction == "LONG" else "buy"
                    result = orders.close_position(
                        size            = tracker.size,
                        side            = close_side,
                        client_order_id = f"exit_{int(time.time())}"
                    )
                    if result["success"]:
                        tracker.close_trade(
                            exit_price = float(current_box_close),
                            reason     = exit_reason
                        )
                    else:
                        log.error(f"[Exit] Close order FAILED: {result['error']}")

            # ENTRY logic
            entry_signal = None
            entry_dir    = None

            if signals["BUY_A"]:
                entry_signal, entry_dir = "BUY_A",  "LONG"
            elif signals["BUY_B"]:
                entry_signal, entry_dir = "BUY_B",  "LONG"
            elif signals["SELL_A"]:
                entry_signal, entry_dir = "SELL_A", "SHORT"
            elif signals["SELL_B"]:
                entry_signal, entry_dir = "SELL_B", "SHORT"

            if entry_signal:
                if tracker.active and tracker.direction != entry_dir:
                    log.info(f"[Entry] Opposite signal {entry_signal} | "
                             f"closing {tracker.direction} first")
                    close_side = "sell" if tracker.direction == "LONG" else "buy"
                    result = orders.close_position(
                        size            = tracker.size,
                        side            = close_side,
                        client_order_id = f"flip_{int(time.time())}"
                    )
                    if result["success"]:
                        tracker.close_trade(
                            exit_price = float(current_box_close),
                            reason     = f"OPPOSITE_SIGNAL_{entry_signal}"
                        )
                    else:
                        log.error(f"[Entry] Flip close FAILED: {result['error']}")
                        time.sleep(POLL_INTERVAL_SEC)
                        continue

                if not tracker.active:
                    order_side = "buy" if entry_dir == "LONG" else "sell"
                    result = orders.place_market_order(
                        side            = order_side,
                        size            = POSITION_SIZE,
                        client_order_id = f"{entry_signal}_{int(time.time())}"
                    )
                    if result["success"]:
                        tracker.open_trade(
                            direction   = entry_dir,
                            entry_price = float(current_box_close),
                            signal_type = entry_signal,
                            order_id    = result["order_id"],
                            size        = POSITION_SIZE
                        )
                    else:
                        log.error(f"[Entry] Open order FAILED: {result['error']}")

            time.sleep(POLL_INTERVAL_SEC)

        except KeyboardInterrupt:
            log.info("[Loop] Keyboard interrupt. Shutting down.")
            break

        except Exception as e:
            log.error(f"[Loop] Unhandled exception: {e}")
            log.error(traceback.format_exc())
            log.info("[Loop] Sleeping 120s before retry...")
            time.sleep(120)

    log.info("[Loop] S2 RenkoReversal bot stopped.")


if __name__ == "__main__":
    run_live()
