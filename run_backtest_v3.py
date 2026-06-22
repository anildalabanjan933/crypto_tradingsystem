from engine.backtest_engine import run_backtest
from strategies.pnf_bearish_variant_4b_v3 import PnFBearishVariant4BV3
from backtest_analyzer import BacktestReportGenerator

STRATEGY_NAME = "PnFBearishVariant4BV3"
SYMBOL        = "BTCUSD"
LOT_SIZE      = 1
START_DATE    = "2025-06-10"
END_DATE      = "2026-06-10"
CSV_PATH      = "data/btc_1m_delta.csv"

print(f"\nRunning {STRATEGY_NAME} backtest...")

result = run_backtest(
    strategy_class=PnFBearishVariant4BV3,
    symbol=SYMBOL,
    lot_size=LOT_SIZE,
    start_date=START_DATE,
    end_date=END_DATE,
    csv_path=CSV_PATH
)

generator = BacktestReportGenerator(
    trades=result['trades'],
    metrics=result['metrics'],
    strategy_name=STRATEGY_NAME,
    symbol=SYMBOL,
    start_date=START_DATE,
    end_date=END_DATE
)

html_path = generator.generate_html_report()
csv_path  = generator.generate_csv_trade_log()

print(f"HTML report: {html_path}")
print(f"Trade log:   {csv_path}")
