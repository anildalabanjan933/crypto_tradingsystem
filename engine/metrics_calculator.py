# engine/metrics_calculator.py
# Responsibility: Calculate all backtest metrics
# Charge Model: AlgoTest post-backtest method
# - Per-trade charges (taker fees, slippage, funding) already in trade records
# - Tax applied HERE post-run: 10% on total winning PnL only

import pandas as pd
import numpy as np
from utils import usd_to_inr


class MetricsCalculator:
    """
    Calculates all backtest metrics from trade list.

    AlgoTest post-backtest charge model:
    ─────────────────────────────────────
    Per-trade charges (already applied in trade_builder.py):
      - Taker fees: 0.10 USD per trade
      - Slippage:   5.00 USD per trade
      - Funding:    0.01 USD per 8H held

    Post-run charges (applied HERE after all trades complete):
      - Insurance:  0.00 USD (not charged on Delta Exchange)
      - Tax:        10% on total winning PnL only (winners only, not losers)

    Tax formula:
      winning_pnl  = sum of net_pnl for all winning trades (net_pnl > 0)
      total_tax    = winning_pnl * tax_rate (0.10)
      final_net_pnl = total_pnl - total_tax
    """

    def __init__(self, trades, initial_capital=100000, charges_config=None):
        """
        Parameters
        ----------
        trades          : list of dict — trade records from TradeBuilder
        initial_capital : float        — initial capital in USD
        charges_config  : dict         — charge rates (tax_rate, usd_to_inr_rate)
        """
        self.trades          = trades
        self.initial_capital = initial_capital
        self.charges_config  = charges_config or {}
        self.usd_to_inr_rate = self.charges_config.get("usd_to_inr_rate", 84)
        self.initial_capital_inr = usd_to_inr(initial_capital, self.usd_to_inr_rate)
        self.metrics = {}

    def calculate_all_metrics(self):
        """
        Calculate all backtest metrics including post-run tax.

        Returns
        -------
        dict — All metrics (USD + INR, pre-tax + post-tax)
        """
        if not self.trades:
            print("No trades to analyze")
            return {}

        df_trades = pd.DataFrame(self.trades)

        # ── Force numeric types on all PnL and charge columns ─────────────────
        numeric_cols = [
            'net_pnl', 'gross_pnl', 'net_pnl_pct', 'net_pnl_inr',
            'taker_fees_usd', 'slippage_usd', 'funding_usd',
            'insurance_usd', 'tax_usd', 'total_charges_usd',
            'favorable_excursion_pct', 'adverse_excursion_pct',
            'cumulative_pnl', 'cumulative_pnl_pct'
        ]
        for col in numeric_cols:
            if col in df_trades.columns:
                df_trades[col] = pd.to_numeric(
                    df_trades[col], errors='coerce'
                ).fillna(0.0)

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 1: BASIC TRADE COUNTS
        # ══════════════════════════════════════════════════════════════════════
        self.metrics['total_trades']   = len(df_trades)
        self.metrics['winning_trades'] = int((df_trades['net_pnl'] > 0).sum())
        self.metrics['losing_trades']  = int((df_trades['net_pnl'] <= 0).sum())
        self.metrics['win_rate']       = (
            self.metrics['winning_trades'] / self.metrics['total_trades'] * 100
            if self.metrics['total_trades'] > 0 else 0.0
        )

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 2: GROSS PnL (before any charges)
        # ══════════════════════════════════════════════════════════════════════
        self.metrics['total_gross_pnl']     = float(df_trades['gross_pnl'].sum())
        self.metrics['total_gross_pnl_inr'] = usd_to_inr(
            self.metrics['total_gross_pnl'], self.usd_to_inr_rate
        )

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 3: PER-TRADE CHARGES BREAKDOWN
        # (taker fees + slippage + funding — already in trade records)
        # ══════════════════════════════════════════════════════════════════════
        self.metrics['total_taker_fees'] = float(df_trades['taker_fees_usd'].sum())
        self.metrics['total_slippage']   = float(df_trades['slippage_usd'].sum())
        self.metrics['total_funding']    = float(df_trades['funding_usd'].sum())
        self.metrics['total_insurance']  = 0.0  # never charged on Delta Exchange

        # Per-trade charges subtotal (excl. tax)
        per_trade_charges_total = (
            self.metrics['total_taker_fees'] +
            self.metrics['total_slippage']   +
            self.metrics['total_funding']    +
            self.metrics['total_insurance']
        )

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 4: NET PnL PRE-TAX
        # (gross_pnl minus per-trade charges, before tax)
        # ══════════════════════════════════════════════════════════════════════
        total_net_pnl_pretax     = float(df_trades['net_pnl'].sum())
        total_net_pnl_pretax_inr = usd_to_inr(total_net_pnl_pretax, self.usd_to_inr_rate)

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 5: POST-RUN TAX (AlgoTest model)
        # Tax = 10% on total winning PnL only
        # Applied AFTER all trades complete — never per trade
        # ══════════════════════════════════════════════════════════════════════
        tax_rate = self.charges_config.get('tax_rate', 0.10)

        # Winning PnL = sum of net_pnl for all trades where net_pnl > 0
        winning_pnl = float(
            df_trades[df_trades['net_pnl'] > 0]['net_pnl'].sum()
        )

        # Tax applies only if there is positive winning PnL
        total_tax = winning_pnl * tax_rate if winning_pnl > 0 else 0.0

        self.metrics['total_tax']     = total_tax
        self.metrics['total_tax_inr'] = usd_to_inr(total_tax, self.usd_to_inr_rate)

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 6: FINAL NET PnL (post-tax)
        # This is the true final result after ALL charges including tax
        # ══════════════════════════════════════════════════════════════════════
        total_pnl_final     = total_net_pnl_pretax - total_tax
        total_pnl_final_inr = usd_to_inr(total_pnl_final, self.usd_to_inr_rate)

        self.metrics['total_pnl']         = total_pnl_final
        self.metrics['total_pnl_inr']     = total_pnl_final_inr
        self.metrics['total_pnl_pct']     = (
            total_pnl_final / self.initial_capital * 100
        ) if self.initial_capital else 0.0

        # Pre-tax net PnL (for reference)
        self.metrics['total_pnl_pretax']     = total_net_pnl_pretax
        self.metrics['total_pnl_pretax_inr'] = total_net_pnl_pretax_inr

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 7: TOTAL CHARGES SUMMARY (all charges combined)
        # ══════════════════════════════════════════════════════════════════════
        total_charges_all = per_trade_charges_total + total_tax
        self.metrics['total_charges']     = total_charges_all
        self.metrics['total_charges_inr'] = usd_to_inr(
            total_charges_all, self.usd_to_inr_rate
        )

        # INR breakdown for report Section 7
        self.metrics['total_taker_fees_inr'] = usd_to_inr(
            self.metrics['total_taker_fees'], self.usd_to_inr_rate
        )
        self.metrics['total_slippage_inr']   = usd_to_inr(
            self.metrics['total_slippage'], self.usd_to_inr_rate
        )
        self.metrics['total_funding_inr']    = usd_to_inr(
            self.metrics['total_funding'], self.usd_to_inr_rate
        )
        self.metrics['total_insurance_inr']  = 0.0

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 8: PROFITABILITY
        # ══════════════════════════════════════════════════════════════════════
        self.metrics['gross_profit'] = float(
            df_trades[df_trades['net_pnl'] > 0]['net_pnl'].sum()
        )
        self.metrics['gross_loss']   = float(
            abs(df_trades[df_trades['net_pnl'] <= 0]['net_pnl'].sum())
        )
        self.metrics['profit_factor'] = (
            self.metrics['gross_profit'] / self.metrics['gross_loss']
            if self.metrics['gross_loss'] > 0 else 0.0
        )

        self.metrics['gross_profit_inr'] = usd_to_inr(
            self.metrics['gross_profit'], self.usd_to_inr_rate
        )
        self.metrics['gross_loss_inr']   = usd_to_inr(
            self.metrics['gross_loss'], self.usd_to_inr_rate
        )

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 9: EXPECTANCY
        # ══════════════════════════════════════════════════════════════════════
        self.metrics['expectancy']     = (
            total_pnl_final / self.metrics['total_trades']
            if self.metrics['total_trades'] > 0 else 0.0
        )
        self.metrics['expectancy_inr'] = usd_to_inr(
            self.metrics['expectancy'], self.usd_to_inr_rate
        )
        self.metrics['expectancy_pct'] = (
            self.metrics['expectancy'] / self.initial_capital * 100
        ) if self.initial_capital else 0.0

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 10: EQUITY CURVE (post-tax adjusted)
        # Equity curve uses pre-tax net_pnl per trade, then deducts total_tax
        # at the end to reflect AlgoTest post-run tax model
        # ══════════════════════════════════════════════════════════════════════
        equity = [self.initial_capital]
        for pnl in df_trades['net_pnl']:
            equity.append(equity[-1] + float(pnl))

        # Apply post-run tax as final deduction on last equity point
        equity[-1] = equity[-1] - total_tax
        self.metrics['equity_curve'] = equity

        # INR equity curve
        equity_inr = [e * self.usd_to_inr_rate for e in equity]
        self.metrics['equity_curve_inr'] = equity_inr

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 11: DRAWDOWN
        # ══════════════════════════════════════════════════════════════════════
        equity_arr  = np.array(equity, dtype=float)
        running_max = np.maximum.accumulate(equity_arr)
        drawdown_pct = np.where(
            running_max > 0,
            (equity_arr - running_max) / running_max * 100,
            0.0
        )
        self.metrics['drawdown_series']  = drawdown_pct.tolist()
        self.metrics['max_drawdown']     = float(np.min(drawdown_pct))
        self.metrics['max_drawdown_pct'] = self.metrics['max_drawdown']
        self.metrics['max_drawdown_inr'] = abs(
            self.metrics['max_drawdown'] / 100 * self.initial_capital_inr
        )

        # ── Return to Max Drawdown ─────────────────────────────────────────────
        self.metrics['return_to_max_dd'] = (
            self.metrics['total_pnl_pct'] / abs(self.metrics['max_drawdown'])
            if self.metrics['max_drawdown'] != 0 else 0.0
        )

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 12: SHARPE RATIO
        # Uses net_pnl_pct (float) per trade — annualised assuming 252 trading days
        # ══════════════════════════════════════════════════════════════════════
        returns     = df_trades['net_pnl_pct'].astype(float).values
        std_returns = float(np.std(returns))
        self.metrics['sharpe_ratio'] = (
            float(np.mean(returns)) / std_returns * np.sqrt(252)
            if std_returns > 0 else 0.0
        )

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 13: AVERAGE TRADE DURATION
        # ══════════════════════════════════════════════════════════════════════
        df_trades['entry_datetime'] = pd.to_datetime(df_trades['entry_datetime'])
        df_trades['exit_datetime']  = pd.to_datetime(df_trades['exit_datetime'])
        df_trades['duration_days']  = (
            (df_trades['exit_datetime'] - df_trades['entry_datetime'])
            .dt.total_seconds() / 86400
        )
        self.metrics['avg_trade_duration_days'] = float(
            df_trades['duration_days'].mean()
        )

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 14: WIN/LOSS STREAKS
        # ══════════════════════════════════════════════════════════════════════
        win_flags = (df_trades['net_pnl'] > 0).astype(int).tolist()

        max_win_streak  = 0
        max_loss_streak = 0
        cur_win         = 0
        cur_loss        = 0

        for flag in win_flags:
            if flag == 1:
                cur_win  += 1
                cur_loss  = 0
                max_win_streak = max(max_win_streak, cur_win)
            else:
                cur_loss += 1
                cur_win   = 0
                max_loss_streak = max(max_loss_streak, cur_loss)

        self.metrics['max_win_streak']  = max_win_streak
        self.metrics['max_loss_streak'] = max_loss_streak

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 15: MONTHLY RETURNS (INR primary)
        # ══════════════════════════════════════════════════════════════════════
        df_trades['month'] = df_trades['exit_datetime'].dt.to_period('M')
        monthly_pnl        = df_trades.groupby('month')['net_pnl_inr'].sum()
        self.metrics['monthly_returns'] = {
            str(k): float(v) for k, v in monthly_pnl.items()
        }

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 16: YEARLY RETURNS (INR primary)
        # ══════════════════════════════════════════════════════════════════════
        df_trades['year'] = df_trades['exit_datetime'].dt.year
        yearly_pnl        = df_trades.groupby('year')['net_pnl_inr'].sum()
        self.metrics['yearly_returns'] = {
            str(k): float(v) for k, v in yearly_pnl.items()
        }

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 17: LARGEST WIN / LARGEST LOSS
        # ══════════════════════════════════════════════════════════════════════
        self.metrics['largest_win']      = float(df_trades['net_pnl'].max())
        self.metrics['largest_loss']     = float(df_trades['net_pnl'].min())
        self.metrics['largest_win_inr']  = usd_to_inr(
            self.metrics['largest_win'], self.usd_to_inr_rate
        )
        self.metrics['largest_loss_inr'] = usd_to_inr(
            self.metrics['largest_loss'], self.usd_to_inr_rate
        )

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 18: AVERAGE WIN / AVERAGE LOSS
        # ══════════════════════════════════════════════════════════════════════
        winning_trades_df = df_trades[df_trades['net_pnl'] > 0]
        losing_trades_df  = df_trades[df_trades['net_pnl'] <= 0]

        self.metrics['avg_win']      = float(
            winning_trades_df['net_pnl'].mean()
        ) if len(winning_trades_df) > 0 else 0.0
        self.metrics['avg_loss']     = float(
            losing_trades_df['net_pnl'].mean()
        ) if len(losing_trades_df) > 0 else 0.0
        self.metrics['avg_win_inr']  = usd_to_inr(
            self.metrics['avg_win'], self.usd_to_inr_rate
        )
        self.metrics['avg_loss_inr'] = usd_to_inr(
            self.metrics['avg_loss'], self.usd_to_inr_rate
        )

        return self.metrics
