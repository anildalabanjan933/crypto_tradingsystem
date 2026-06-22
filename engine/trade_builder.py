# engine/trade_builder.py
# Responsibility: Build complete trade records from entry and exit signals
# Charge Model: AlgoTest post-backtest method
# - Slippage, taker fees, funding applied per trade AFTER simulation
# - Tax applied post-run in metrics_calculator.py (not per trade)
# - Entry/exit prices NEVER modified during simulation

import pandas as pd
from datetime import datetime
from utils import format_date, round_price, round_percent, usd_to_inr, format_currency

# ─────────────────────────────────────────────
# CHARGE CONSTANTS
# All charges applied to LOT_NOTIONAL_USD (100 USD fixed)
# NOT to full BTC position notional
# ─────────────────────────────────────────────
LOT_NOTIONAL_USD = 100.0


class TradeBuilder:
    """
    Builds complete trade records from entry and exit signals.

    Signal field contract (what strategy must emit):
    ─────────────────────────────────────────────────
    ENTRY signal:
      signal_type : 'ENTRY'            (uppercase)
      entry_type  : 'FIRST_ENTRY' or 'RE_ENTRY'
      price       : float              (entry price)
      sl_price    : float              (Supertrend SL at entry)
      timestamp   : pd.Timestamp or datetime
      sma10, sma20, adx, column_idx   (optional metadata)

    EXIT signal:
      signal_type : 'EXIT'             (uppercase)
      exit_type   : 'SL_HIT_SUPERTREND' or 'DOUBLE_TOP'
      price       : float              (exit price)
      timestamp   : pd.Timestamp or datetime

    Direction is inferred from strategy type (always 'short' for Bearish 4B).
    No 'direction' field required in signals.
    """

    def __init__(self, size_qty=1, initial_capital=100000, charges_config=None,
                 margin_config=None, contract_unit=0.001):
        self.size_qty         = size_qty
        self.initial_capital  = initial_capital
        self.charges_config   = charges_config or {}
        self.margin_config    = margin_config or {}
        self.contract_unit    = contract_unit
        self.trades           = []
        self.cumulative_pnl   = 0
        self.cumulative_pnl_inr = 0
        self.trade_number     = 0

    def build_trades(self, signals):
        """
        Build trades by matching ENTRY/EXIT signal pairs in chronological order.

        Matching rules:
        - ENTRY signal (signal_type == 'ENTRY') opens a trade
        - EXIT signal  (signal_type == 'EXIT')  closes the open trade
        - Direction is always 'short' for Bearish 4B (no direction field needed)
        - Unmatched ENTRY at end of data is discarded with a warning
        """
        # Sort by timestamp — handles both pd.Timestamp and datetime objects
        sorted_signals = sorted(signals, key=lambda x: x["timestamp"])

        print(f"Building trades from {len(sorted_signals)} total signals")

        active_trade = None

        for signal in sorted_signals:
            # Case-insensitive match — handles 'ENTRY', 'entry', 'Entry'
            signal_type = signal.get("signal_type", "").upper()

            if signal_type == "ENTRY" and active_trade is None:
                active_trade = signal

            elif signal_type == "EXIT" and active_trade is not None:
                trade_record = self._create_trade_record(active_trade, signal)
                self.trades.append(trade_record)
                active_trade = None

        if active_trade is not None:
            print(f"  Warning: Unclosed trade (Entry at {active_trade['timestamp']}) "
                  f"at end of data. Skipping.")

        print(f"Built {len(self.trades)} complete trade records")
        return self.trades

    def _create_trade_record(self, entry_signal, exit_signal):
        """
        Build a complete trade record from entry and exit signals.

        Reads these fields from signals:
          entry_signal: timestamp, price, sl_price, entry_type
          exit_signal:  timestamp, price, exit_type
        """
        self.trade_number += 1

        # ── Extract core fields ────────────────────────────────────────
        entry_price = float(entry_signal["price"])
        exit_price  = float(exit_signal["price"])

        # Direction: Bearish 4B is always short
        # Extend here if supporting long strategies in future
        direction   = entry_signal.get("direction", "short").lower()

        # entry_type: 'FIRST_ENTRY' or 'RE_ENTRY'
        entry_type  = entry_signal.get("entry_type", "FIRST_ENTRY")

        # exit_type: 'SL_HIT_SUPERTREND' or 'DOUBLE_TOP'
        # FIXED: reads 'exit_type' key (strategy emits 'exit_type', not 'exit_reason')
        exit_reason = exit_signal.get("exit_type", exit_signal.get("exit_reason", "PATTERN_EXIT"))

        # SL price: reads 'sl_price' key (strategy emits 'sl_price', not 'stop_loss')
        stop_loss_price = float(entry_signal.get("sl_price", entry_signal.get("stop_loss", 0.0)))

        # ── Quantity calculation ───────────────────────────────────────
        actual_quantity = self.size_qty * self.contract_unit
        size_value      = entry_price * actual_quantity   # display only

        # ── Gross PnL ─────────────────────────────────────────────────
        if direction == "short":
            gross_pnl = (entry_price - exit_price) * actual_quantity
        else:
            gross_pnl = (exit_price - entry_price) * actual_quantity

        # ── Duration ──────────────────────────────────────────────────
        # FIXED: handles pd.Timestamp, datetime, and Unix int
        duration_hours = self._calc_duration_hours(
            entry_signal["timestamp"], exit_signal["timestamp"]
        )

        # ── Apply charges ─────────────────────────────────────────────
        net_pnl, charges_breakdown = self._apply_charges(
            gross_pnl=gross_pnl,
            duration_hours=duration_hours
        )

        # ── Cumulative PnL ────────────────────────────────────────────
        self.cumulative_pnl += net_pnl
        usd_to_inr_rate      = self.charges_config.get("usd_to_inr_rate", 84)
        net_pnl_inr          = usd_to_inr(net_pnl, usd_to_inr_rate)
        self.cumulative_pnl_inr += net_pnl_inr

        # ── PnL percentages ───────────────────────────────────────────
        net_pnl_pct = round_percent(
            (net_pnl / self.initial_capital) * 100
        ) if self.initial_capital else 0.0

        cumulative_pnl_pct = round_percent(
            (self.cumulative_pnl / self.initial_capital) * 100
        ) if self.initial_capital else 0.0

        # ── Margin ────────────────────────────────────────────────────
        margin_required = self._calculate_margin(entry_price, actual_quantity)

        # ── Excursion ─────────────────────────────────────────────────
        (favorable_excursion, favorable_excursion_pct,
         adverse_excursion,   adverse_excursion_pct) = self._calculate_excursion(
            entry_price, exit_price, direction
        )

        # ── Datetime strings ──────────────────────────────────────────
        entry_datetime_str = self._ts_to_str(entry_signal["timestamp"])
        exit_datetime_str  = self._ts_to_str(exit_signal["timestamp"])

        trade_record = {
            "trade_number"          : self.trade_number,
            "entry_type"            : entry_type,
            "exit_type"             : exit_reason,
            "entry_datetime"        : entry_datetime_str,
            "exit_datetime"         : exit_datetime_str,
            "direction"             : direction,
            "entry_price"           : round_price(entry_price),
            "exit_price"            : round_price(exit_price),
            "size_qty"              : self.size_qty,
            "actual_quantity"       : round_price(actual_quantity),
            "size_value"            : round_price(size_value),
            "lot_notional_usd"      : LOT_NOTIONAL_USD,
            "gross_pnl"             : round_price(gross_pnl),
            "net_pnl"               : round_price(net_pnl),
            "net_pnl_inr"           : round_price(net_pnl_inr),
            "net_pnl_pct"           : net_pnl_pct,
            "favorable_excursion"   : round_price(favorable_excursion),
            "favorable_excursion_pct": round_percent(favorable_excursion_pct),
            "adverse_excursion"     : round_price(adverse_excursion),
            "adverse_excursion_pct" : round_percent(adverse_excursion_pct),
            "cumulative_pnl"        : round_price(self.cumulative_pnl),
            "cumulative_pnl_inr"    : round_price(self.cumulative_pnl_inr),
            "cumulative_pnl_pct"    : cumulative_pnl_pct,
            "margin_required"       : round_price(margin_required),
            "taker_fees_usd"        : round_price(charges_breakdown["taker_fees"]),
            "slippage_usd"          : round_price(charges_breakdown["slippage"]),
            "funding_usd"           : round_price(charges_breakdown["funding"]),
            "insurance_usd"         : round_price(charges_breakdown["insurance"]),
            "tax_usd"               : 0.0,
            "total_charges_usd"     : round_price(charges_breakdown["total_charges"]),
            "stop_loss"             : round_price(stop_loss_price),
        }

        return trade_record

    # ══════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════

    def _ts_to_str(self, ts) -> str:
        """Convert any timestamp type to readable string."""
        try:
            if isinstance(ts, pd.Timestamp):
                return ts.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(ts, datetime):
                return ts.strftime("%Y-%m-%d %H:%M:%S")
            else:
                # Assume Unix int/float
                return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(ts)

    def _calc_duration_hours(self, entry_ts, exit_ts) -> float:
        """
        Calculate trade duration in hours.
        Handles pd.Timestamp, datetime, and Unix int/float.
        """
        try:
            def to_dt(ts):
                if isinstance(ts, pd.Timestamp):
                    return ts.to_pydatetime()
                elif isinstance(ts, datetime):
                    return ts
                else:
                    return datetime.fromtimestamp(float(ts))

            entry_dt = to_dt(entry_ts)
            exit_dt  = to_dt(exit_ts)
            hours    = (exit_dt - entry_dt).total_seconds() / 3600
            return max(hours, 0.0)
        except Exception:
            return 8.0   # fallback: 1 funding interval

    def _calculate_margin(self, entry_price, actual_quantity):
        """margin = (entry_price × actual_quantity) / leverage"""
        leverage = self.margin_config.get('leverage', 10)
        return (entry_price * actual_quantity) / leverage

    def _apply_charges(self, gross_pnl, duration_hours=8):
        """
        Calculate per-trade charges. Returns (net_pnl, breakdown).

        All charges on LOT_NOTIONAL_USD (100 USD):
          Taker fee : 0.05% × 2 sides = 0.10 USD
          Slippage  : 5.00% total     = 5.00 USD
          Funding   : 0.01% per 8H interval
          Insurance : 0.00 USD
          Tax       : 0.00 USD (post-run in metrics_calculator.py)
        """
        cb = {}

        # Taker fees
        taker_fee_rate   = self.charges_config.get('taker_fee_rate', 0.0005)
        cb["taker_fees"] = LOT_NOTIONAL_USD * taker_fee_rate * 2   # entry + exit

        # Slippage
        slippage_rate    = self.charges_config.get('slippage_rate', 0.05)
        cb["slippage"]   = LOT_NOTIONAL_USD * slippage_rate

        # Funding
        funding_rate_annual    = self.charges_config.get('funding_rate_annual', 0.1095)
        funding_interval_hours = self.charges_config.get('funding_interval_hours', 8)
        intervals_per_year     = (365 * 24) / funding_interval_hours
        rate_per_interval      = funding_rate_annual / intervals_per_year
        funding_intervals      = duration_hours / funding_interval_hours
        cb["funding"]          = LOT_NOTIONAL_USD * rate_per_interval * funding_intervals

        # Insurance and tax
        cb["insurance"] = 0.0
        cb["tax"]       = 0.0

        cb["total_charges"] = cb["taker_fees"] + cb["slippage"] + cb["funding"]

        net_pnl = gross_pnl - cb["total_charges"]
        return net_pnl, cb

    def _calculate_excursion(self, entry_price, exit_price, direction):
        """Calculate favorable and adverse excursion."""
        if direction in ["long", "buy"]:
            if exit_price > entry_price:
                fe  = exit_price - entry_price
                fep = (fe / entry_price) * 100
                ae  = 0.0
                aep = 0.0
            else:
                fe  = 0.0
                fep = 0.0
                ae  = entry_price - exit_price
                aep = (ae / entry_price) * 100
        else:  # short
            if entry_price > exit_price:
                fe  = entry_price - exit_price
                fep = (fe / entry_price) * 100
                ae  = 0.0
                aep = 0.0
            else:
                fe  = 0.0
                fep = 0.0
                ae  = exit_price - entry_price
                aep = (ae / entry_price) * 100

        return fe, fep, ae, aep
