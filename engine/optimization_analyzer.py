# engine/optimization_analyzer.py
# Responsibility: Analyze and report optimization results

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from datetime import datetime
from utils import format_currency, format_number, round_price, round_percent, usd_to_inr


class OptimizationAnalyzer:
    """
    Analyzes and generates reports for optimization results.
    """

    def __init__(self, optimization_results, strategy_name, symbol, start_date, end_date):
        self.optimization_results = optimization_results
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = 100000  # Assuming fixed initial capital for optimization comparison

    def generate_html_report(self):
        """
        Generates an HTML report summarizing optimization results.
        """
        print("📊 Generating Optimization HTML report...")

        os.makedirs("output", exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_file = f"output/optimization_results_{self.strategy_name}_{self.symbol}_{timestamp}.html"

        html_content = self._create_html_template()

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"✅ Optimization report saved: {html_file}")
        return html_file

    def _create_html_template(self):
        """
        Creates the full HTML content for the optimization report.
        """
        best_result = self._get_best_result()
        best_params_html = self._format_params_for_html(best_result['parameters']) if best_result else "N/A"
        best_metrics_html = self._format_metrics_for_html(best_result['metrics']) if best_result else "N/A"

        all_results_table = self._create_all_results_table()

        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Optimization Report - {self.strategy_name}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}

        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}

        .header-info {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}

        .header-item {{
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 5px;
        }}

        .header-item label {{
            font-size: 12px;
            opacity: 0.9;
            display: block;
            margin-bottom: 5px;
        }}

        .header-item value {{
            font-size: 18px;
            font-weight: bold;
        }}

        .section {{
            background: white;
            padding: 25px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        .section h2 {{
            font-size: 20px;
            margin-bottom: 20px;
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}

        th {{
            background-color: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}

        td {{
            padding: 12px;
            border-bottom: 1px solid #ddd;
        }}

        tr:hover {{
            background-color: #f9f9f9;
        }}

        .positive {{
            color: #27ae60;
            font-weight: bold;
        }}

        .negative {{
            color: #e74c3c;
            font-weight: bold;
        }}

        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}

        .metric-card {{
            background: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #667eea;
        }}

        .metric-card label {{
            font-size: 12px;
            color: #666;
            display: block;
            margin-bottom: 5px;
        }}

        .metric-card value {{
            font-size: 18px;
            font-weight: bold;
            display: block;
        }}

        .footer {{
            text-align: center;
            padding: 20px;
            color: #999;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Optimization Report: {self.strategy_name}</h1>
            <p>{self.symbol} | {self.start_date} to {self.end_date}</p>

            <div class="header-info">
                <div class="header-item">
                    <label>Total Combinations</label>
                    <value>{len(self.optimization_results)}</value>
                </div>
                <div class="header-item">
                    <label>Best PnL (₹)</label>
                    <value class="{'positive' if best_result and best_result['metrics']['total_pnl_inr'] >= 0 else 'negative'}">{format_currency(best_result['metrics']['total_pnl_inr']) if best_result else 'N/A'}</value>
                </div>
                <div class="header-item">
                    <label>Best Return %</label>
                    <value class="{'positive' if best_result and best_result['metrics']['total_pnl_pct'] >= 0 else 'negative'}">{round_percent(best_result['metrics']['total_pnl_pct']) if best_result else 'N/A'}%</value>
                </div>
                <div class="header-item">
                    <label>Best Win Rate</label>
                    <value>{round_percent(best_result['metrics']['win_rate']) if best_result else 'N/A'}%</value>
                </div>
                <div class="header-item">
                    <label>Best Sharpe Ratio</label>
                    <value>{format_number(best_result['metrics']['sharpe_ratio']) if best_result else 'N/A'}</value>
                </div>
                <div class="header-item">
                    <label>Best Max Drawdown</label>
                    <value class="{'negative' if best_result and best_result['metrics']['max_drawdown_pct'] < 0 else ''}">{round_percent(best_result['metrics']['max_drawdown_pct']) if best_result else 'N/A'}%</value>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>🏆 Best Performing Parameters</h2>
            {best_params_html}
        </div>

        <div class="section">
            <h2>📈 Best Performance Metrics</h2>
            {best_metrics_html}
        </div>

        <div class="section">
            <h2>📊 All Optimization Results</h2>
            {all_results_table}
        </div>

        <div class="footer">
            <p>Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>
    </div>
</body>
</html>
"""

    def _get_best_result(self):
        """
        Finds the best result based on Net PnL.
        """
        if not self.optimization_results:
            return None

        # Sort by total_pnl_inr to find the best
        sorted_results = sorted(self.optimization_results,
                                key=lambda x: x['metrics'].get('total_pnl_inr', -float('inf')), reverse=True)
        return sorted_results[0]

    def _format_params_for_html(self, params):
        """Formats parameters into an HTML list."""
        html = "<div class='metric-grid'>"
        for name, value in params.items():
            html += f"""
            <div class="metric-card">
                <label>{name.replace('_', ' ').title()}</label>
                <value>{value}</value>
            </div>
            """
        html += "</div>"
        return html

    def _format_metrics_for_html(self, metrics):
        """Formats key metrics into an HTML grid."""
        html = "<div class='metric-grid'>"
        key_metrics = [
            ('Total PnL (₹)', metrics.get('total_pnl_inr', 0), True),
            ('Return %', metrics.get('total_pnl_pct', 0), True),
            ('Win Rate', metrics.get('win_rate', 0), True),
            ('Profit Factor', metrics.get('profit_factor', 0), False),
            ('Expectancy (₹)', metrics.get('expectancy_inr', 0), True),
            ('Max Drawdown', metrics.get('max_drawdown_pct', 0), True),
            ('Sharpe Ratio', metrics.get('sharpe_ratio', 0), False),
            ('Total Trades', metrics.get('total_trades', 0), False),
        ]
        for label, value, is_currency_or_percent in key_metrics:
            if is_currency_or_percent:
                formatted_value = format_currency(value) if 'PnL' in label or 'Expectancy' in label else round_percent(
                    value) + '%'
            else:
                formatted_value = format_number(value)

            class_name = ""
            if 'PnL' in label or 'Return' in label or 'Expectancy' in label:
                class_name = "positive" if value >= 0 else "negative"
            elif 'Drawdown' in label:
                class_name = "negative" if value < 0 else ""

            html += f"""
            <div class="metric-card">
                <label>{label}</label>
                <value class="{class_name}">{formatted_value}</value>
            </div>
            """
        html += "</div>"
        return html

    def _create_all_results_table(self):
        """
        Creates an HTML table for all optimization results.
        """
        if not self.optimization_results:
            return "<p>No optimization results to display.</p>"

        df_results = pd.DataFrame([
            {**res['parameters'], **{f"Metric_{k}": v for k, v in res['metrics'].items()}}
            for res in self.optimization_results
        ])

        # Select and reorder columns for display
        display_columns = list(self.optimization_results[0]['parameters'].keys()) + [
            'Metric_total_pnl_inr', 'Metric_total_pnl_pct', 'Metric_win_rate', 'Metric_profit_factor',
            'Metric_max_drawdown_pct'
        ]
        df_results = df_results[display_columns]

        # Rename columns for readability
        df_results.rename(columns={
            'Metric_total_pnl_inr': 'Total PnL (₹)',
            'Metric_total_pnl_pct': 'Return %',
            'Metric_win_rate': 'Win Rate %',
            'Metric_profit_factor': 'Profit Factor',
            'Metric_max_drawdown_pct': 'Max Drawdown %',
            **{k: k.replace('_', ' ').title() for k in self.optimization_results[0]['parameters'].keys()}
        }, inplace=True)

        # Format numeric columns
        for col in ['Total PnL (₹)']:
            df_results[col] = df_results[col].apply(lambda x: format_currency(x))
        for col in ['Return %', 'Win Rate %', 'Max Drawdown %']:
            df_results[col] = df_results[col].apply(lambda x: round_percent(x) + '%')
        for col in ['Profit Factor']:
            df_results[col] = df_results[col].apply(lambda x: format_number(x))

        # Add color coding to PnL and Return columns
        def color_pnl(val):
            if isinstance(val, str) and '₹' in val:
                num_val = float(val.replace('₹', '').replace(',', '').replace('+', ''))
            elif isinstance(val, str) and '%' in val:
                num_val = float(val.replace('%', ''))
            else:
                num_val = val

            if num_val >= 0:
                return 'positive'
            return 'negative'

        # Apply CSS classes to cells
        html_table = "<table><thead><tr>"
        for col in df_results.columns:
            html_table += f"<th>{col}</th>"
        html_table += "</tr></thead><tbody>"

        for index, row in df_results.iterrows():
            html_table += "<tr>"
            for col in df_results.columns:
                cell_value = row[col]
                cell_class = ""
                if col in ['Total PnL (₹)', 'Return %', 'Max Drawdown %']:
                    cell_class = color_pnl(cell_value)
                html_table += f"<td class='{cell_class}'>{cell_value}</td>"
            html_table += "</tr>"
        html_table += "</tbody></table>"

        return html_table

