# run_live_trading.py
# Responsibility: 24/7 live trading loop for BTC Renko + Supertrend strategy
# Runs on Delta Exchange testnet (BTCMomentum sub-account) by default
#
# Strategy rules (mirrors validate_trades.py exactly):
#   Entry : 1 Renko box close after trendline break (BUY_A/B or SELL_A/B)
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

# =============================================================================
# CONFIGURATION  –  edit these before running
# =============================================================================

API_KEY        = "qyzLRj9JfKaasJcvyFd8GFvE99CtPO"
API_SECRET     = "ZuzFcf8tDheVLAE71wL0rSxHzmMyuTM1z8HqXQgT74hUDlkZ2v9cCIlSHvvR"
TESTNET        = True          # True = demo testnet | False = live account

# Position sizing  –  ONLY change LOT_MULTIPLIER
LOT_MULTIPLIER = 10            # 10x = 100 lots | 1x = 10 lots | 20x = 200 lots
BASE_LOTS      = 10
POSITION_SIZE  = LOT_MULTIPLIER * BASE_LOTS   # = 100 lots

# Renko settings (must match Delta Exchange chart exactly)
RENKO_BOX_SIZE = 200           # Traditional Renko, 200 USD box

# Supertrend settings (must match backtest exactly)
ST_ATR_LEN     = 5
ST_FACTOR      = 4.0

# Signal settings (must match validate_trades.py exactly)
SWING_L          = 2
SWING_R          = 2
SR_TOLERANCE     = 1.0
MIN_AGE_HORIZ    = 30
COOLDOWN_BOXES   = 20
ANCHOR_LOOKBACK  = 50

# Data fetch settings
WARMUP_CANDLES    = 500        # 30M candles to fetch (~10 days of warmup)
POLL_INTERVAL_SEC = 60         # check for new closed box every 60 seconds

# Logging
LOG_FILE = "logs/live_trading.log"

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
log = logging.getLogger("LiveTrading")

# =============================================================================
# HELPER: Fetch and build 2H candles from 30M data
# =============================================================================

def fetch_recent_candles(fetcher: DeltaExchangeFetcher, n_30m: int = 2000) -> pd.DataFrame:
    """
    Fetch the last n_30m 30-minute candles and aggregate to 2H.
    Returns DataFrame with columns: datetime, open, high, low, close, volume
    """
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

    # Aggregate 30M -> 2H
    df["bucket"] = df["datetime"].dt.floor("2h")
    df_2h = df.groupby("bucket").agg(
        open=("open",    "first"),
        high=("high",    "max"),
        low=("low",      "min"),
        close=("close",  "last"),
        volume=("volume","sum")
    ).reset_index().rename(columns={"bucket": "datetime"})

    # NOTE: zero-volume filter removed — testnet returns zero-volume for older bars
    df_2h = df_2h.reset_index(drop=True)

    log.info(f"Fetched {len(df_2h)} 2H candles "
             f"({df_2h['datetime'].iloc[0]} -> {df_2h['datetime'].iloc[-1]})")
    return df_2h


# =============================================================================
# HELPER: Build Renko boxes
# =============================================================================

def build_renko_boxes(df_2h: pd.DataFrame) -> pd.DataFrame:
    """
    Build Traditional Renko boxes from 2H OHLCV using RenkoBuilder.
    Returns DataFrame with columns:
        bar_index, renko_open, renko_close, renko_dir, renko_high, renko_low, box_idx
    """
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
# HELPER: Compute Supertrend on Renko boxes
# =============================================================================

def get_supertrend_bull(df_renko: pd.DataFrame) -> pd.Series:
    """
    Compute Supertrend on Renko OHLC using SupertrendIndicator.
    Returns boolean Series: True = bullish (st_dir == -1), False = bearish.
    Matches backtest exactly: ATR=5, Factor=4, Wilder RMA.
    """
    st_indicator = SupertrendIndicator(atr_period=ST_ATR_LEN, factor=ST_FACTOR)
    df_st        = st_indicator.calculate(df_renko)
    # st_dir: -1 = bull (GREEN), +1 = bear (RED)
    return df_st["st_dir"] == -1

# =============================================================================
# POSITION TRACKER  –  in-memory state
# =============================================================================

