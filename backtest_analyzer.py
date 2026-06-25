# backtest_analyzer.py
# Responsibility: Analyze and generate reports for backtest results

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.offline
import os
from datetime import datetime
from utils import format_currency, format_number, round_price, round_percent, usd_to_inr


class BacktestReportGenerator:

    def __init__(self, trades, metrics, strategy_name, symbol,
                 start_date, end_date, slippage=0):
        self.trades              = trades
        self.metrics             = metrics
        self.strategy_name       = strategy_name
        self.symbol              = symbol
        self.start_date          = start_date
        self.end_date            = end_date
        self.slippage            = slippage
        self.initial_capital     = 100000
        self.initial_capital_inr = usd_to_inr(self.initial_capital, 84)

    def generate_html_report(self):
        print("📊 Generating HTML report...")
        os.makedirs("output", exist_ok=True)
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_file  = f"output/backtest_report_{self.strategy_name}_{self.symbol}_{timestamp}.html"
        html_content = self._create_html_template()
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"✅ HTML report saved: {html_file}")
        return html_file

    def generate_csv_trade_log(self):
        print("📝 Generating CSV trade log...")
        os.makedirs("output", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file  = f"output/trade_log_{self.strategy_name}_{self.symbol}_{timestamp}.csv"
        df_trades = pd.DataFrame(self.trades)
        df_trades.to_csv(csv_file, index=False)
        print(f"✅ CSV trade log saved: {csv_file}")
        return csv_file

    def _create_html_template(self):
        if not self.metrics:
            return "<h1>No metrics available to generate report.</h1>"

        # ── Existing metrics ───────────────────────────────────────────────
        total_pnl_inr        = self.metrics.get('total_pnl_inr', 0)
        total_pnl_pct        = self.metrics.get('total_pnl_pct', 0)
        total_trades         = self.metrics.get('total_trades', 0)
        win_rate             = self.metrics.get('win_rate', 0)
        profit_factor        = self.metrics.get('profit_factor', 0)
        expectancy_inr       = self.metrics.get('expectancy_inr', 0)
        sharpe_ratio         = self.metrics.get('sharpe_ratio', 0)
        avg_trade_duration   = self.metrics.get('avg_trade_duration_days', 0)

        total_taker_fees_inr = self.metrics.get('total_taker_fees_inr', 0)
        total_slippage_inr   = self.metrics.get('total_slippage_inr', 0)
        total_funding_inr    = self.metrics.get('total_funding_inr', 0)
        total_insurance_inr  = self.metrics.get('total_insurance_inr', 0)
        total_tax_inr        = self.metrics.get('total_tax_inr', 0)
        total_charges_inr    = self.metrics.get('total_charges_inr', 0)
        total_gross_pnl_inr  = self.metrics.get('total_gross_pnl_inr', 0)

        # ── NEW missing metrics ────────────────────────────────────────────
        loss_rate            = 100 - win_rate
        avg_win_inr          = self.metrics.get('avg_win_inr', 0)
        avg_loss_inr         = self.metrics.get('avg_loss_inr', 0)
        largest_win_inr      = self.metrics.get('largest_win_inr', 0)
        largest_loss_inr     = self.metrics.get('largest_loss_inr', 0)
        max_win_streak       = self.metrics.get('max_win_streak', 0)
        max_loss_streak      = self.metrics.get('max_loss_streak', 0)

        # Reward to Risk Ratio = avg_win / abs(avg_loss)
        avg_loss_abs      = abs(avg_loss_inr) if avg_loss_inr != 0 else 1
        reward_risk_ratio = avg_win_inr / avg_loss_abs if avg_loss_abs > 0 else 0.0

        # Duration of Max Drawdown
        dd_start, dd_end, dd_max_days = self._calc_drawdown_duration()

        # ── Equity curve ───────────────────────────────────────────────────
        equity_data_raw = self.metrics.get('equity_curve', [self.initial_capital])

        # Always trim last point (tax lump-sum) from equity curve display
        equity_data_trimmed = equity_data_raw[:-1] if len(equity_data_raw) > 1 else equity_data_raw[:]
        equity_data_inr     = [usd_to_inr(e - self.initial_capital, 84) for e in equity_data_trimmed]

        if self.trades:
            all_equity_dates = [pd.to_datetime(self.start_date)] + [
                pd.to_datetime(t['exit_datetime']) for t in self.trades
            ]
            # Trim dates to match trimmed equity length
            equity_dates = all_equity_dates[:len(equity_data_trimmed)]
        else:
            equity_dates = [pd.to_datetime(self.start_date)]

        if len(equity_dates) != len(equity_data_inr):
            min_len         = min(len(equity_dates), len(equity_data_inr))
            equity_dates    = equity_dates[:min_len]
            equity_data_inr = equity_data_inr[:min_len]

        equity_chart_fig = go.Figure(data=[
            go.Scatter(
                x=equity_dates, y=equity_data_inr,
                fill='tozeroy', fillcolor='rgba(39, 174, 96, 0.2)',
                line=dict(color='#27ae60', width=2),
                mode='lines', name='Cumulative PnL'
            )
        ])
        equity_chart_fig.update_layout(
            title='Equity Curve (₹)', xaxis_title='Date',
            yaxis_title='Cumulative PnL (₹)', hovermode='x unified', height=400
        )
        equity_chart_html = plotly.offline.plot(
            equity_chart_fig, include_plotlyjs=False, output_type='div'
        )

        # ── Drawdown chart + max DD recompute (tax spike excluded) ─────────
        # Tax is deducted as a lump sum at the very last equity point.
        # We ALWAYS exclude the last point from drawdown calculation so the
        # tax deduction never inflates the max drawdown figure.
        # Re-use equity_data_raw already fetched above (no duplicate fetch)

        # Always trim last point (tax lump-sum) for drawdown purposes
        equity_for_dd          = equity_data_raw[:-1] if len(equity_data_raw) > 1 else equity_data_raw[:]
        drawdown_dates_trimmed = len(equity_data_raw) > 1

        # ── Recompute max_drawdown_inr and max_drawdown_pct from
        #    spike-excluded equity series (fixes wrong -Rs 2,10,130 in cards)
        peak_for_dd     = equity_for_dd[0]
        real_max_dd_usd = 0.0
        for val in equity_for_dd:
            if val > peak_for_dd:
                peak_for_dd = val
            dd_val = val - peak_for_dd          # always <= 0
            if dd_val < real_max_dd_usd:
                real_max_dd_usd = dd_val

        # INR amount (negative) and % (base = Rs 1,00,000 actual capital)
        max_drawdown_inr = usd_to_inr(real_max_dd_usd, 84)   # e.g. -54,757
        max_drawdown_pct = (real_max_dd_usd / 100000) * 100  # e.g. -0.55%

        # Recompute Return/MaxDD (Calmar) using corrected drawdown
        if max_drawdown_inr != 0:
            return_to_max_dd = round(abs(total_pnl_inr / max_drawdown_inr), 2)
        else:
            return_to_max_dd = 0.0

        # Calculate drawdown series in ₹ from running peak
        peak         = equity_for_dd[0]
        drawdown_inr = []
        for val in equity_for_dd:
            if val > peak:
                peak = val
            drawdown_inr.append(usd_to_inr(val - peak, 84))

        if self.trades:
            all_dd_dates = [pd.to_datetime(self.start_date)] + [
                pd.to_datetime(t['exit_datetime']) for t in self.trades
            ]
        else:
            all_dd_dates = [pd.to_datetime(self.start_date)]

        if drawdown_dates_trimmed and len(all_dd_dates) > len(drawdown_inr):
            drawdown_dates = all_dd_dates[:len(drawdown_inr)]
        else:
            drawdown_dates = all_dd_dates

        if len(drawdown_dates) != len(drawdown_inr):
            min_len        = min(len(drawdown_dates), len(drawdown_inr))
            drawdown_dates = drawdown_dates[:min_len]
            drawdown_inr   = drawdown_inr[:min_len]

        drawdown_chart_fig = go.Figure(data=[
            go.Scatter(
                x=drawdown_dates, y=drawdown_inr,
                fill='tozeroy', fillcolor='rgba(231, 76, 60, 0.2)',
                line=dict(color='#e74c3c', width=2),
                mode='lines', name='Drawdown (₹)'
            )
        ])
        drawdown_chart_fig.update_layout(
            title='Drawdown (₹)', xaxis_title='Date',
            yaxis_title='Drawdown (₹)', hovermode='x unified', height=400
        )
        drawdown_chart_html = plotly.offline.plot(
            drawdown_chart_fig, include_plotlyjs=False, output_type='div'
        )

        # ── Monthly returns table ──────────────────────────────────────────
        monthly_returns_html = (
            "<table><thead><tr>"
            "<th>Month</th><th>PnL (₹)</th><th>PnL %</th>"
            "</tr></thead><tbody>"
        )
        monthly_returns = self.metrics.get('monthly_returns', {})
        for month, pnl in sorted(monthly_returns.items()):
            pnl_pct   = (pnl / 100000) * 100
            pnl_class = 'positive' if pnl >= 0 else 'negative'
            monthly_returns_html += (
                f"<tr><td>{month}</td>"
                f"<td class='{pnl_class}'>{format_currency(pnl)}</td>"
                f"<td class='{pnl_class}'>{round_percent(pnl_pct)}%</td></tr>"
            )
        monthly_returns_html += "</tbody></table>"

        # ── Yearly returns table ───────────────────────────────────────────
        yearly_returns_html = (
            "<table><thead><tr>"
            "<th>Year</th><th>PnL (₹)</th><th>PnL %</th>"
            "</tr></thead><tbody>"
        )
        yearly_returns = self.metrics.get('yearly_returns', {})
        for year, pnl in sorted(yearly_returns.items()):
            pnl_pct   = (pnl / 100000) * 100
            pnl_class = 'positive' if pnl >= 0 else 'negative'
            yearly_returns_html += (
                f"<tr><td>{year}</td>"
                f"<td class='{pnl_class}'>{format_currency(pnl)}</td>"
                f"<td class='{pnl_class}'>{round_percent(pnl_pct)}%</td></tr>"
            )
        yearly_returns_html += "</tbody></table>"

        # ── CSS classes (set AFTER max_drawdown_pct is recomputed) ─────────
        pnl_class        = 'positive' if total_pnl_inr >= 0 else 'negative'
        pnl_pct_class    = 'positive' if total_pnl_pct >= 0 else 'negative'
        dd_class         = 'negative' if max_drawdown_pct < 0 else ''
        gross_pnl_class  = 'positive' if total_gross_pnl_inr >= 0 else 'negative'
        winning_class    = 'positive'
        losing_class     = 'negative'
        expectancy_class = 'positive' if expectancy_inr >= 0 else 'negative'
        avg_win_class    = 'positive' if avg_win_inr >= 0 else 'negative'
        avg_loss_class   = 'negative'
        rr_class         = 'positive' if reward_risk_ratio >= 1 else 'negative'
        rtdd_class       = 'positive' if return_to_max_dd >= 0 else 'negative'

        # ── Slippage label ─────────────────────────────────────────────────
        if self.slippage > 0:
            slippage_label = f"Slippage (${self.slippage}/side × 2 × {total_trades} trades)"
        else:
            slippage_label = "Slippage (none)"

        # ══════════════════════════════════════════════════════════════════
        # HTML TEMPLATE
        # ══════════════════════════════════════════════════════════════════
        html = (
            '<!DOCTYPE html>\n'
            '<html lang="en">\n'
            '<head>\n'
            '    <meta charset="UTF-8">\n'
            '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f'    <title>Backtest Report - {self.strategy_name}</title>\n'
            '    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>\n'
            '    <style>\n'
            '        * { margin: 0; padding: 0; box-sizing: border-box; }\n'
            '        body { font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif; background-color: #f5f5f5; color: #333; line-height: 1.6; }\n'
            '        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }\n'
            '        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px; margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }\n'
            '        .header h1 { font-size: 28px; margin-bottom: 10px; }\n'
            '        .header-info { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-top: 20px; }\n'
            '        .header-item { background: rgba(255,255,255,0.1); padding: 15px; border-radius: 5px; }\n'
            '        .header-item label { font-size: 12px; opacity: 0.9; display: block; margin-bottom: 5px; }\n'
            '        .header-item value { font-size: 18px; font-weight: bold; }\n'
            '        .section { background: white; padding: 25px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }\n'
            '        .section h2 { font-size: 20px; margin-bottom: 20px; color: #667eea; border-bottom: 2px solid #667eea; padding-bottom: 10px; }\n'
            '        .chart-container { width: 100%; height: 400px; margin-bottom: 20px; }\n'
            '        table { width: 100%; border-collapse: collapse; margin-top: 15px; }\n'
            '        th { background-color: #667eea; color: white; padding: 12px; text-align: left; font-weight: 600; }\n'
            '        td { padding: 12px; border-bottom: 1px solid #ddd; }\n'
            '        tr:hover { background-color: #f9f9f9; }\n'
            '        .positive { color: #27ae60; font-weight: bold; }\n'
            '        .negative { color: #e74c3c; font-weight: bold; }\n'
            '        .neutral  { color: #8e44ad; font-weight: bold; }\n'
            '        .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px; }\n'
            '        .metric-card { background: #f9f9f9; padding: 15px; border-radius: 5px; border-left: 4px solid #667eea; }\n'
            '        .metric-card label { font-size: 12px; color: #666; display: block; margin-bottom: 5px; }\n'
            '        .metric-card value { font-size: 18px; font-weight: bold; display: block; }\n'
            '        .footer { text-align: center; padding: 20px; color: #999; font-size: 12px; }\n'
            '    </style>\n'
            '</head>\n'
            '<body>\n'
            '    <div class="container">\n'

            # ── SECTION 1: HEADER ──────────────────────────────────────────
            '        <div class="header">\n'
            f'            <h1>{self.strategy_name}</h1>\n'
            f'            <p>{self.symbol} | {self.start_date} to {self.end_date} | '
            f'Slippage: {"$" + str(self.slippage) + "/side" if self.slippage > 0 else "None"}</p>\n'
            '            <div class="header-info">\n'
            '                <div class="header-item">\n'
            '                    <label>Total PnL</label>\n'
            f'                    <value class="{pnl_class}">{format_currency(total_pnl_inr)}</value>\n'
            '                </div>\n'
            '                <div class="header-item">\n'
            '                    <label>Total Trades</label>\n'
            f'                    <value>{total_trades}</value>\n'
            '                </div>\n'
            '                <div class="header-item">\n'
            '                    <label>Win Rate</label>\n'
            f'                    <value>{round_percent(win_rate)}%</value>\n'
            '                </div>\n'
            '                <div class="header-item">\n'
            '                    <label>Max Drawdown (₹)</label>\n'
            f'                    <value class="negative">-{format_currency(abs(max_drawdown_inr))}</value>\n'
            '                </div>\n'
            '                <div class="header-item">\n'
            '                    <label>Profit Factor</label>\n'
            f'                    <value>{format_number(profit_factor)}</value>\n'
            '                </div>\n'
            '                <div class="header-item">\n'
            '                    <label>Sharpe Ratio</label>\n'
            f'                    <value>{format_number(sharpe_ratio)}</value>\n'
            '                </div>\n'
            '            </div>\n'
            '        </div>\n'
            '\n'

            # ── SECTION 2: EQUITY CURVE ────────────────────────────────────
            '        <div class="section">\n'
            '            <h2>📈 Equity Curve</h2>\n'
            f'            {equity_chart_html}\n'
            '        </div>\n'
            '\n'

            # ── SECTION 3: DRAWDOWN ────────────────────────────────────────
            '        <div class="section">\n'
            '            <h2>📉 Drawdown</h2>\n'
            f'            {drawdown_chart_html}\n'
            '        </div>\n'
            '\n'

            # ── SECTION 4: MONTHLY RETURNS ─────────────────────────────────
            '        <div class="section">\n'
            '            <h2>📅 Monthly Returns (₹)</h2>\n'
            f'            {monthly_returns_html}\n'
            '        </div>\n'
            '\n'

            # ── SECTION 5: YEARLY RETURNS ──────────────────────────────────
            '        <div class="section">\n'
            '            <h2>📅 Yearly Returns (₹)</h2>\n'
            f'            {yearly_returns_html}\n'
            '        </div>\n'
            '\n'

            # ── SECTION 6: STRATEGY STATISTICS ────────────────────────────
            '        <div class="section">\n'
            '            <h2>📊 Strategy Statistics</h2>\n'
            '            <div class="metric-grid">\n'

            '                <div class="metric-card">\n'
            '                    <label>Total Trades</label>\n'
            f'                    <value>{total_trades}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Winning Trades</label>\n'
            f'                    <value class="{winning_class}">{self.metrics.get("winning_trades", 0)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Losing Trades</label>\n'
            f'                    <value class="{losing_class}">{self.metrics.get("losing_trades", 0)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Win Rate</label>\n'
            f'                    <value>{round_percent(win_rate)}%</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Loss Rate</label>\n'
            f'                    <value class="negative">{round_percent(loss_rate)}%</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Profit Factor</label>\n'
            f'                    <value>{format_number(profit_factor)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Total PnL (₹)</label>\n'
            f'                    <value class="{pnl_class}">{format_currency(total_pnl_inr)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Expectancy (₹)</label>\n'
            f'                    <value class="{expectancy_class}">{format_currency(expectancy_inr)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Avg Profit on Winning Trades (₹)</label>\n'
            f'                    <value class="{avg_win_class}">{format_currency(avg_win_inr)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Avg Loss on Losing Trades (₹)</label>\n'
            f'                    <value class="{avg_loss_class}">{format_currency(avg_loss_inr)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Max Profit in Single Trade (₹)</label>\n'
            f'                    <value class="positive">{format_currency(largest_win_inr)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Max Loss in Single Trade (₹)</label>\n'
            f'                    <value class="negative">{format_currency(largest_loss_inr)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Max Drawdown</label>\n'
            f'                    <value class="{dd_class}">{round_percent(max_drawdown_pct)}% '
            f'(-{format_currency(abs(max_drawdown_inr))})</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Duration of Max Drawdown</label>\n'
            f'                    <value class="negative">{dd_max_days} days ({dd_start} to {dd_end})</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Return / Max Drawdown</label>\n'
            f'                    <value class="{rtdd_class}">{format_number(return_to_max_dd)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Reward to Risk Ratio</label>\n'
            f'                    <value class="{rr_class}">{format_number(reward_risk_ratio)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Sharpe Ratio</label>\n'
            f'                    <value>{format_number(sharpe_ratio)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Max Win Streak</label>\n'
            f'                    <value class="positive">{max_win_streak}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Max Loss Streak</label>\n'
            f'                    <value class="negative">{max_loss_streak}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Max Days in Drawdown</label>\n'
            f'                    <value class="negative">{dd_max_days} days</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Avg Trade Duration</label>\n'
            f'                    <value>{format_number(avg_trade_duration)} days</value>\n'
            '                </div>\n'

            '            </div>\n'
            '        </div>\n'
            '\n'

            # ── SECTION 7: CHARGES BREAKDOWN ──────────────────────────────
            '        <div class="section">\n'
            '            <h2>💰 Charges Breakdown (₹)</h2>\n'
            '            <table>\n'
            '                <thead>\n'
            '                    <tr><th>Charge Type</th><th>Amount (₹)</th></tr>\n'
            '                </thead>\n'
            '                <tbody>\n'
            '                    <tr>\n'
            '                        <td>Taker Fees (0.05%)</td>\n'
            f'                        <td class="negative">{format_currency(total_taker_fees_inr)}</td>\n'
            '                    </tr>\n'
            '                    <tr>\n'
            f'                        <td>{slippage_label}</td>\n'
            f'                        <td class="negative">{format_currency(total_slippage_inr)}</td>\n'
            '                    </tr>\n'
            '                    <tr>\n'
            '                        <td>Funding Rate (10.95%)</td>\n'
            f'                        <td class="negative">{format_currency(total_funding_inr)}</td>\n'
            '                    </tr>\n'
            '                    <tr>\n'
            '                        <td>Insurance Fund</td>\n'
            f'                        <td class="negative">{format_currency(total_insurance_inr)}</td>\n'
            '                    </tr>\n'
            '                    <tr>\n'
            '                        <td>Tax (10% on winning trades)</td>\n'
            f'                        <td class="negative">{format_currency(total_tax_inr)}</td>\n'
            '                    </tr>\n'
            '                    <tr style="background-color: #f0f0f0; font-weight: bold;">\n'
            '                        <td>Total Charges</td>\n'
            f'                        <td class="negative">{format_currency(total_charges_inr)}</td>\n'
            '                    </tr>\n'
            '                    <tr style="background-color: #f0f0f0; font-weight: bold;">\n'
            '                        <td>Gross PnL</td>\n'
            f'                        <td class="{gross_pnl_class}">{format_currency(total_gross_pnl_inr)}</td>\n'
            '                    </tr>\n'
            '                    <tr style="background-color: #e8f5e9; font-weight: bold;">\n'
            '                        <td>Net PnL (After Charges)</td>\n'
            f'                        <td class="{pnl_class}">{format_currency(total_pnl_inr)}</td>\n'
            '                    </tr>\n'
            '                </tbody>\n'
            '            </table>\n'
            '        </div>\n'
            '\n'

            # ── FOOTER ─────────────────────────────────────────────────────
            '        <div class="footer">\n'
            f'            <p>Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | '
            f'Strategy: {self.strategy_name} | Symbol: {self.symbol} | '
            f'Slippage: {"$" + str(self.slippage) + "/side" if self.slippage > 0 else "None"}</p>\n'
            '        </div>\n'
            '    </div>\n'
            '</body>\n'
            '</html>\n'
        )

        return html

    def _calc_drawdown_duration(self):
        """
        Calculate duration of max drawdown period.
        Uses equity curve directly (always excludes final tax lump-sum point).
        Returns: (start_date_str, end_date_str, max_days)
        """
        if not self.trades:
            return "N/A", "N/A", 0

        try:
            equity_data_raw = self.metrics.get('equity_curve', [])
            if not equity_data_raw or len(equity_data_raw) < 2:
                return "N/A", "N/A", 0

            # Always trim last point (tax lump-sum deduction)
            equity_for_dd = equity_data_raw[:-1]
            trimmed       = True

            dates = [pd.to_datetime(self.start_date)] + [
                pd.to_datetime(t['exit_datetime']) for t in self.trades
            ]
            if trimmed:
                dates = dates[:len(equity_for_dd)]

            if len(dates) != len(equity_for_dd):
                min_len       = min(len(dates), len(equity_for_dd))
                dates         = dates[:min_len]
                equity_for_dd = equity_for_dd[:min_len]

            # Find drawdown periods from equity curve
            peak  = equity_for_dd[0]
            in_dd = []
            for val in equity_for_dd:
                if val > peak:
                    peak = val
                in_dd.append(val < peak)

            max_days  = 0
            dd_start  = "N/A"
            dd_end    = "N/A"
            cur_start = None

            for i, flag in enumerate(in_dd):
                if flag:
                    if cur_start is None:
                        cur_start = dates[i]
                    cur_days = (dates[i] - cur_start).days
                    if cur_days > max_days:
                        max_days = cur_days
                        dd_start = cur_start.strftime("%Y-%m-%d")
                        dd_end   = dates[i].strftime("%Y-%m-%d")
                else:
                    cur_start = None

            return dd_start, dd_end, max_days

        except Exception:
            return "N/A", "N/A", 0
