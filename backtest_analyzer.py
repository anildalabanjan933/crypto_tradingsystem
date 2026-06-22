# backtest_analyzer.py
# Responsibility: Analyze and generate reports for backtest results

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.offline
import os
from datetime import datetime
from utils import format_currency, format_number, round_price, round_percent, usd_to_inr


class BacktestReportGenerator:
    """
    Generates an HTML report and CSV trade log for backtest results.
    """

    def __init__(self, trades, metrics, strategy_name, symbol, start_date, end_date):
        self.trades = trades
        self.metrics = metrics
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = 100000
        self.initial_capital_inr = usd_to_inr(self.initial_capital, 84)

    def generate_html_report(self):
        """
        Generates an HTML report summarizing backtest results.
        """
        print("📊 Generating HTML report...")

        os.makedirs("output", exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_file = f"output/backtest_report_{self.strategy_name}_{self.symbol}_{timestamp}.html"

        html_content = self._create_html_template()

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"✅ HTML report saved: {html_file}")
        return html_file

    def generate_csv_trade_log(self):
        """
        Generates a CSV trade log.
        """
        print("📝 Generating CSV trade log...")

        os.makedirs("output", exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = f"output/trade_log_{self.strategy_name}_{self.symbol}_{timestamp}.csv"

        df_trades = pd.DataFrame(self.trades)
        df_trades.to_csv(csv_file, index=False)

        print(f"✅ CSV trade log saved: {csv_file}")
        return csv_file

    def _create_html_template(self):
        """
        Creates the full HTML content for the backtest report.
        """
        if not self.metrics:
            return "<h1>No metrics available to generate report.</h1>"

        # Extract metrics
        total_pnl_inr = self.metrics.get('total_pnl_inr', 0)
        total_pnl_pct = self.metrics.get('total_pnl_pct', 0)
        total_trades = self.metrics.get('total_trades', 0)
        win_rate = self.metrics.get('win_rate', 0)
        max_drawdown_pct = self.metrics.get('max_drawdown_pct', 0)
        profit_factor = self.metrics.get('profit_factor', 0)
        expectancy_inr = self.metrics.get('expectancy_inr', 0)
        sharpe_ratio = self.metrics.get('sharpe_ratio', 0)
        avg_trade_duration = self.metrics.get('avg_trade_duration', 0)

        # Charges breakdown
        total_taker_fees_inr = self.metrics.get('total_taker_fees_inr', 0)
        total_slippage_inr = self.metrics.get('total_slippage_inr', 0)
        total_funding_inr = self.metrics.get('total_funding_inr', 0)
        total_insurance_inr = self.metrics.get('total_insurance_inr', 0)
        total_tax_inr = self.metrics.get('total_tax_inr', 0)
        total_charges_inr = self.metrics.get('total_charges_inr', 0)
        total_gross_pnl_inr = self.metrics.get('total_gross_pnl_inr', 0)

        # Pre-compute CSS classes to avoid nested quotes inside f-string
        pnl_class = 'positive' if total_pnl_inr >= 0 else 'negative'
        pnl_pct_class = 'positive' if total_pnl_pct >= 0 else 'negative'
        dd_class = 'negative' if max_drawdown_pct < 0 else ''
        gross_pnl_class = 'positive' if total_gross_pnl_inr >= 0 else 'negative'
        winning_class = 'positive' if self.metrics.get('winning_trades', 0) >= 0 else ''
        losing_class = 'negative' if self.metrics.get('losing_trades', 0) > 0 else ''
        expectancy_class = 'positive' if expectancy_inr >= 0 else 'negative'

        # Equity Curve Plot
        equity_data = self.metrics.get('equity_curve', [self.initial_capital])
        equity_data_inr = [usd_to_inr(e, 84) for e in equity_data]

        if self.trades:
            equity_dates = [pd.to_datetime(self.start_date)] + [pd.to_datetime(t['exit_datetime']) for t in self.trades]
        else:
            equity_dates = [pd.to_datetime(self.start_date)]

        if len(equity_dates) != len(equity_data_inr):
            if len(equity_data_inr) == 1 and len(equity_dates) == 1:
                pass
            elif len(equity_data_inr) > 1 and len(equity_dates) == 1:
                equity_dates = [pd.to_datetime(self.start_date)] * len(equity_data_inr)
            elif len(equity_data_inr) == 1 and len(equity_dates) > 1:
                equity_data_inr = equity_data_inr * len(equity_dates)

        equity_chart_fig = go.Figure(data=[
            go.Scatter(
                x=equity_dates,
                y=equity_data_inr,
                fill='tozeroy',
                fillcolor='rgba(39, 174, 96, 0.2)',
                line=dict(color='#27ae60', width=2),
                mode='lines',
                name='Cumulative PnL'
            )
        ])
        equity_chart_fig.update_layout(
            title='Equity Curve (₹)',
            xaxis_title='Date',
            yaxis_title='Cumulative PnL (₹)',
            hovermode='x unified',
            height=400
        )
        equity_chart_html = plotly.offline.plot(
            equity_chart_fig,
            include_plotlyjs=False,
            output_type='div'
        )

        # Drawdown Plot
        drawdown_data = self.metrics.get('drawdown_curve', [0])

        if self.trades:
            drawdown_dates = [pd.to_datetime(self.start_date)] + [pd.to_datetime(t['exit_datetime']) for t in self.trades]
        else:
            drawdown_dates = [pd.to_datetime(self.start_date)]

        if len(drawdown_dates) != len(drawdown_data):
            if len(drawdown_data) == 1 and len(drawdown_dates) == 1:
                pass
            elif len(drawdown_data) > 1 and len(drawdown_dates) == 1:
                drawdown_dates = [pd.to_datetime(self.start_date)] * len(drawdown_data)
            elif len(drawdown_data) == 1 and len(drawdown_dates) > 1:
                drawdown_data = drawdown_data * len(drawdown_dates)

        drawdown_chart_fig = go.Figure(data=[
            go.Scatter(
                x=drawdown_dates,
                y=drawdown_data,
                fill='tozeroy',
                fillcolor='rgba(231, 76, 60, 0.2)',
                line=dict(color='#e74c3c', width=2),
                mode='lines',
                name='Drawdown %'
            )
        ])
        drawdown_chart_fig.update_layout(
            title='Drawdown (%)',
            xaxis_title='Date',
            yaxis_title='Drawdown (%)',
            hovermode='x unified',
            height=400
        )
        drawdown_chart_html = plotly.offline.plot(
            drawdown_chart_fig,
            include_plotlyjs=False,
            output_type='div'
        )

        # Monthly Returns Table
        monthly_returns_html = "<table><thead><tr><th>Month</th><th>PnL (₹)</th><th>PnL %</th></tr></thead><tbody>"
        monthly_returns = self.metrics.get('monthly_returns', {})
        sorted_monthly_returns = sorted(monthly_returns.items())
        for month, pnl in sorted_monthly_returns:
            pnl_pct = (pnl / self.initial_capital_inr) * 100 if self.initial_capital_inr else 0
            pnl_class = 'positive' if pnl >= 0 else 'negative'
            monthly_returns_html += f"<tr><td>{month}</td><td class='{pnl_class}'>{format_currency(pnl)}</td><td class='{pnl_class}'>{round_percent(pnl_pct)}%</td></tr>"
        monthly_returns_html += "</tbody></table>"

        # Yearly Returns Table
        yearly_returns_html = "<table><thead><tr><th>Year</th><th>PnL (₹)</th><th>PnL %</th></tr></thead><tbody>"
        yearly_returns = self.metrics.get('yearly_returns', {})
        sorted_yearly_returns = sorted(yearly_returns.items())
        for year, pnl in sorted_yearly_returns:
            pnl_pct = (pnl / self.initial_capital_inr) * 100 if self.initial_capital_inr else 0
            pnl_class = 'positive' if pnl >= 0 else 'negative'
            yearly_returns_html += f"<tr><td>{year}</td><td class='{pnl_class}'>{format_currency(pnl)}</td><td class='{pnl_class}'>{round_percent(pnl_pct)}%</td></tr>"
        yearly_returns_html += "</tbody></table>"

        # Build HTML using string concatenation to avoid f-string nested quote issues
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
            '        .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px; }\n'
            '        .metric-card { background: #f9f9f9; padding: 15px; border-radius: 5px; border-left: 4px solid #667eea; }\n'
            '        .metric-card label { font-size: 12px; color: #666; display: block; margin-bottom: 5px; }\n'
            '        .metric-card value { font-size: 18px; font-weight: bold; display: block; }\n'
            '        .footer { text-align: center; padding: 20px; color: #999; font-size: 12px; }\n'
            '    </style>\n'
            '</head>\n'
            '<body>\n'
            '    <div class="container">\n'
            '        <div class="header">\n'
            f'            <h1>{self.strategy_name}</h1>\n'
            f'            <p>{self.symbol} | {self.start_date} to {self.end_date}</p>\n'
            '            <div class="header-info">\n'
            '                <div class="header-item">\n'
            '                    <label>Initial Capital</label>\n'
            f'                    <value>{format_currency(usd_to_inr(self.initial_capital, 84))}</value>\n'
            '                </div>\n'
            '                <div class="header-item">\n'
            '                    <label>Total PnL</label>\n'
            f'                    <value class="{pnl_class}">{format_currency(total_pnl_inr)}</value>\n'
            '                </div>\n'
            '                <div class="header-item">\n'
            '                    <label>Return %</label>\n'
            f'                    <value class="{pnl_pct_class}">{round_percent(total_pnl_pct)}%</value>\n'
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
            '                    <label>Max Drawdown</label>\n'
            f'                    <value class="{dd_class}">{round_percent(max_drawdown_pct)}%</value>\n'
            '                </div>\n'
            '            </div>\n'
            '        </div>\n'
            '\n'
            '        <div class="section">\n'
            '            <h2>📈 Equity Curve</h2>\n'
            f'            {equity_chart_html}\n'
            '        </div>\n'
            '\n'
            '        <div class="section">\n'
            '            <h2>📉 Drawdown</h2>\n'
            f'            {drawdown_chart_html}\n'
            '        </div>\n'
            '\n'
            '        <div class="section">\n'
            '            <h2>📅 Monthly Returns (₹)</h2>\n'
            f'            {monthly_returns_html}\n'
            '        </div>\n'
            '\n'
            '        <div class="section">\n'
            '            <h2>📅 Yearly Returns (₹)</h2>\n'
            f'            {yearly_returns_html}\n'
            '        </div>\n'
            '\n'
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
            '                    <label>Max Drawdown</label>\n'
            f'                    <value class="{dd_class}">{round_percent(max_drawdown_pct)}%</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Sharpe Ratio</label>\n'
            f'                    <value>{format_number(sharpe_ratio)}</value>\n'
            '                </div>\n'
            '                <div class="metric-card">\n'
            '                    <label>Avg Trade Duration</label>\n'
            f'                    <value>{format_number(avg_trade_duration)} days</value>\n'
            '                </div>\n'
            '            </div>\n'
            '        </div>\n'
            '\n'
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
            '                        <td>Slippage (5%)</td>\n'
            f'                        <td class="negative">{format_currency(total_slippage_inr)}</td>\n'
            '                    </tr>\n'
            '                    <tr>\n'
            '                        <td>Funding Rate (10.95%)</td>\n'
            f'                        <td class="negative">{format_currency(total_funding_inr)}</td>\n'
            '                    </tr>\n'
            '                    <tr>\n'
            '                        <td>Insurance Fund (5%)</td>\n'
            f'                        <td class="negative">{format_currency(total_insurance_inr)}</td>\n'
            '                    </tr>\n'
            '                    <tr>\n'
            '                        <td>Tax (8.85%)</td>\n'
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
            '        <div class="footer">\n'
            f'            <p>Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>\n'
            '        </div>\n'
            '    </div>\n'
            '</body>\n'
            '</html>\n'
        )

        return html