class PositionTracker:
    """Tracks the single active trade in memory."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.active      = False
        self.direction   = None    # "LONG" or "SHORT"
        self.entry_price = 0.0
        self.entry_time  = None
        self.signal_type = None    # "BUY_A" / "BUY_B" / "SELL_A" / "SELL_B"
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
        # 0.001 BTC per lot (matches backtest CONTRACT_VALUE)
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
    log.info("BTC Renko+Supertrend Live Trading Bot STARTING")
    log.info(f"Mode      : {'TESTNET' if TESTNET else 'LIVE'}")
    log.info(f"Lots      : {POSITION_SIZE} ({LOT_MULTIPLIER}x multiplier)")
    log.info(f"Renko     : box={RENKO_BOX_SIZE}")
    log.info(f"ST        : ATR={ST_ATR_LEN} Factor={ST_FACTOR}")
    log.info(f"Signals   : BUY_A, BUY_B, SELL_A, SELL_B")
    log.info("=" * 60)

    # ── Initialise components ────────────────────────────────────────────────
    fetcher  = DeltaExchangeFetcher()
    orders   = OrderManager(API_KEY, API_SECRET, testnet=TESTNET)
    executor = SignalExecutor(
        swing_l        = SWING_L,
        swing_r        = SWING_R,
        sr_tolerance   = SR_TOLERANCE,
        min_age_horiz  = MIN_AGE_HORIZ,
        cooldown_boxes = COOLDOWN_BOXES,
        anchor_lookback= ANCHOR_LOOKBACK
    )
    tracker  = PositionTracker()

    # ── Sync with exchange: check if position already open ───────────────────
    pos = orders.get_position()
    if pos["success"] and pos["size"] != 0:
        log.warning(f"[Startup] Existing position detected: "
                    f"{pos['direction']} {abs(pos['size'])} lots "
                    f"@ {pos['entry_price']:.0f}")
        log.warning("[Startup] Tracking existing position. Will exit on next ST flip.")
        tracker.open_trade(
            direction  = pos["direction"],
            entry_price= pos["entry_price"],
            signal_type= "EXISTING",
            order_id   = None,
            size       = abs(pos["size"])
        )

    # ── State for new-box detection ──────────────────────────────────────────
    last_box_count = 0
    last_box_close = None

    log.info(f"[Loop] Starting poll loop every {POLL_INTERVAL_SEC}s ...")

    while True:
        try:
            # ── 1. Fetch latest candles ──────────────────────────────────────
            df_2h = fetch_recent_candles(fetcher, n_30m=WARMUP_CANDLES)
            if df_2h.empty:
                log.warning("[Loop] Empty candle data, retrying in 60s")
                time.sleep(60)
                continue

            # ── 2. Build Renko boxes ─────────────────────────────────────────
            df_renko = build_renko_boxes(df_2h)
            if df_renko.empty:
                log.warning("[Loop] Empty Renko data, retrying in 60s")
                time.sleep(60)
                continue

            current_box_count = len(df_renko)
            current_box_close = df_renko["renko_close"].iloc[-1]

            # ── 3. Check if a new box has closed ─────────────────────────────
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

            # ── 4. Compute Supertrend ────────────────────────────────────────
            st_bull = get_supertrend_bull(df_renko)

            # ── 5. Run signal detector ───────────────────────────────────────
            signals = executor.update(df_renko, st_bull)

            log.info(f"[Signals] BUY_A={signals['BUY_A']} "
                     f"BUY_B={signals['BUY_B']} "
                     f"SELL_A={signals['SELL_A']} "
                     f"SELL_B={signals['SELL_B']} | "
                     f"ST_flip_bull={signals['st_flip_bull']} "
                     f"ST_flip_bear={signals['st_flip_bear']}")

            # ── 6. EXIT logic: Supertrend flip ───────────────────────────────
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

            # ── 7. ENTRY logic: new signal ───────────────────────────────────
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
                # Opposite position open -> close it first
                if tracker.active and tracker.direction != entry_dir:
                    log.info(f"[Entry] Opposite signal {entry_signal} | "
                             f"closing existing {tracker.direction} first")
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

                # Open new trade only if now flat
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

            # ── 8. Sleep until next poll ─────────────────────────────────────
            time.sleep(POLL_INTERVAL_SEC)

        except KeyboardInterrupt:
            log.info("[Loop] Keyboard interrupt. Shutting down.")
            break

        except Exception as e:
            log.error(f"[Loop] Unhandled exception: {e}")
            log.error(traceback.format_exc())
            log.info("[Loop] Sleeping 120s before retry...")
            time.sleep(120)

    log.info("[Loop] Live trading bot stopped.")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    run_live()
