# engine/optimization_analyzer.py
# Responsibility: Analyze and report optimization results

import pandas as pd
import os
from datetime import datetime
from utils import format_currency, format_number, round_percent, format_percent
from config.backtest_config import backtest_config


class OptimizationAnalyzer:
    """
    Analyzes and generates reports for optimization results.
    """

    def __init__(self, optimization_results, strategy_name, symbol,
                 start_date, end_date, lot_size=100, slippage=0):
        self.optimization_results = optimization_results
        self.strategy_name        = strategy_name
        self.symbol               = symbol
        self.start_date           = start_date
        self.end_date             = end_date
        self.lot_size             = lot_size
        self.slippage             = slippage
        self.usd_to_inr_rate      = backtest_config.get('usd_to_inr_rate', 84)
        self.initial_capital_usd  = backtest_config.get('initial_capital_usd', 100000)
        # INR capital for Return % header card (portfolio margin mode)
        self.initial_capital_inr  = self.initial_capital_usd * self.usd_to_inr_rate  # 8,400,000

    # ------------------------------------------------------------------
    # PUBLIC
    # ------------------------------------------------------------------

    def generate_html_report(self):
        print("Generating Optimization HTML report...")
        os.makedirs("output", exist_ok=True)
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_file  = (f"output/optimization_results_{self.strategy_name}"
                      f"_{self.symbol}_{timestamp}.html")
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(self._create_html_template())
        print(f"Optimization report saved: {html_file}")
        return html_file

    # ------------------------------------------------------------------
    # MONTHLY / YEARLY TABLES
    # FIX: pnl / initial_capital_usd * 100  (USD denominator = 100,000)
    # matches backtest HTML AlgoTest portfolio margin format exactly
    # ------------------------------------------------------------------

    def _build_monthly_returns_html(self, metrics):
        monthly_returns = metrics.get('monthly_returns', {})
        if not monthly_returns:
            return "<p>No monthly data available.</p>"

        html = (
            "<table><thead><tr>"
            "<th>Month</th><th>PnL (₹)</th><th>PnL %</th><th>Return % on Capital (3x DD)</th>"
            "</tr></thead><tbody>"
        )
        for month, pnl in sorted(monthly_returns.items()):
            # FIX: USD denominator matches backtest HTML
            pnl_pct   = (pnl / self.initial_capital_inr) * 100
            pnl_class = 'positive' if pnl >= 0 else 'negative'
            html += (
                f"<tr><td>{month}</td>"
                f"<td class='{pnl_class}'>{format_currency(pnl)}</td>"
                f"<td class='{pnl_class}'>{format_percent(pnl_pct)}</td>"
                f"<td class='{pnl_class}'>{format_percent((pnl / (3 * abs(metrics.get('max_drawdown_inr', 1)))) * 100)}</td></tr>"
            )
        html += "</tbody></table>"
        return html
    def _build_yearly_returns_html(self, metrics):
        yearly_returns = metrics.get('yearly_returns', {})
        if not yearly_returns:
            return "<p>No yearly data available.</p>"

        html = (
            "<table><thead><tr>"
            "<th>Year</th><th>PnL (₹)</th><th>PnL %</th><th>Return % on Capital (3x DD)</th>"
            "</tr></thead><tbody>"
        )
        for year, pnl in sorted(yearly_returns.items()):
            # FIX: USD denominator matches backtest HTML
            pnl_pct   = (pnl / self.initial_capital_inr) * 100
            pnl_class = 'positive' if pnl >= 0 else 'negative'
            html += (
                f"<tr><td>{year}</td>"
                f"<td class='{pnl_class}'>{format_currency(pnl)}</td>"
                f"<td class='{pnl_class}'>{format_percent(pnl_pct)}</td>"
                f"<td class='{pnl_class}'>{format_percent((pnl / (3 * abs(metrics.get('max_drawdown_inr', 1)))) * 100)}</td></tr>"
            )
        html += "</tbody></table>"
        return html
    # ------------------------------------------------------------------
    # HTML TEMPLATE
    # ------------------------------------------------------------------

    def _create_html_template(self):
        best_result       = self._get_best_result()
        best_params_html  = (self._format_params_for_html(best_result['parameters'])
                             if best_result else "N/A")
        best_metrics_html = (self._format_metrics_for_html(best_result['metrics'])
                             if best_result else "N/A")
        all_results_table = self._create_all_results_table()

        monthly_html = (self._build_monthly_returns_html(best_result['metrics'])
                        if best_result else "<p>No data.</p>")
        yearly_html  = (self._build_yearly_returns_html(best_result['metrics'])
                        if best_result else "<p>No data.</p>")

        best_params_label = ""
        if best_result:
            best_params_label = " — Best Combo: " + ", ".join(
                f"{k}={v}" for k, v in best_result['parameters'].items()
            )

        # FIX: Return % header card = net_pnl_inr / initial_capital_usd * 100
        # (AlgoTest USD denominator 100,000 — matches backtest monthly/yearly % format)
        best_return_pct = (
            (best_result['metrics']['total_pnl_inr'] / self.initial_capital_inr) * 100
            if best_result else 0
        )

        best_return_class = "positive" if best_return_pct >= 0 else "negative"

        # FIX: Max Drawdown header card — show "-X.XX% (-₹Y,YYY)" format
        # matching backtest HTML "Max Drawdown" card exactly
        best_max_dd_pct = (
            best_result['metrics'].get('max_drawdown_pct', 0)
            if best_result else 0
        )
        best_max_dd_inr = (
            best_result['metrics'].get('max_drawdown_inr', 0)
            if best_result else 0
        )
        best_max_dd_display = (
            f"{format_percent(best_max_dd_pct)} (-{format_currency(abs(best_max_dd_inr))})"
            if best_result else "N/A"
        )
        best_max_dd_class = "negative" if best_max_dd_pct < 0 else ""

        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Optimization Report - {self.strategy_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f5f5f5; color: #333; line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; padding: 30px; border-radius: 8px;
            margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header-info {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px; margin-top: 20px;
        }}
        .header-item {{
            background: rgba(255,255,255,0.1); padding: 15px; border-radius: 5px;
        }}
        .header-item label {{
            font-size: 12px; opacity: 0.9; display: block; margin-bottom: 5px;
        }}
        .header-item value {{ font-size: 18px; font-weight: bold; }}
        .section {{
            background: white; padding: 25px; margin-bottom: 20px;
            border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            font-size: 20px; margin-bottom: 20px; color: #667eea;
            border-bottom: 2px solid #667eea; padding-bottom: 10px;
        }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th {{
            background-color: #667eea; color: white;
            padding: 12px; text-align: left; font-weight: 600;
        }}
        td {{ padding: 12px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background-color: #f9f9f9; }}
        .positive {{ color: #27ae60; font-weight: bold; }}
        .negative {{ color: #e74c3c; font-weight: bold; }}
        .metric-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px; margin-top: 15px;
        }}
        .metric-card {{
            background: #f9f9f9; padding: 15px; border-radius: 5px;
            border-left: 4px solid #667eea;
        }}
        .metric-card label {{
            font-size: 12px; color: #666; display: block; margin-bottom: 5px;
        }}
        .metric-card value {{ font-size: 18px; font-weight: bold; display: block; }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
        .info-bar {{
            background: rgba(255,255,255,0.15); padding: 10px 15px;
            border-radius: 5px; margin-top: 15px; font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Optimization Report: {self.strategy_name}</h1>
            <p>{self.symbol} | {self.start_date} to {self.end_date}</p>

            <div class="info-bar">
                Lot Size: <strong>{self.lot_size} lots</strong> &nbsp;|&nbsp;
                Slippage: <strong>${self.slippage}/side</strong> &nbsp;|&nbsp;
                Capital: <strong>₹{self.initial_capital_inr:,.0f} INR</strong> &nbsp;|&nbsp;
                Charges: <strong>Included (same as backtest)</strong>
            </div>

            <div class="header-info">
                <div class="header-item">
                    <label>Total Combinations</label>
                    <value>{len(self.optimization_results)}</value>
                </div>
                <div class="header-item">
                    <label>Best PnL (₹)</label>
                    <value class="{'positive' if best_result and best_result['metrics']['total_pnl_inr'] >= 0 else 'negative'}">
                        {format_currency(best_result['metrics']['total_pnl_inr']) if best_result else 'N/A'}
                    </value>
                </div>
                <div class="header-item">
                    <label>Best Return %</label>
                    <!-- FIX: net_pnl_inr / initial_capital_inr * 100 (portfolio margin, matches backtest top card) -->
                    <value class="{best_return_class}">
                        {format_percent(best_return_pct)}
                    </value>
                </div>
                <div class="header-item">
                    <label>Best Win Rate</label>
                    <value>{format_percent(best_result['metrics']['win_rate']) if best_result else 'N/A'}</value>
                </div>
                <div class="header-item">
                    <label>Best Sharpe Ratio</label>
                    <value>{'{:,.2f}'.format(float(best_result['metrics']['sharpe_ratio'])) if best_result else 'N/A'}</value>
                </div>
                <div class="header-item">
                    <label>Best Max Drawdown</label>
                    <!-- FIX: "-X.XX% (-₹Y,YYY)" format matching backtest HTML card -->
                    <value class="{best_max_dd_class}">
                        {best_max_dd_display}
                    </value>
                </div>
                <div class="header-item">
                    <label>Recommended Capital</label>
                    <value>{format_currency(3 * abs(best_result['metrics'].get('max_drawdown_inr', 0))) if best_result else 'N/A'}</value>
                </div>
                <div class="header-item">
                    <label>Return on Capital</label>
                    <value class="{best_return_class}">{format_percent((best_result['metrics']['total_pnl_inr'] / (3 * abs(best_result['metrics'].get('max_drawdown_inr', 1)))) * 100) if best_result else 'N/A'}</value>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Best Performing Parameters</h2>
            {best_params_html}
        </div>

        <div class="section">
            <h2>Best Performance Metrics</h2>
            {best_metrics_html}
        </div>

        <div class="section">
            <h2>Monthly Returns (₹){best_params_label}</h2>
            {monthly_html}
        </div>

        <div class="section">
            <h2>Yearly Returns (₹){best_params_label}</h2>
            {yearly_html}
        </div>

        <div class='section'>
            <h2>Risk Management</h2>
            <div class='metric-grid'>
                <div class='metric-card'><label>Recommended Capital</label><value>{format_currency(3 * abs(best_result['metrics'].get('max_drawdown_inr', 0))) if best_result else 'N/A'}</value></div>
                <div class='metric-card'><label>Max Drawdown (₹)</label><value class='negative'>{format_currency(abs(best_result['metrics'].get('max_drawdown_inr', 0))) if best_result else 'N/A'}</value></div>
                <div class='metric-card'><label>Max DD Duration</label><value>{best_result['metrics'].get('max_drawdown_duration', 'N/A') if best_result else 'N/A'}</value></div>
                <div class='metric-card'><label>Return on Capital Total</label><value class='positive'>{format_percent((best_result['metrics']['total_pnl_inr'] / (3 * abs(best_result['metrics'].get('max_drawdown_inr', 1)))) * 100) if best_result else 'N/A'}</value></div>
                <div class='metric-card'><label>Best Month ROC</label><value class='positive'>{format_percent(max([(pnl / (3 * abs(best_result['metrics'].get('max_drawdown_inr', 1)))) * 100 for pnl in best_result['metrics'].get('monthly_returns', {1: 0}).values()], default=0)) if best_result else 'N/A'}</value></div>
                <div class='metric-card'><label>Avg Monthly ROC</label><value>{format_percent((sum(best_result['metrics'].get('monthly_returns', {}).values()) / max(len(best_result['metrics'].get('monthly_returns', {})), 1) / (3 * abs(best_result['metrics'].get('max_drawdown_inr', 1)))) * 100) if best_result else 'N/A'}</value></div>
                <div class='metric-card'><label>Return / Max DD Ratio</label><value>{'{:,.2f}'.format(abs(best_result['metrics'].get('total_pnl_inr', 0) / best_result['metrics'].get('max_drawdown_inr', 1))) if best_result else 'N/A'}</value></div>
                <div class='metric-card'><label>Sharpe Ratio</label><value>{'{:,.2f}'.format(float(best_result['metrics'].get('sharpe_ratio', 0))) if best_result else 'N/A'}</value></div>
            </div>
        </div>


        <div class="section">
            <h2>All Optimization Results</h2>
            {all_results_table}
        </div>

        <div class="footer">
            <p>Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>
    </div>
</body>
</html>
"""

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_best_result(self):
        if not self.optimization_results:
            return None
        return max(
            self.optimization_results,
            key=lambda x: x['metrics'].get('total_pnl_inr', -float('inf'))
        )

    def _format_params_for_html(self, params):
        html = "<div class='metric-grid'>"
        for name, value in params.items():
            html += f"""
            <div class="metric-card">
                <label>{name.replace('_', ' ').title()}</label>
                <value>{value}</value>
            </div>"""
        html += "</div>"
        return html

    def _format_metrics_for_html(self, metrics):
        """
        Metrics grid for Best Performance section.
        FIX: Return % = net_pnl_inr / initial_capital_inr * 100 (portfolio margin)
        FIX: Max Drawdown = "-X.XX% (-₹Y,YYY)" format matching backtest HTML
        FIX: all % values use format_percent() (adds % symbol)
        """
        html = "<div class='metric-grid'>"

        net_pnl_inr       = metrics.get('total_pnl_inr', 0)
        total_charges_inr = metrics.get('total_charges_inr', 0)
        gross_pnl_inr     = net_pnl_inr + total_charges_inr

        # FIX: Return % = net_pnl_inr / initial_capital_usd * 100 (AlgoTest USD denominator)
        total_pnl_pct = (net_pnl_inr / self.initial_capital_inr) * 100

        # Max Drawdown — pct + INR value in same card (matches backtest HTML)
        max_dd_pct = metrics.get('max_drawdown_pct', 0)
        max_dd_inr = metrics.get('max_drawdown_inr', 0)
        max_dd_display = f"{format_percent(max_dd_pct)} (-{format_currency(abs(max_dd_inr))})"

        key_metrics = [
            ('Total PnL (₹)',     net_pnl_inr,                      'currency'),
            ('Gross PnL (₹)',     gross_pnl_inr,                    'currency'),
            ('Total Charges (₹)', total_charges_inr,                'currency'),
            ('Return %',          total_pnl_pct,                    'percent'),
            ('Win Rate %',        metrics.get('win_rate', 0),       'percent'),
            ('Profit Factor',     metrics.get('profit_factor', 0),  'decimal'),
            ('Expectancy (₹)',    metrics.get('expectancy_inr', 0), 'currency'),
            ('Avg Win (₹)',       metrics.get('avg_win_inr', 0),    'currency'),
            ('Avg Loss (₹)',      metrics.get('avg_loss_inr', 0),   'currency'),
            ('Max Drawdown',      max_dd_display,                   'preformatted'),
            ('Sharpe Ratio',      metrics.get('sharpe_ratio', 0),   'decimal'),
            ('Total Trades',      metrics.get('total_trades', 0),   'number'),
        ]

        for label, value, fmt in key_metrics:
            if fmt == 'preformatted':
                formatted_value = value          # already "-X.XX% (-₹Y,YYY)"
            elif fmt == 'currency':
                formatted_value = format_currency(value)
            elif fmt == 'percent':
                formatted_value = format_percent(value)
            else:
                formatted_value = '{:,.2f}'.format(float(value)) if fmt == 'decimal' else format_number(value)

            class_name = ""
            if label in ('Total PnL (₹)', 'Gross PnL (₹)', 'Return %',
                         'Expectancy (₹)', 'Avg Win (₹)'):
                class_name = "positive" if (value if fmt != 'preformatted' else 0) >= 0 else "negative"
            elif label in ('Total Charges (₹)', 'Avg Loss (₹)'):
                class_name = "negative" if (value if fmt != 'preformatted' else 0) < 0 else ""
            elif label == 'Max Drawdown':
                class_name = "negative" if max_dd_pct < 0 else ""

            html += f"""
            <div class="metric-card">
                <label>{label}</label>
                <value class="{class_name}">{formatted_value}</value>
            </div>"""
        html += "</div>"
        return html

    # -----------------------------------------------------------------------
    # _create_all_results_table
    # FIX: Return % = net_pnl_inr / initial_capital_usd * 100 (AlgoTest USD denominator)
    # -----------------------------------------------------------------------
    # -----------------------------------------------------------------------
    # _create_all_results_table
    # FIX: Return % = net_pnl_inr / initial_capital_usd * 100 (AlgoTest USD denominator)
    # FIX: Max Drawdown column = "-3.79% (-₹318,689)" format (pct + INR value)
    # -----------------------------------------------------------------------
    def _create_all_results_table(self):
        if not self.optimization_results:
            return "<p>No optimization results to display.</p>"

        rows = []
        for res in self.optimization_results:
            net_pnl_inr = res['metrics'].get('total_pnl_inr', 0)
            max_dd_pct = res['metrics'].get('max_drawdown_pct', 0)
            max_dd_inr = res['metrics'].get('max_drawdown_inr', 0)
            # FIX: preformat Max Drawdown as "-3.79% (-₹318,689)" — matches backtest HTML
            max_dd_display = f"{format_percent(max_dd_pct)} (-{format_currency(abs(max_dd_inr))})"

            row = {
                **res['parameters'],
                'total_pnl_inr': net_pnl_inr,
                # FIX: USD denominator (100,000) matches AlgoTest portfolio margin format
                'return_pct': (net_pnl_inr / self.initial_capital_inr) * 100,
                'win_rate': res['metrics'].get('win_rate', 0),
                'profit_factor': res['metrics'].get('profit_factor', 0),
                'sharpe_ratio': res['metrics'].get('sharpe_ratio', 0),
                'max_drawdown_pct': max_dd_display,  # FIX: preformatted string, not raw float
                'total_trades': res['metrics'].get('total_trades', 0),
            }
            rows.append(row)

        df_results = pd.DataFrame(rows)

        display_columns = (
                list(self.optimization_results[0]['parameters'].keys()) +
                ['total_pnl_inr', 'return_pct', 'win_rate',
                 'profit_factor', 'sharpe_ratio', 'max_drawdown_pct', 'total_trades']
        )
        display_columns = [c for c in display_columns if c in df_results.columns]
        df_results = df_results[display_columns]

        df_results.rename(columns={
            'total_pnl_inr': 'Total PnL (₹)',
            'return_pct': 'Return %',
            'win_rate': 'Win Rate %',
            'profit_factor': 'Profit Factor',
            'sharpe_ratio': 'Sharpe Ratio',
            'max_drawdown_pct': 'Max Drawdown',  # FIX: no % suffix — value is preformatted string
            'total_trades': 'Total Trades',
            **{k: k.replace('_', ' ').title()
               for k in self.optimization_results[0]['parameters'].keys()}
        }, inplace=True)

        df_results['Total PnL (₹)'] = df_results['Total PnL (₹)'].apply(format_currency)
        df_results['Return %'] = df_results['Return %'].apply(format_percent)
        df_results['Win Rate %'] = df_results['Win Rate %'].apply(format_percent)
        # FIX: Max Drawdown already preformatted string — NO .apply() needed, skip it
        df_results['Profit Factor'] = df_results['Profit Factor'].apply(lambda x: '{:,.2f}'.format(float(x)))
        df_results['Sharpe Ratio'] = df_results['Sharpe Ratio'].apply(lambda x: '{:,.2f}'.format(float(x)))
        df_results['Total Trades'] = df_results['Total Trades'].apply(format_number)

        def color_val(val):
            try:
                num_val = float(
                    str(val).replace('₹', '').replace(',', '')
                    .replace('+', '').replace('%', '')
                )
                return 'positive' if num_val >= 0 else 'negative'
            except Exception:
                return ''

        html_table = "<table><thead><tr>"
        for col in df_results.columns:
            html_table += f"<th>{col}</th>"
        html_table += "</tr></thead><tbody>"

        for _, row in df_results.iterrows():
            html_table += "<tr>"
            for col in df_results.columns:
                cell_value = row[col]
                cell_class = ""
                if col in ['Total PnL (₹)', 'Return %']:
                    cell_class = color_val(cell_value)
                elif col == 'Max Drawdown':
                    # FIX: color from preformatted string — negative if starts with '-'
                    cell_class = 'negative' if str(cell_value).startswith('-') else ''
                html_table += f"<td class='{cell_class}'>{cell_value}</td>"
            html_table += "</tr>"
        html_table += "</tbody></table>"

        return html_table
