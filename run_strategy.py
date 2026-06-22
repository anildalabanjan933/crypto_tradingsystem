# run_strategy.py
# Responsibility: Complete pipeline - fetch data, run strategy, generate CSV

import os
from datetime import datetime
from data.delta_exchange_fetcher import fetch_and_prepare_data
from strategies.futures.bullish_trend_pullback import run_bullish_trend_pullback_strategy
from strategies.futures.pnf_pullback import run_pnf_pullback_strategy
from strategies.options.long_call import run_long_call_strategy
from engine.trade_builder import build_trades
from algotest_csv_generator import generate_algotest_csv, validate_algotest_header


def main():
    """
    Complete pipeline:
    1. Select strategy
    2. Fetch data (if multi-timeframe strategy)
    3. Run strategy
    4. Build trade records
    5. Generate AlgoTest CSV
    6. Run backtest analysis
    """

    print("\n" + "=" * 70)
    print("BACKTEST STRATEGY - COMPLETE PIPELINE")
    print("=" * 70)

    # Step 1: Validate CSV header
    print("\n[Step 1] Validating AlgoTest CSV header...")
    try:
        validate_algotest_header()
        print("✅ Header schema validated")
    except ValueError as e:
        print(f"❌ Header validation failed: {e}")
        return

    # Step 2: Select strategy
    print("\n[Step 2] Selecting strategy...")
    print("Available strategies:")
    print("  1. Futures - Bullish Trend Pullback (Multi-Timeframe)")
    print("  2. Futures - PnF Pullback (Sample)")
    print("  3. Options - Long Call (Sample)")

    choice = input("\nEnter strategy choice (1, 2, or 3): ").strip()

    signals = None
    use_mtf = False

    if choice == "1":
        print("\n📊 Running Futures - Bullish Trend Pullback strategy...")
        strategy_name = "bullish_trend_pullback"
        strategy_type = "futures"
        use_mtf = True
    elif choice == "2":
        print("\n📊 Running Futures - PnF Pullback strategy...")
        signals = run_pnf_pullback_strategy()
        strategy_name = "pnf_pullback"
        strategy_type = "futures"
        use_mtf = False
    elif choice == "3":
        print("\n📊 Running Options - Long Call strategy...")
        signals = run_long_call_strategy()
        strategy_name = "long_call"
        strategy_type = "options"
        use_mtf = False
    else:
        print("❌ Invalid choice. Exiting.")
        return

    # Step 3: Fetch and prepare data (for multi-timeframe strategies)
    if use_mtf:
        print("\n[Step 3] Fetching and preparing BTC data...")
        data_30m, data_1h, data_4h = fetch_and_prepare_data(
            start_date="2024-01-01",
            end_date="2025-12-31"
        )

        if data_30m is None or data_1h is None or data_4h is None:
            print("❌ Failed to fetch and prepare data")
            return

        # Step 4: Run strategy
        print("\n[Step 4] Running Bullish Trend Pullback strategy...")
        try:
            signals = run_bullish_trend_pullback_strategy(data_4h, data_1h, data_30m)

            if len(signals) == 0:
                print("⚠️  No signals generated")
                return

            print(f"✅ Generated {len(signals)} signals")

        except Exception as e:
            print(f"❌ Strategy execution failed: {e}")
            import traceback
            traceback.print_exc()
            return

    else:
        # For non-MTF strategies, signals already generated
        if signals is None or len(signals) == 0:
            print("⚠️  No signals generated")
            return

        print(f"✅ Generated {len(signals)} signals")

    # Step 5: Build trade records
    print("\n[Step 5] Building trade records...")
    try:
        trade_records = build_trades(signals, size_qty=1, initial_capital=100000)

        if len(trade_records) == 0:
            print("⚠️  No trades generated")
            return

        print(f"✅ Built {len(trade_records)} trade records")

        # Display sample trades
        print(f"\nSample trades:")
        for i, trade in enumerate(trade_records[:5]):
            print(
                f"  Trade #{trade['trade_number']}: {trade['entry_type']} @ {trade['entry_price']} → {trade['exit_type']} @ {trade['exit_price']}")
            print(f"    PnL: {trade['net_pnl']} ({trade['net_pnl_pct']}%)")

        if len(trade_records) > 5:
            print(f"  ... and {len(trade_records) - 5} more trades")

    except Exception as e:
        print(f"❌ Trade building failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 6: Generate AlgoTest CSV
    print("\n[Step 6] Generating AlgoTest CSV...")

    output_dir = f"output/{strategy_type}"
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{strategy_name}_trades_{timestamp}.csv"
    output_path = os.path.join(output_dir, output_filename)

    try:
        generate_algotest_csv(trade_records, output_path)
        print(f"✅ CSV generated successfully")

    except Exception as e:
        print(f"❌ CSV generation failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 7: Run backtest analysis
    print("\n[Step 7] Running backtest analysis...")
    try:
        from backtest_analyzer import BacktestAnalyzer

        analyzer = BacktestAnalyzer(output_path, initial_capital=100000)
        analyzer.run_analysis()

    except Exception as e:
        print(f"⚠️  Backtest analysis skipped: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("✅ PIPELINE COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print(f"\n📊 Strategy Results:")
    print(f"   Strategy: {strategy_name}")
    print(f"   Total trades: {len(trade_records)}")
    print(f"   Total PnL: {trade_records[-1]['cumulative_pnl']}")
    print(f"   Total PnL %: {trade_records[-1]['cumulative_pnl_pct']}%")
    print(f"\n📁 CSV Output:")
    print(f"   {output_path}")
    print(f"\n📊 Equity Curve Chart:")
    print(f"   backtest_equity_curve.png")
    print(f"\n🚀 Next: Upload CSV to AlgoTest or analyze results above")


if __name__ == "__main__":
    main()
