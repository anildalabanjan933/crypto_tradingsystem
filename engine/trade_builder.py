# engine/trade_builder.py
# Responsibility: Build complete trade records from entry and exit signals
# Charge Model: AlgoTest post-backtest method

import pandas as pd
from datetime import datetime
from utils import format_date, round_price, round_percent, usd_to_inr, format_currency

LOT_NOTIONAL_USD = 100.0


class TradeBuilder:

    def __init__(self, size_qty=1, initial_capital=100000, charges_config=None,
                 margin_config=None, contract_unit=0.001, slippage=0):
        self.size_qty           = size_qty
        self.initial_capital    = initial_capital
        self.charges_config     = charges_config or {}
        self.margin_config      = margin_config or {}
        self.contract_unit      = contract_unit
        self.slippage           = slippage          # $ per side
        self.trades             = []
        self.cumulative_pnl     = 0
        self.cumulative_pnl_inr = 0
        self.trade_number       = 0

    # ── build_trades, _create_trade_record, all helpers UNCHANGED ──
    # Only _apply_charges updated below

    def build_trades(self, signals):
        sorted_signals = sorted(signals, key=lambda x: x["timestamp"])
        print(f"Building trades from {len(sorted_signals)} total signals")
        active_trade = None
        for signal in sorted_signals:
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
        self.trade_number += 1

        entry_price     = float(entry_signal["price"])
        exit_price      = float(exit_signal["price"])
        direction       = entry_signal.get("direction", "short").lower()
        entry_type      = entry_signal.get("entry_type", "FIRST_ENTRY")
        exit_reason     = exit_signal.get("exit_type", exit_signal.get("exit_reason", "PATTERN_EXIT"))
        stop_loss_price = float(entry_signal.get("sl_price", entry_signal.get("stop_loss", 0.0)))

        actual_quantity = self.size_qty * self.contract_unit
        size_value      = entry_price * actual_quantity

        if direction == "short":
            gross_pnl = (entry_price - exit_price) * actual_quantity
        else:
            gross_pnl = (exit_price - entry_price) * actual_quantity

        duration_hours = self._calc_duration_hours(
            entry_signal["timestamp"], exit_signal["timestamp"]
        )

        net_pnl, charges_breakdown = self._apply_charges(
            gross_pnl=gross_pnl,
            duration_hours=duration_hours
        )

        self.cumulative_pnl += net_pnl
        usd_to_inr_rate      = self.charges_config.get("usd_to_inr_rate", 84)
        net_pnl_inr          = usd_to_inr(net_pnl, usd_to_inr_rate)
        self.cumulative_pnl_inr += net_pnl_inr

        net_pnl_pct = round_percent(
            (net_pnl / self.initial_capital) * 100
        ) if self.initial_capital else 0.0

        cumulative_pnl_pct = round_percent(
            (self.cumulative_pnl / self.initial_capital) * 100
        ) if self.initial_capital else 0.0

        margin_required = self._calculate_margin(entry_price, actual_quantity)

        (favorable_excursion, favorable_excursion_pct,
         adverse_excursion,   adverse_excursion_pct) = self._calculate_excursion(
            entry_price, exit_price, direction
        )

        entry_datetime_str = self._ts_to_str(entry_signal["timestamp"])
        exit_datetime_str  = self._ts_to_str(exit_signal["timestamp"])

        trade_record = {
            "trade_number"           : self.trade_number,
            "entry_type"             : entry_type,
            "exit_type"              : exit_reason,
            "entry_datetime"         : entry_datetime_str,
            "exit_datetime"          : exit_datetime_str,
            "direction"              : direction,
            "entry_price"            : round_price(entry_price),
            "exit_price"             : round_price(exit_price),
            "size_qty"               : self.size_qty,
            "actual_quantity"        : round_price(actual_quantity),
            "size_value"             : round_price(size_value),
            "lot_notional_usd"       : LOT_NOTIONAL_USD,
            "gross_pnl"              : round_price(gross_pnl),
            "net_pnl"                : round_price(net_pnl),
            "net_pnl_inr"            : round_price(net_pnl_inr),
            "net_pnl_pct"            : net_pnl_pct,
            "favorable_excursion"    : round_price(favorable_excursion),
            "favorable_excursion_pct": round_percent(favorable_excursion_pct),
            "adverse_excursion"      : round_price(adverse_excursion),
            "adverse_excursion_pct"  : round_percent(adverse_excursion_pct),
            "cumulative_pnl"         : round_price(self.cumulative_pnl),
            "cumulative_pnl_inr"     : round_price(self.cumulative_pnl_inr),
            "cumulative_pnl_pct"     : cumulative_pnl_pct,
            "margin_required"        : round_price(margin_required),
            "taker_fees_usd"         : round_price(charges_breakdown["taker_fees"]),
            "slippage_usd"           : round_price(charges_breakdown["slippage"]),
            "slippage_applied"       : self.slippage,
            "funding_usd"            : round_price(charges_breakdown["funding"]),
            "insurance_usd"          : round_price(charges_breakdown["insurance"]),
            "tax_usd"                : 0.0,
            "total_charges_usd"      : round_price(charges_breakdown["total_charges"]),
            "stop_loss"              : round_price(stop_loss_price),
        }

        return trade_record

    def _apply_charges(self, gross_pnl, duration_hours=8):
        """
        Slippage: self.slippage $ per side × 2 sides (entry + exit)
        All other charges unchanged.
        """
        cb = {}

        # Taker fees
        taker_fee_rate   = self.charges_config.get('taker_fee_rate', 0.0005)
        cb["taker_fees"] = LOT_NOTIONAL_USD * taker_fee_rate * 2

        # Slippage — $ per side × 2 sides (entry + exit)
        cb["slippage"] = self.slippage * 2

        # Funding
        funding_rate_annual    = self.charges_config.get('funding_rate_annual', 0.1095)
        funding_interval_hours = self.charges_config.get('funding_interval_hours', 8)
        intervals_per_year     = (365 * 24) / funding_interval_hours
        rate_per_interval      = funding_rate_annual / intervals_per_year
        funding_intervals      = duration_hours / funding_interval_hours
        cb["funding"]          = LOT_NOTIONAL_USD * rate_per_interval * funding_intervals

        cb["insurance"] = 0.0
        cb["tax"]       = 0.0

        cb["total_charges"] = cb["taker_fees"] + cb["slippage"] + cb["funding"]

        net_pnl = gross_pnl - cb["total_charges"]
        return net_pnl, cb

    def _ts_to_str(self, ts) -> str:
        try:
            if isinstance(ts, pd.Timestamp):
                return ts.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(ts, datetime):
                return ts.strftime("%Y-%m-%d %H:%M:%S")
            else:
                return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(ts)

    def _calc_duration_hours(self, entry_ts, exit_ts) -> float:
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
            return 8.0

    def _calculate_margin(self, entry_price, actual_quantity):
        leverage = self.margin_config.get('leverage', 10)
        return (entry_price * actual_quantity) / leverage

    def _calculate_excursion(self, entry_price, exit_price, direction):
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
        else:
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
