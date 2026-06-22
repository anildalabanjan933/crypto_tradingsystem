# main.py
# Responsibility: Main menu orchestrator

from run_single_strategy import run_single_strategy
from run_optimization import run_optimization_workflow # NEW import
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
        print("2. Portfolio Backtest (Predefined)")
        print("3. Portfolio Backtest (Dynamic)")
        print("4. Strategy Optimization") # NEW option
        print("5. Exit")
        print("=" * 70)

        choice = input("Enter choice (1-5): ")

        if choice == '1':
            run_single_strategy()
        elif choice == '2':
            print("Portfolio Backtest (Predefined) - Not yet implemented.")
        elif choice == '3':
            print("Portfolio Backtest (Dynamic) - Not yet implemented.")
        elif choice == '4': # NEW option handler
            run_optimization_workflow()
        elif choice == '5':
            print("Exiting. Goodbye!")
            sys.exit()
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main_menu()

