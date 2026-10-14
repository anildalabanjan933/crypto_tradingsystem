# main.py
# Responsibility: Main menu orchestrator

from run_single_strategy import run_single_strategy
from run_optimization import run_optimization_workflow
from run_portfolio_backtest import run_portfolio_backtest
from data.download_market_data import run_download_menu
import sys

def main_menu():
    """
    Displays the main menu and handles user input.
    """
    while True:
        print("\n" + "=" * 70)
        print("CRYPTO TRADING BACKTEST ENGINE")
        print("=" * 70)
        print("\nMain Menu:")
        print("1. Single Strategy Backtest")
        print("2. Portfolio Backtest - Predefined")
        print("3. Portfolio Backtest - Dynamic")
        print("4. Strategy Optimization")
        print("5. Download / Update Market Data")
        print("6. Exit")
        print("=" * 70)

        choice = input("Enter choice (1-6): ")

        if choice == "1":
            run_single_strategy()
        elif choice == "2":
            print("Portfolio Backtest - Predefined - Not yet implemented.")
        elif choice == "3":
            run_portfolio_backtest()
        elif choice == "4":
            run_optimization_workflow()
        elif choice == "5":
            run_download_menu()
        elif choice == "6":
            print("Exiting. Goodbye!")
            sys.exit()
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main_menu()
