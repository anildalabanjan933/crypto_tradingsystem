content = open('scripts/run_backtest_cli.py').read()
new_reporter = """    reporter = BacktestReportGenerator(
        trades=result.get('trades', []),
        metrics=result.get('metrics', {}),
        strategy_name=args.strategy,
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        slippage=args.slippage
    )
    reporter.generate_html_report()
    reporter.generate_csv_report()
    print("Reports saved to output/")"""

import re
fixed = re.sub(
    r'reporter = BacktestReportGenerator\(.*?print\("Reports saved to output/"\)',
    new_reporter.strip(),
    content,
    flags=re.DOTALL
)
open('scripts/run_backtest_cli.py', 'w').write(fixed)
print('FIXED')
