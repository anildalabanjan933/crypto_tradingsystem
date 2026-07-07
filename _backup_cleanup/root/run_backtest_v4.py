# run_backtest_v4.py
from engine.backtest_engine import run_backtest
from strategies.pnf_bearish_variant_4b_v4 import PnFBearishVariant4BV4
from backtest_analyzer import BacktestReportGenerator
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

STRATEGY_NAME = "PnFBearishVariant4BV4"
SYMBOL        = "BTCUSD"
CSV_PATH      = "data/btc_1m_delta.csv"

# ── Menu Inputs ───────────────────────────────────────────────
LOT_SIZE = int(input("Enter lot size (e.g. 100): ").strip())
SLIPPAGE = float(input("Enter slippage $ per side (0 = no slippage): ").strip())

print("\nSelect date range:")
print("  1. 1 Month")
print("  2. 3 Months")
print("  3. 6 Months")
print("  4. 1 Year")
print("  5. 2 Years")
print("  6. 3 Years")
print("  7. 4 Years")
print("  8. 5 Years")
print("  9. Custom Date Range")

date_choice = input("Enter choice (1-9): ").strip()

today = datetime.today().date()

if date_choice == "1":
    END_DATE   = str(today)
    START_DATE = str(today - relativedelta(months=1))
elif date_choice == "2":
    END_DATE   = str(today)
    START_DATE = str(today - relativedelta(months=3))
elif date_choice == "3":
    END_DATE   = str(today)
    START_DATE = str(today - relativedelta(months=6))
elif date_choice == "4":
    END_DATE   = str(today)
    START_DATE = str(today - relativedelta(years=1))
elif date_choice == "5":
    END_DATE   = str(today)
    START_DATE = str(today - relativedelta(years=2))
elif date_choice == "6":
    END_DATE   = str(today)
    START_DATE = str(today - relativedelta(years=3))
elif date_choice == "7":
    END_DATE   = str(today)
    START_DATE = str(today - relativedelta(years=4))
elif date_choice == "8":
    END_DATE   = str(today)
    START_DATE = str(today - relativedelta(years=5))
elif date_choice == "9":
    START_DATE = input("Enter start date (YYYY-MM-DD): ").strip()
    END_DATE   = input("Enter end date   (YYYY-MM-DD): ").strip()
else:
    print("Invalid choice. Exiting.")
    exit(1)

print(f"  Date range: {START_DATE} to {END_DATE}")

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
