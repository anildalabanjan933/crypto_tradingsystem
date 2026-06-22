# engine/renko_backtest_engine.py
# Renko backtest engine - standalone, bypasses 1M-first engine
# HTML report matches PnF algotest format exactly
# Adds: R:R column, Charges Breakdown, Monthly/Yearly Returns, Plotly equity + drawdown
# Post-backtest: slippage applied via menu; commission/tax/funding from charges_config

import os
import json
import math
import pandas as pd
import numpy as np
from datetime import datetime

from engine.trade_builder import TradeBuilder
from engine.metrics_calculator import MetricsCalculator
from strategies.renko_options_strategy import RenkoOptionsStrategy
from indicators.renko import RenkoBuilder, SupertrendIndicator, SwingDetector
from config.charges_config import charges_config


class RenkoBacktestEngine:
    """
    Standalone engine for Renko-based options strategy backtest.

    Key differences from BacktestEngine:
      - Loads 2h OHLCV CSV directly (no 1M aggregation)
      - Builds Renko + Supertrend + Swings internally
      - Passes prepared renko_df to strategy.generate_signals()
      - Injects options_pnl from strategy signals into trade records
      - Saves raw trades (zero slippage) first
      - Post-backtest slippage menu: user enters custom USD/side
      - Commission/tax/funding read from charges_config
      - Generates HTML report matching PnF algotest format
    """

    def __init__(self, config: dict):
        self.config          = config
        self.csv_path        = config['csv_path']
        self.symbol          = config.get('symbol', 'BTCUSD')
        self.initial_capital = float(config.get('initial_capital', 1000.0))
        self.future_lots     = int(config.get('future_lots', 100))
        self.strategy_mode   = int(config.get('strategy_mode', 1))
        self.start_date      = config.get('start_date', None)
        self.end_date        = config.get('end_date', None)
        self.usd_to_inr      = float(charges_config.get('usd_to_inr_rate', 84.0))

        # ── Charges from charges_config (authoritative source) ────────
        self.taker_fee_rate      = float(charges_config.get('taker_fee_rate', 0.0005))
        self.tax_rate            = float(charges_config.get('tax_rate', 0.10))
        self.funding_rate_annual = float(charges_config.get('funding_rate_annual', 0.1095))
        self.funding_interval_h  = float(charges_config.get('funding_interval_hours', 8))
        self.lot_notional_usd    = float(charges_config.get('lot_notional_usd', 100.0))
        self.contract_value      = float(charges_config.get('contract_value', 0.001))

        # ── Slippage: set to 0 initially, applied post-backtest ───────
        self.slippage_usd = 0.0

        self.df        = None
        self.renko_df  = None
        self.strategy  = None
        self.signals   = []
        self.raw_trades = []   # zero-slippage trades saved here
        self.trades    = []    # final trades after slippage applied
        self.metrics   = {}

    # ── Public entry point ────────────────────────────────────────────
    def run(self) -> dict:
        print("=" * 70)
        print(f"RENKO BACKTEST ENGINE - {self.symbol}")
        print(f"Mode: {self.strategy_mode} | Lots: {self.future_lots} | "
              f"Capital: ${self.initial_capital:,.0f}")
        print("=" * 70)

        print("\n[Step 1] Loading 2h data...")
        self._load_data()

        print("\n[Step 2] Building Renko + indicators...")
        self._build_renko()

        print("\n[Step 3] Running strategy signals...")
        self._run_strategy()

        print("\n[Step 4] Building trades (zero slippage)...")
        self._build_trades()

        print("\n[Step 5] Injecting options P&L...")
        self._inject_options_pnl()

        print("\n[Step 6] Post-backtest slippage menu...")
        self._apply_slippage_menu()

        print("\n[Step 7] Calculating metrics...")
        self._calculate_metrics()

        print("\n[Step 8] Saving outputs...")
        self._save_outputs()

        return self.metrics

    # ── Step 1: Load CSV ──────────────────────────────────────────────
    def _load_data(self):
        df = pd.read_csv(self.csv_path)

        dt_col = None
        for c in ['datetime', 'timestamp', 'time', 'date']:
            if c in df.columns:
                dt_col = c
                break
        if dt_col is None:
            raise ValueError(f"No datetime column found in {self.csv_path}")

        df['datetime'] = pd.to_datetime(df[dt_col])
        df = df.sort_values('datetime').reset_index(drop=True)

        if 'volume' in df.columns:
            before = len(df)
            df = df[df['volume'] > 0].reset_index(drop=True)
            print(f"  Loaded {before} bars | Clean: {len(df)} bars | "
                  f"{df['datetime'].iloc[0].date()} to {df['datetime'].iloc[-1].date()}")
        else:
            print(f"  Loaded {len(df)} bars | "
                  f"{df['datetime'].iloc[0].date()} to {df['datetime'].iloc[-1].date()}")

        if self.start_date:
            df = df[df['datetime'] >= pd.to_datetime(self.start_date)]
        if self.end_date:
            df = df[df['datetime'] <= pd.to_datetime(self.end_date)]
        df = df.reset_index(drop=True)
        print(f"  After date filter: {len(df)} bars")

        self.df = df

    # ── Step 2: Build Renko + indicators ─────────────────────────────
    def _build_renko(self):
        box_size = self.config.get('renko_box', 200)

        builder  = RenkoBuilder(box_size=box_size)
        renko_df = builder.build(self.df['close'].values)

        renko_df['timestamp'] = renko_df['bar_index'].apply(
            lambda idx: self.df['datetime'].iloc[
                min(int(idx), len(self.df) - 1)
            ].strftime('%Y-%m-%dT%H:%M:%S')
        )

        st = SupertrendIndicator(
            atr_period = self.config.get('st_atr_len', 5),
            factor     = self.config.get('st_factor', 4.0)
        )
        renko_df = st.calculate(renko_df)

        sd = SwingDetector(
            swing_left  = self.config.get('swing_left', 2),
            swing_right = self.config.get('swing_right', 2)
        )
        renko_df = sd.detect(renko_df)

        self.renko_df = renko_df

        bull = int((renko_df['renko_dir'] == 1).sum())
        bear = int((renko_df['renko_dir'] == -1).sum())
        print(f"  Renko bars: {len(renko_df)} | Bull: {bull} | Bear: {bear}")

    # ── Step 3: Run strategy signals ─────────────────────────────────
    def _run_strategy(self):
        strategy_config         = dict(self.config)
        strategy_config['mode'] = self.config.get('strategy_mode', 1)

        strategy      = RenkoOptionsStrategy(strategy_config)
        self.strategy = strategy
        self.signals  = strategy.generate_signals(self.renko_df)

        entry_signals = [s for s in self.signals if s['signal_type'] == 'ENTRY']
        exit_signals  = [s for s in self.signals if s['signal_type'] == 'EXIT']
        buy_a  = sum(1 for s in entry_signals if s.get('entry_type') == 'BUY_A')
        buy_b  = sum(1 for s in entry_signals if s.get('entry_type') == 'BUY_B')
        sell_a = sum(1 for s in entry_signals if s.get('entry_type') == 'SELL_A')
        sell_b = sum(1 for s in entry_signals if s.get('entry_type') == 'SELL_B')

        print(f"  Total signals : {len(self.signals)}")
        print(f"  Entries       : {len(entry_signals)} "
              f"(BUY_A={buy_a}, BUY_B={buy_b}, SELL_A={sell_a}, SELL_B={sell_b})")
        print(f"  Exits         : {len(exit_signals)}")

    # ── Step 4: Build trades (zero slippage) ──────────────────────────
    def _build_trades(self):
        print(f"  Building trades from {len(self.signals)} signals (zero slippage)")

        charges_cfg = {
            'taker_fee_rate': self.taker_fee_rate,
            'slippage_rate': 0.0,
            'funding_rate_annual': self.funding_rate_annual,
            'funding_interval_hours': self.funding_interval_h,
            'usd_to_inr_rate': self.usd_to_inr,
            'tax_rate': 0.0,
        }

        builder = TradeBuilder(
            size_qty=self.future_lots,
            initial_capital=self.initial_capital,
            charges_config=charges_cfg,
            contract_unit=self.contract_value,
        )

        self.raw_trades = builder.build_trades(self.signals)

        # ── Inject sl_price from entry signals into trade records ─────
        # TradeBuilder does not carry sl_price through to trade dict;
        # inject manually so R:R calculation works correctly.
        entry_sl_map = {}
        for sig in self.signals:
            if sig.get('signal_type') == 'ENTRY':
                ts = pd.Timestamp(sig['timestamp']).strftime('%Y-%m-%dT%H:%M:%S')
                entry_sl_map[ts] = sig.get('sl_price', 0.0)

        for trade in self.raw_trades:
            entry_dt = trade.get('entry_datetime', '')
            if entry_dt:
                ts_key = pd.Timestamp(entry_dt).strftime('%Y-%m-%dT%H:%M:%S')
                if ts_key in entry_sl_map:
                    trade['sl_price'] = entry_sl_map[ts_key]

        import copy
        self.trades = copy.deepcopy(self.raw_trades)
        print(f"  Built {len(self.trades)} trade records (raw, zero slippage)")

    # ── Step 5: Inject options P&L ────────────────────────────────────
    def _inject_options_pnl(self):
        exit_pnl_map = {}
        for sig in self.signals:
            if sig.get('signal_type') == 'EXIT':
                ts = pd.Timestamp(sig['timestamp']).strftime('%Y-%m-%dT%H:%M:%S')
                exit_pnl_map[ts] = sig.get('options_pnl', 0.0)

        injected = 0
        for trade in self.trades:
            exit_dt = trade.get('exit_datetime', '')
            if exit_dt:
                ts_key      = pd.Timestamp(exit_dt).strftime('%Y-%m-%dT%H:%M:%S')
                options_pnl = exit_pnl_map.get(ts_key, 0.0)
                future_net  = trade.get('net_pnl', 0.0)
                trade['future_net_pnl'] = future_net
                trade['options_pnl']    = options_pnl
                trade['net_pnl']        = future_net + options_pnl
                if options_pnl != 0.0:
                    injected += 1

        # Mirror into raw_trades as well so re-application preserves options_pnl
        import copy
        self.raw_trades = copy.deepcopy(self.trades)

        print(f"  Options P&L injected into {injected} trades")

    # ── Step 6: Post-backtest slippage menu ───────────────────────────
    def _apply_slippage_menu(self):
        """
        Prompt user for custom slippage per side (USD).
        Re-applies slippage to raw_trades without re-running backtest.
        All other charges already baked in via TradeBuilder (commission, tax).
        Funding applied separately in charges breakdown display only.
        """
        print("\n" + "─" * 50)
        print("  POST-BACKTEST SLIPPAGE CONFIGURATION")
        print("  (Commission, tax, funding already applied from charges_config)")
        print("─" * 50)
        print(f"  Current charges_config rates:")
        print(f"    Taker fee  : {self.taker_fee_rate * 100:.3f}% per side")
        print(f"    Tax rate   : {self.tax_rate * 100:.0f}% on profits")
        print(f"    Funding    : {self.funding_rate_annual * 100:.3f}% annual "
              f"({self.funding_interval_h}H interval)")
        print("─" * 50)

        while True:
            raw = input(
                "\n  Enter slippage per side in USD "
                "(e.g. 3 = $3/side, 0 = no slippage, Enter = skip): "
            ).strip()

            if raw == '':
                print("  Slippage skipped — using $0.00/side")
                self.slippage_usd = 0.0
                break

            try:
                val = float(raw)
                if val < 0:
                    print("  Invalid: slippage cannot be negative. Try again.")
                    continue
                self.slippage_usd = val
                print(f"  Slippage set to ${val:.2f}/side "
                      f"(${val * 2:.2f} round-trip per trade)")
                break
            except ValueError:
                print("  Invalid input. Enter a number like 3 or 5.5")

        # Re-apply slippage to trades from raw_trades baseline
        import copy
        self.trades = copy.deepcopy(self.raw_trades)

        slip_per_trade = self.slippage_usd * 2  # entry side + exit side
        adjusted = 0
        for trade in self.trades:
            if slip_per_trade > 0:
                original_future = trade.get('future_net_pnl', trade.get('net_pnl', 0.0))
                trade['net_pnl'] = trade.get('net_pnl', 0.0) - slip_per_trade
                trade['future_net_pnl'] = original_future - slip_per_trade
                adjusted += 1

        if slip_per_trade > 0:
            print(f"  Slippage applied to {adjusted} trades "
                  f"(-${slip_per_trade:.2f} each = "
                  f"-${slip_per_trade * adjusted:,.2f} total)")
        else:
            print("  No slippage applied.")

    # ── Step 7: Calculate metrics ─────────────────────────────────────
    def _calculate_metrics(self):
        charges_cfg_for_metrics = {
            'tax_rate': self.tax_rate,
            'usd_to_inr_rate': self.usd_to_inr,
        }

        calc = MetricsCalculator(
            trades=self.trades,
            initial_capital=self.initial_capital,
            charges_config=charges_cfg_for_metrics,
        )
        self.metrics = calc.calculate_all_metrics()

        # ── Win / Risk / Reward ───────────────────────────────────────
        wins = [t for t in self.trades if t.get('net_pnl', 0) > 0]
        losses = [t for t in self.trades if t.get('net_pnl', 0) <= 0]

        avg_win_usd = (sum(t['net_pnl'] for t in wins) / len(wins)) if wins else 0.0
        avg_loss_usd = (sum(t['net_pnl'] for t in losses) / len(losses)) if losses else 0.0

        avg_risk = abs(avg_loss_usd)
        avg_reward = abs(avg_win_usd)
        rr_ratio = (avg_reward / avg_risk) if avg_risk > 0 else 0.0

        breakeven_wr = (1 / (1 + rr_ratio) * 100) if rr_ratio > 0 else 0.0

        wr = self.metrics.get('win_rate', 0) / 100
        expected_val = (wr * avg_win_usd) + ((1 - wr) * avg_loss_usd)

        # ── Win Trade R:R (R:R of winning trades only) ────────────────
        win_rr_list = []
        for t in wins:
            try:
                entry_p = float(t.get('entry_price', 0))
                exit_p = float(t.get('exit_price', 0))
                sl_p = float(t.get('sl_price', 0))
                risk = abs(entry_p - sl_p)
                reward = abs(exit_p - entry_p)
                if risk > 0:
                    win_rr_list.append(reward / risk)
            except Exception:
                pass
        win_trade_rr = (sum(win_rr_list) / len(win_rr_list)) if win_rr_list else 0.0

        # Store all computed values back into metrics for HTML use
        self.metrics['avg_risk'] = avg_risk
        self.metrics['avg_reward'] = avg_reward
        self.metrics['rr_ratio'] = rr_ratio
        self.metrics['breakeven_wr'] = breakeven_wr
        self.metrics['expected_value'] = expected_val
        self.metrics['win_trade_rr'] = win_trade_rr
        self.metrics['slippage_usd'] = self.slippage_usd

        m = self.metrics
        print(f"\n  {'─' * 50}")
        print(f"  Total Trades    : {m.get('total_trades', 0)}")
        print(f"  Win Rate        : {m.get('win_rate', 0):.1f}%")
        print(f"  Net P&L (USD)   : ${m.get('total_pnl', 0):,.2f}")
        print(f"  Net P&L (INR)   : ₹{m.get('total_pnl_inr', 0):,.0f}")
        print(f"  Max Drawdown    : {m.get('max_drawdown', 0):.1f}%")
        print(f"  Profit Factor   : {m.get('profit_factor', 0):.2f}")
        print(f"  Avg Win         : ${avg_win_usd:,.2f}")
        print(f"  Avg Loss        : ${avg_loss_usd:,.2f}")
        print(f"  Avg Risk        : ${avg_risk:,.2f}")
        print(f"  Avg Reward      : ${avg_reward:,.2f}")
        print(f"  R:R Ratio       : {rr_ratio:.2f}")
        print(f"  Win Trade R:R   : {win_trade_rr:.2f}")
        print(f"  Breakeven WR    : {breakeven_wr:.1f}%")
        print(f"  Expected Value  : ${expected_val:,.2f}/trade")
        print(f"  Sharpe Ratio    : {m.get('sharpe_ratio', 0):.2f}")
        print(f"  Max Win Streak  : {m.get('max_win_streak', 0)}")
        print(f"  Max Loss Streak : {m.get('max_loss_streak', 0)}")
        print(f"  Avg Duration    : {m.get('avg_trade_duration_days', 0):.1f} days")
        print(f"  Total Tax       : ${m.get('total_tax', 0):,.2f}")
        print(f"  Slippage/side   : ${self.slippage_usd:.2f}")
        print(f"  {'─' * 50}")

    # ── Step 8: Save outputs ──────────────────────────────────────────
    def _save_outputs(self):
        os.makedirs('output', exist_ok=True)
        slug = f"renko_mode{self.strategy_mode}_{self.symbol.lower()}"

        csv_path  = f"output/{slug}_trades.csv"
        self._save_trade_csv(csv_path)
        print(f"  Trade CSV      : {csv_path}")

        val_path  = "output/renko_validation_trades.csv"
        self._save_validation_csv(val_path)
        print(f"  Validation CSV : {val_path}")

        html_path = f"output/{slug}_report.html"
        self._generate_html_report(html_path)
        print(f"  HTML Report    : {html_path}")

    # ── Save trade CSV ────────────────────────────────────────────────
    def _save_trade_csv(self, path: str):
        rows = []
        for t in self.trades:
            try:
                hold_days = (
                    pd.Timestamp(t.get('exit_datetime', '')) -
                    pd.Timestamp(t.get('entry_datetime', ''))
                ).days
            except Exception:
                hold_days = 0

            rows.append({
                'trade_number'      : t.get('trade_number', ''),
                'direction'         : t.get('direction', '').upper(),
                'entry_type'        : t.get('entry_type', ''),
                'exit_type'         : t.get('exit_type', ''),
                'entry_datetime'    : t.get('entry_datetime', ''),
                'entry_price'       : round(t.get('entry_price', 0), 1),
                'exit_datetime'     : t.get('exit_datetime', ''),
                'exit_price'        : round(t.get('exit_price', 0), 1),
                'size_qty'          : t.get('size_qty', self.future_lots),
                'future_net_pnl'    : round(t.get('future_net_pnl', t.get('net_pnl', 0)), 2),
                'options_pnl'       : round(t.get('options_pnl', 0), 4),
                'net_pnl'           : round(t.get('net_pnl', 0), 2),
                'net_pnl_inr'       : round(t.get('net_pnl', 0) * self.usd_to_inr, 0),
                'hold_days'         : hold_days,
                'slippage_applied'  : round(self.slippage_usd * 2, 2),
                'cumulative_pnl_pct': round(t.get('cumulative_pnl_pct', 0), 2),
            })

        pd.DataFrame(rows).to_csv(path, index=False)

    # ── Save validation CSV ───────────────────────────────────────────
    def _save_validation_csv(self, path: str):
        rows = []
        for t in self.trades:
            try:
                hold_days = (
                    pd.Timestamp(t.get('exit_datetime', '')) -
                    pd.Timestamp(t.get('entry_datetime', ''))
                ).days
            except Exception:
                hold_days = 0

            try:
                entry_p = float(t.get('entry_price', 0))
                exit_p  = float(t.get('exit_price', 0))
                sl_p    = float(t.get('sl_price', 0))
                risk    = abs(entry_p - sl_p)
                reward  = abs(exit_p - entry_p)
                rr      = round(reward / risk, 2) if risk > 0 else None
            except Exception:
                rr = None

            rows.append({
                'trade_num'      : t.get('trade_number', ''),
                'direction'      : t.get('direction', '').upper(),
                'entry_type'     : t.get('entry_type', ''),
                'exit_type'      : t.get('exit_type', ''),
                'entry_datetime' : t.get('entry_datetime', ''),
                'entry_price'    : round(t.get('entry_price', 0), 1),
                'exit_datetime'  : t.get('exit_datetime', ''),
                'exit_price'     : round(t.get('exit_price', 0), 1),
                'hold_days'      : hold_days,
                'gross_pnl_usd'  : round(t.get('future_net_pnl', t.get('net_pnl', 0)), 2),
                'net_pnl_usd'    : round(t.get('net_pnl', 0), 2),
                'rr_ratio'       : rr,
            })

        pd.DataFrame(rows).to_csv(path, index=False)

    # ── Generate HTML report ──────────────────────────────────────────
    def _generate_html_report(self, path: str):
        m   = self.metrics
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # ── Derived header values ─────────────────────────────────────
        total_trades = m.get('total_trades', 0)
        win_rate_pct = m.get('win_rate', 0)  # already 0-100, no * 100
        net_pnl_usd = m.get('total_pnl', 0)
        net_pnl_inr = m.get('total_pnl_inr', 0)
        max_dd_pct = m.get('max_drawdown', 0)  # already negative %, no * 100
        profit_factor = m.get('profit_factor', 0)
        sharpe = m.get('sharpe_ratio', 0)
        avg_dur = m.get('avg_trade_duration_days', 0)
        avg_win = m.get('avg_win', 0)
        avg_loss = m.get('avg_loss', 0)
        max_win_str = m.get('max_win_streak', 0)
        max_loss_str = m.get('max_loss_streak', 0)
        total_tax = m.get('total_tax', 0)
        largest_win = m.get('largest_win', 0)
        largest_loss = m.get('largest_loss', 0)
        winning_trades = sum(1 for t in self.trades if t.get('net_pnl', 0) > 0)
        losing_trades = total_trades - winning_trades

        return_pct = (net_pnl_usd / self.initial_capital * 100) if self.initial_capital else 0
        initial_inr = self.initial_capital * self.usd_to_inr

        # ── W/R/R values ──────────────────────────────────────────────
        avg_risk      = m.get('avg_risk', 0)
        avg_reward    = m.get('avg_reward', 0)
        rr_ratio      = m.get('rr_ratio', 0)
        breakeven_wr  = m.get('breakeven_wr', 0)
        expected_val  = m.get('expected_value', 0)
        win_trade_rr  = m.get('win_trade_rr', 0)
        slippage_usd  = m.get('slippage_usd', 0)

        pnl_color_cls = 'positive' if net_pnl_usd >= 0 else 'negative'
        ret_color_cls = 'positive' if return_pct  >= 0 else 'negative'

        # Date range
        dates     = [t.get('entry_datetime', '') for t in self.trades if t.get('entry_datetime')]
        date_from = min(dates)[:10] if dates else ''
        date_to   = max(
            t.get('exit_datetime', '') for t in self.trades
            if t.get('exit_datetime')
        )[:10] if self.trades else ''

        # ── Chart data ────────────────────────────────────────────────
        eq_x, eq_y, dd_x, dd_y = self._build_chart_data()
        eq_x_json = json.dumps(eq_x)
        eq_y_json = json.dumps(eq_y)
        dd_x_json = json.dumps(dd_x)
        dd_y_json = json.dumps(dd_y)

        # ── Section builders ──────────────────────────────────────────
        monthly_rows                              = self._build_monthly_rows()
        yearly_rows                               = self._build_yearly_rows()
        charges_rows, gross_pnl_usd, total_charges_usd = self._build_charges_breakdown()
        trade_rows                                = self._build_trade_rows()

        mode_labels = {1: 'Momentum Hedged', 2: 'DTE-0 Income', 3: 'Deep ITM Covered'}
        mode_label  = mode_labels.get(self.strategy_mode, f'Mode {self.strategy_mode}')

        # ── Win Trade R:R color ───────────────────────────────────────
        wtr_color = '#27ae60' if win_trade_rr >= 2 else '#f39c12' if win_trade_rr >= 1 else '#e74c3c'
        wtr_cls   = 'positive' if win_trade_rr >= 2 else 'neutral' if win_trade_rr >= 1 else 'negative'

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report - Renko {mode_label} {self.symbol}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f5f5f5; color: #333; line-height: 1.6; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                   color: white; padding: 30px; border-radius: 8px;
                   margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header-info {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                        gap: 20px; margin-top: 20px; }}
        .header-item {{ background: rgba(255,255,255,0.1); padding: 15px; border-radius: 5px; }}
        .header-item label {{ font-size: 12px; opacity: 0.9; display: block; margin-bottom: 5px; }}
        .header-item value {{ font-size: 18px; font-weight: bold; }}
        .section {{ background: white; padding: 25px; margin-bottom: 20px;
                    border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .section h2 {{ font-size: 20px; margin-bottom: 20px; color: #667eea;
                       border-bottom: 2px solid #667eea; padding-bottom: 10px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 13px; }}
        th {{ background-color: #667eea; color: white; padding: 10px 12px;
              text-align: left; font-weight: 600; white-space: nowrap; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #ddd; white-space: nowrap; }}
        tr:hover {{ background-color: #f9f9f9; }}
        .positive {{ color: #27ae60; font-weight: bold; }}
        .negative {{ color: #e74c3c; font-weight: bold; }}
        .neutral  {{ color: #f39c12; font-weight: bold; }}
        .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                        gap: 15px; margin-top: 15px; }}
        .metric-card {{ background: #f9f9f9; padding: 15px; border-radius: 5px;
                        border-left: 4px solid #667eea; }}
        .metric-card label {{ font-size: 12px; color: #666; display: block; margin-bottom: 5px; }}
        .metric-card value {{ font-size: 18px; font-weight: bold; display: block; }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
        .rr-good  {{ color: #27ae60; font-weight: bold; }}
        .rr-ok    {{ color: #f39c12; font-weight: bold; }}
        .rr-bad   {{ color: #e74c3c; font-weight: bold; }}
        .rr-na    {{ color: #999; }}
        .tag-buy-a  {{ background:#d4edda; color:#155724; padding:2px 6px;
                       border-radius:3px; font-size:11px; font-weight:600; }}
        .tag-buy-b  {{ background:#cce5ff; color:#004085; padding:2px 6px;
                       border-radius:3px; font-size:11px; font-weight:600; }}
        .tag-sell-a {{ background:#f8d7da; color:#721c24; padding:2px 6px;
                       border-radius:3px; font-size:11px; font-weight:600; }}
        .tag-sell-b {{ background:#fff3cd; color:#856404; padding:2px 6px;
                       border-radius:3px; font-size:11px; font-weight:600; }}
        .dir-long  {{ color:#27ae60; font-weight:bold; }}
        .dir-short {{ color:#e74c3c; font-weight:bold; }}
        .table-scroll {{ overflow-x: auto; }}
        .charge-badge {{ background:#f0f4ff; border:1px solid #667eea; color:#667eea;
                         padding:2px 8px; border-radius:12px; font-size:11px;
                         font-weight:600; margin-left:8px; }}
    </style>
</head>
<body>
<div class="container">

    <!-- HEADER -->
    <div class="header">
        <h1>Renko {mode_label} - {self.symbol}</h1>
        <p>{self.symbol} | {date_from} to {date_to} | Box: ${self.config.get('renko_box', 200)} | ST ATR={self.config.get('st_atr_len', 5)} F={self.config.get('st_factor', 4.0)} | Slippage: ${slippage_usd:.2f}/side</p>
        <div class="header-info">
            <div class="header-item">
                <label>Initial Capital</label>
                <value>${self.initial_capital:,.0f} (₹{initial_inr:,.0f})</value>
            </div>
            <div class="header-item">
                <label>Total PnL (USD)</label>
                <value class="{pnl_color_cls}">${net_pnl_usd:,.2f}</value>
            </div>
            <div class="header-item">
                <label>Total PnL (INR)</label>
                <value class="{pnl_color_cls}">₹{net_pnl_inr:,.0f}</value>
            </div>
            <div class="header-item">
                <label>Return %</label>
                <value class="{ret_color_cls}">{return_pct:+.2f}%</value>
            </div>
            <div class="header-item">
                <label>Total Trades</label>
                <value>{total_trades}</value>
            </div>
            <div class="header-item">
                <label>Win Rate</label>
                <value>{win_rate_pct:.2f}%</value>
            </div>
            <div class="header-item">
                <label>Max Drawdown</label>
                <value class="negative">{max_dd_pct:.2f}%</value>
            </div>
            <div class="header-item">
                <label>Profit Factor</label>
                <value>{profit_factor:.2f}</value>
            </div>
        </div>
    </div>

    <!-- EQUITY CURVE -->
    <div class="section">
        <h2>&#x1F4C8; Equity Curve (USD)</h2>
        <div id="equity_chart" style="height:400px; width:100%;"></div>
    </div>

    <!-- DRAWDOWN -->
    <div class="section">
        <h2>&#x1F4C9; Drawdown (%)</h2>
        <div id="drawdown_chart" style="height:400px; width:100%;"></div>
    </div>

    <!-- MONTHLY RETURNS -->
    <div class="section">
        <h2>&#x1F4C5; Monthly Returns (USD)</h2>
        <table>
            <thead><tr><th>Month</th><th>PnL (USD)</th><th>PnL (INR)</th><th>PnL %</th></tr></thead>
            <tbody>{monthly_rows}</tbody>
        </table>
    </div>

    <!-- YEARLY RETURNS -->
    <div class="section">
        <h2>&#x1F4C5; Yearly Returns (USD)</h2>
        <table>
            <thead><tr><th>Year</th><th>PnL (USD)</th><th>PnL (INR)</th><th>PnL %</th></tr></thead>
            <tbody>{yearly_rows}</tbody>
        </table>
    </div>

    <!-- STRATEGY STATISTICS -->
    <div class="section">
        <h2>&#x1F4CA; Strategy Statistics</h2>
        <div class="metric-grid">

            <!-- Core counts -->
            <div class="metric-card">
                <label>Total Trades</label>
                <value>{total_trades}</value>
            </div>
            <div class="metric-card">
                <label>Winning Trades</label>
                <value class="positive">{winning_trades}</value>
            </div>
            <div class="metric-card">
                <label>Losing Trades</label>
                <value class="negative">{losing_trades}</value>
            </div>
            <div class="metric-card">
                <label>Win Rate (Actual)</label>
                <value class="{'positive' if win_rate_pct >= breakeven_wr else 'negative'}">{win_rate_pct:.2f}%</value>
            </div>

            <!-- Win / Risk / Reward -->
            <div class="metric-card" style="border-left-color:#27ae60">
                <label>Avg Win (Reward)</label>
                <value class="positive">${avg_reward:,.2f}</value>
            </div>
            <div class="metric-card" style="border-left-color:#e74c3c">
                <label>Avg Loss (Risk)</label>
                <value class="negative">${avg_risk:,.2f}</value>
            </div>
            <div class="metric-card" style="border-left-color:{'#27ae60' if rr_ratio >= 2 else '#f39c12' if rr_ratio >= 1 else '#e74c3c'}">
                <label>Risk : Reward Ratio</label>
                <value class="{'positive' if rr_ratio >= 2 else 'neutral' if rr_ratio >= 1 else 'negative'}">{rr_ratio:.2f} R</value>
            </div>
            <div class="metric-card" style="border-left-color:{wtr_color}">
                <label>Win Trade R:R</label>
                <value class="{wtr_cls}">{win_trade_rr:.2f} R</value>
            </div>
            <div class="metric-card" style="border-left-color:#9b59b6">
                <label>Breakeven Win Rate</label>
                <value class="{'positive' if win_rate_pct > breakeven_wr else 'negative'}">{breakeven_wr:.1f}%</value>
            </div>
            <div class="metric-card" style="border-left-color:#3498db">
                <label>Expected Value / Trade</label>
                <value class="{'positive' if expected_val >= 0 else 'negative'}">${expected_val:,.2f}</value>
            </div>

            <!-- Performance -->
            <div class="metric-card">
                <label>Profit Factor</label>
                <value class="{'positive' if profit_factor >= 1 else 'negative'}">{profit_factor:.2f}</value>
            </div>
            <div class="metric-card">
                <label>Total PnL (USD)</label>
                <value class="{pnl_color_cls}">${net_pnl_usd:,.2f}</value>
            </div>
            <div class="metric-card">
                <label>Largest Win</label>
                <value class="positive">${largest_win:,.2f}</value>
            </div>
            <div class="metric-card">
                <label>Largest Loss</label>
                <value class="negative">${largest_loss:,.2f}</value>
            </div>
            <div class="metric-card">
                <label>Expectancy (INR)</label>
                <value class="{'positive' if expected_val >= 0 else 'negative'}">₹{expected_val * self.usd_to_inr:,.0f}</value>
            </div>
            <div class="metric-card">
                <label>Max Drawdown</label>
                <value class="negative">{max_dd_pct:.2f}%</value>
            </div>
            <div class="metric-card">
                <label>Sharpe Ratio</label>
                <value>{sharpe:.2f}</value>
            </div>
            <div class="metric-card">
                <label>Max Win Streak</label>
                <value class="positive">{max_win_str}</value>
            </div>
            <div class="metric-card">
                <label>Max Loss Streak</label>
                <value class="negative">{max_loss_str}</value>
            </div>
            <div class="metric-card">
                <label>Avg Trade Duration</label>
                <value>{avg_dur:.1f} days</value>
            </div>

        </div>
    </div>

    <!-- CHARGES BREAKDOWN -->
    <div class="section">
        <h2>&#x1F4B0; Charges Breakdown (USD)
            <span class="charge-badge">Slippage ${slippage_usd:.2f}/side</span>
            <span class="charge-badge">Fee {self.taker_fee_rate * 100:.3f}%</span>
            <span class="charge-badge">Tax {self.tax_rate * 100:.0f}%</span>
        </h2>
        <table>
            <thead>
                <tr><th>Charge Type</th><th>Rate</th><th>Amount (USD)</th><th>Amount (INR)</th></tr>
            </thead>
            <tbody>
                {charges_rows}
                <tr style="background-color:#f0f0f0; font-weight:bold;">
                    <td colspan="2">Gross PnL (before charges)</td>
                    <td class="{'positive' if gross_pnl_usd >= 0 else 'negative'}">${gross_pnl_usd:,.2f}</td>
                    <td class="{'positive' if gross_pnl_usd >= 0 else 'negative'}">₹{gross_pnl_usd * self.usd_to_inr:,.0f}</td>
                </tr>
                <tr style="background-color:#f0f0f0; font-weight:bold;">
                    <td colspan="2">Total Charges</td>
                    <td class="negative">-${total_charges_usd:,.2f}</td>
                    <td class="negative">-₹{total_charges_usd * self.usd_to_inr:,.0f}</td>
                </tr>
                <tr style="background-color:#e8f5e9; font-weight:bold;">
                    <td colspan="2">Net PnL (after all charges)</td>
                    <td class="{pnl_color_cls}">${net_pnl_usd:,.2f}</td>
                    <td class="{pnl_color_cls}">₹{net_pnl_inr:,.0f}</td>
                </tr>
            </tbody>
        </table>
    </div>

    <!-- TRADE LOG -->
    <div class="section">
        <h2>&#x1F4CB; Trade Log</h2>
        <div class="table-scroll">
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Entry Time</th>
                    <th>Exit Time</th>
                    <th>Dir</th>
                    <th>Entry Type</th>
                    <th>Exit Type</th>
                    <th>Entry $</th>
                    <th>Exit $</th>
                    <th>Lots</th>
                    <th>Future P&amp;L</th>
                    <th>Options P&amp;L</th>
                    <th>Net P&amp;L $</th>
                    <th>Net P&amp;L ₹</th>
                    <th>Hold</th>
                    <th>R:R</th>
                    <th>Cum %</th>
                </tr>
            </thead>
            <tbody>
                {trade_rows}
            </tbody>
        </table>
        </div>
    </div>

    <div class="footer">
        <p>Generated on {now} | Renko {mode_label} | {self.symbol} | Box ${self.config.get('renko_box', 200)} | Lots {self.future_lots} | Slippage ${slippage_usd:.2f}/side | Fee {self.taker_fee_rate * 100:.3f}% | Tax {self.tax_rate * 100:.0f}%</p>
    </div>

</div>

<script>
Plotly.newPlot('equity_chart', [{{
    x: {eq_x_json},
    y: {eq_y_json},
    mode: 'lines',
    name: 'Cumulative PnL',
    fill: 'tozeroy',
    fillcolor: 'rgba(39,174,96,0.2)',
    line: {{ color: '#27ae60', width: 2 }}
}}], {{
    height: 400,
    hovermode: 'x unified',
    paper_bgcolor: 'white',
    plot_bgcolor: '#E5ECF6',
    title: {{ text: 'Equity Curve (USD)' }},
    xaxis: {{ title: {{ text: 'Date' }}, gridcolor: 'white' }},
    yaxis: {{ title: {{ text: 'Cumulative PnL (USD)' }}, gridcolor: 'white' }}
}}, {{ responsive: true }});

Plotly.newPlot('drawdown_chart', [{{
    x: {dd_x_json},
    y: {dd_y_json},
    mode: 'lines',
    name: 'Drawdown %',
    fill: 'tozeroy',
    fillcolor: 'rgba(231,76,60,0.2)',
    line: {{ color: '#e74c3c', width: 2 }}
}}], {{
    height: 400,
    hovermode: 'x unified',
    paper_bgcolor: 'white',
    plot_bgcolor: '#E5ECF6',
    title: {{ text: 'Drawdown (%)' }},
    xaxis: {{ title: {{ text: 'Date' }}, gridcolor: 'white' }},
    yaxis: {{ title: {{ text: 'Drawdown (%)' }}, gridcolor: 'white' }}
}}, {{ responsive: true }});
</script>

</body>
</html>"""

        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)

    # ── Chart data builders ───────────────────────────────────────────
    def _build_chart_data(self):
        eq_x, eq_y = [], []
        dd_x, dd_y = [], []

        cumulative = self.initial_capital
        peak       = self.initial_capital

        dates = [t.get('entry_datetime', '') for t in self.trades if t.get('entry_datetime')]
        if dates:
            eq_x.append(min(dates))
            eq_y.append(cumulative)
            dd_x.append(min(dates))
            dd_y.append(0.0)

        for t in self.trades:
            exit_dt = t.get('exit_datetime', '')
            if not exit_dt:
                continue
            pnl        = t.get('net_pnl', 0.0)
            cumulative += pnl
            peak        = max(peak, cumulative)
            drawdown    = ((cumulative - peak) / peak * 100) if peak > 0 else 0.0

            eq_x.append(exit_dt)
            eq_y.append(round(cumulative, 2))
            dd_x.append(exit_dt)
            dd_y.append(round(drawdown, 2))

        return eq_x, eq_y, dd_x, dd_y

    # ── Monthly returns builder ───────────────────────────────────────
    def _build_monthly_rows(self) -> str:
        monthly: dict = {}
        for t in self.trades:
            exit_dt = t.get('exit_datetime', '')
            if not exit_dt:
                continue
            month_key = pd.Timestamp(exit_dt).strftime('%Y-%m')
            monthly[month_key] = monthly.get(month_key, 0.0) + t.get('net_pnl', 0.0)

        rows = ''
        for month in sorted(monthly.keys()):
            pnl     = monthly[month]
            pnl_inr = pnl * self.usd_to_inr
            pct     = pnl / self.initial_capital * 100
            cls     = 'positive' if pnl >= 0 else 'negative'
            rows += (
                f"<tr><td>{month}</td>"
                f"<td class='{cls}'>${pnl:,.2f}</td>"
                f"<td class='{cls}'>₹{pnl_inr:,.0f}</td>"
                f"<td class='{cls}'>{pct:+.2f}%</td></tr>"
            )
        return rows

    # ── Yearly returns builder ────────────────────────────────────────
    def _build_yearly_rows(self) -> str:
        yearly: dict = {}
        for t in self.trades:
            exit_dt = t.get('exit_datetime', '')
            if not exit_dt:
                continue
            year_key = pd.Timestamp(exit_dt).strftime('%Y')
            yearly[year_key] = yearly.get(year_key, 0.0) + t.get('net_pnl', 0.0)

        rows = ''
        for year in sorted(yearly.keys()):
            pnl     = yearly[year]
            pnl_inr = pnl * self.usd_to_inr
            pct     = pnl / self.initial_capital * 100
            cls     = 'positive' if pnl >= 0 else 'negative'
            rows += (
                f"<tr><td>{year}</td>"
                f"<td class='{cls}'>${pnl:,.2f}</td>"
                f"<td class='{cls}'>₹{pnl_inr:,.0f}</td>"
                f"<td class='{cls}'>{pct:+.2f}%</td></tr>"
            )
        return rows

    # ── Charges breakdown builder ─────────────────────────────────────
    def _build_charges_breakdown(self):
        """
        Independent charge layers:
          Layer 1 - Slippage     : slippage_usd * 2 * total_trades
          Layer 2 - Commission   : taker_fee_rate * 2 * lot_notional_usd * lots * trades
          Layer 3 - Funding      : funding_rate_annual / (8760/interval_h) per interval
          Layer 4 - Tax          : tax_rate * sum of winning trade profits
        All rates from charges_config.
        """
        total_trades = len(self.trades)
        net_pnl      = self.metrics.get('total_pnl', 0.0)
        total_tax    = self.metrics.get('total_tax', 0.0)

        # Layer 1: Slippage
        slip_total = self.slippage_usd * 2 * total_trades

        # Layer 2: Commission (taker fee both sides on lot_notional_usd * lots)
        notional_per_trade = self.lot_notional_usd * self.future_lots
        comm_total = self.taker_fee_rate * 2 * notional_per_trade * total_trades

        # Layer 3: Funding (annualized rate prorated by hold days)
        funding_intervals_per_day = 24 / self.funding_interval_h
        daily_funding_rate        = self.funding_rate_annual / 365
        fund_total = 0.0
        for t in self.trades:
            try:
                hold_days = (
                    pd.Timestamp(t.get('exit_datetime', '')) -
                    pd.Timestamp(t.get('entry_datetime', ''))
                ).days
            except Exception:
                hold_days = 0
            fund_total += notional_per_trade * daily_funding_rate * max(hold_days, 1)

        # Layer 4: Tax (already computed by MetricsCalculator)
        gross_pnl     = net_pnl + total_tax + slip_total + comm_total + fund_total
        total_charges = slip_total + comm_total + fund_total + total_tax

        def _row(label, rate_str, amount):
            cls = 'negative' if amount > 0 else 'positive'
            inr = amount * self.usd_to_inr
            return (
                f"<tr>"
                f"<td>{label}</td>"
                f"<td style='color:#666;font-size:12px'>{rate_str}</td>"
                f"<td class='{cls}'>-${amount:,.2f}</td>"
                f"<td class='{cls}'>-₹{inr:,.0f}</td>"
                f"</tr>"
            )

        rows  = _row('Slippage',
                     f'${self.slippage_usd:.2f}/side × 2 × {total_trades} trades',
                     slip_total)
        rows += _row('Commission (Taker Fee)',
                     f'{self.taker_fee_rate * 100:.3f}% × 2 sides × ${notional_per_trade:,.0f} notional × {total_trades} trades',
                     comm_total)
        rows += _row('Funding Rate',
                     f'{self.funding_rate_annual * 100:.3f}% annual / {self.funding_interval_h}H interval',
                     fund_total)
        rows += _row('Tax',
                     f'{self.tax_rate * 100:.0f}% on winning trade profits',
                     total_tax)

        return rows, gross_pnl, total_charges

    # ── Trade table rows builder ──────────────────────────────────────
    def _build_trade_rows(self) -> str:
        rows = ''
        for t in self.trades:
            pnl       = t.get('net_pnl', 0.0)
            pnl_inr   = pnl * self.usd_to_inr
            pnl_cls   = 'positive' if pnl >= 0 else 'negative'
            direction = t.get('direction', '').upper()
            dir_cls   = 'dir-long' if direction == 'LONG' else 'dir-short'

            try:
                hold_days = (
                    pd.Timestamp(t.get('exit_datetime', '')) -
                    pd.Timestamp(t.get('entry_datetime', ''))
                ).days
            except Exception:
                hold_days = 0

            try:
                entry_p = float(t.get('entry_price', 0))
                exit_p  = float(t.get('exit_price', 0))
                sl_p    = float(t.get('sl_price', 0))
                risk    = abs(entry_p - sl_p)
                reward  = abs(exit_p - entry_p)
                if risk > 0:
                    rr_val = reward / risk
                    if rr_val >= 1.0:
                        rr_str = f'<span class="rr-good">{rr_val:.1f}R</span>'
                    elif rr_val >= 0.5:
                        rr_str = f'<span class="rr-ok">{rr_val:.1f}R</span>'
                    else:
                        rr_str = f'<span class="rr-bad">{rr_val:.1f}R</span>'
                else:
                    rr_str = '<span class="rr-na">-</span>'
            except Exception:
                rr_str = '<span class="rr-na">-</span>'

            etype   = t.get('entry_type', '')
            tag_map = {
                'BUY_A' : 'tag-buy-a',
                'BUY_B' : 'tag-buy-b',
                'SELL_A': 'tag-sell-a',
                'SELL_B': 'tag-sell-b',
            }
            tag_cls  = tag_map.get(etype, '')
            etype_td = f'<span class="{tag_cls}">{etype}</span>' if tag_cls else etype

            cum_pct = t.get('cumulative_pnl_pct', 0.0)
            cum_cls = 'positive' if cum_pct >= 0 else 'negative'

            rows += f"""
<tr>
  <td>{t.get('trade_number', '')}</td>
  <td>{t.get('entry_datetime', '')}</td>
  <td>{t.get('exit_datetime', '')}</td>
  <td class="{dir_cls}">{direction}</td>
  <td>{etype_td}</td>
  <td style="font-size:11px;color:#666">{t.get('exit_type', '')}</td>
  <td>${t.get('entry_price', 0):,.1f}</td>
  <td>${t.get('exit_price', 0):,.1f}</td>
  <td>{t.get('size_qty', self.future_lots)}</td>
  <td class="{pnl_cls}">${t.get('future_net_pnl', t.get('net_pnl', 0)):,.2f}</td>
  <td class="{pnl_cls}">${t.get('options_pnl', 0):,.4f}</td>
  <td class="{pnl_cls}"><b>${pnl:,.2f}</b></td>
  <td class="{pnl_cls}">₹{pnl_inr:,.0f}</td>
  <td>{hold_days}d</td>
  <td>{rr_str}</td>
  <td class="{cum_cls}">{cum_pct:+.2f}%</td>
</tr>"""

        return rows
