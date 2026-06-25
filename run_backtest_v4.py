# run_backtest_v4.py
from engine.backtest_engine import run_backtest
from strategies.pnf_bearish_variant_4b_v4 import PnFBearishVariant4BV4
from backtest_analyzer import BacktestReportGenerator

STRATEGY_NAME = "PnFBearishVariant4BV4"
SYMBOL        = "BTCUSD"
CSV_PATH      = "data/btc_1m_delta.csv"

# ── Menu Inputs ───────────────────────────────────────────────
LOT_SIZE   = int(input("Enter lot size (e.g. 100): ").strip())
START_DATE = input("Enter start date (YYYY-MM-DD): ").strip()
END_DATE   = input("Enter end date   (YYYY-MM-DD): ").strip()
SLIPPAGE   = float(input("Enter slippage $ per side (0 = no slippage): ").strip())

print(f"\nRunning {STRATEGY_NAME} backtest...")

result = run_backtest(
    strategy_class=PnFBearishVariant4BV4,
    symbol=SYMBOL,
    lot_size=LOT_SIZE,
    start_date=START_DATE,
    end_date=END_DATE,
    csv_path=CSV_PATH,
    slippage=SLIPPAGE
)

generator = BacktestReportGenerator(
    trades=result['trades'],
    metrics=result['metrics'],
    strategy_name=STRATEGY_NAME,
    symbol=SYMBOL,
    start_date=START_DATE,
    end_date=END_DATE,
    slippage=SLIPPAGE
)

html_path = generator.generate_html_report()
csv_path  = generator.generate_csv_trade_log()

print(f"HTML report: {html_path}")
print(f"Trade log:   {csv_path}")
