# run_renko_backtest.py
# Runner script for Renko options strategy backtest
# Edit the CONFIG block below to change any settings, then run:
#   python run_renko_backtest.py

import sys
import traceback

print("Python:", sys.version)
print("Script started")

try:
    from engine.renko_backtest_engine import RenkoBacktestEngine
    print("Import OK")
except Exception:
    print("IMPORT FAILED:")
    traceback.print_exc()
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════
CONFIG = {

    # ── Data ──────────────────────────────────────────────────────────
    'csv_path'        : 'data/btc_2h_delta.csv',
    'symbol'          : 'BTCUSD',
    'start_date'      : None,
    'end_date'        : None,

    # ── Capital & Lots ────────────────────────────────────────────────
    'initial_capital' : 1000.0,
    'future_lots'     : 100,
    'usd_to_inr'      : 84.0,

    # ── Strategy mode ─────────────────────────────────────────────────
    # 1 = Momentum Hedged | 2 = DTE-0 Income | 3 = Deep ITM Covered
    'strategy_mode'   : 1,
    'mode'            : 1,        # RenkoOptionsStrategy reads 'mode'

    # ── Renko settings ────────────────────────────────────────────────
    'renko_box'       : 200,

    # ── Supertrend ────────────────────────────────────────────────────
    'st_atr_len'      : 5,
    'st_factor'       : 4.0,

    # ── Swing detection ───────────────────────────────────────────────
    'swing_left'      : 2,
    'swing_right'     : 2,

    # ── S/R tolerance (absolute: box * sr_tolerance = USD band) ───────
    'sr_tolerance'    : 0.5,      # 0.5 * $200 box = $100 band

    # ── Charges: ZERO for chart validation run ─────────────────────────
    'slippage_usd'    : 0,        # zero = no price distortion on chart
    'commission_pct'  : 0.0,      # zero = see raw signal P&L only

    # ── Strategy 1 options (set to 1.0 = futures-only test) ───────────
    'otm1_premium'    : 1.0,
    'otm4_premium'    : 1.0,
    'otm1_strike_gap' : 500,
    'otm4_strike_gap' : 2000,
    'trade_dte'       : 7,
    'decay_pct'       : 80,

    # ── Strategy 2 options (set to 1.0 = futures-only test) ───────────
    'dte0_daily_premium' : 1.0,

    # ── Strategy 3 options (set to 1.0 = futures-only test) ───────────
    'deep_itm_premium'   : 1.0,
    'deep_itm_strike_gap': 3000,
}

# ══════════════════════════════════════════════════════════════════════
# RUN
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    try:
        engine  = RenkoBacktestEngine(CONFIG)
        results = engine.run()

        trades = results['trades']
        if trades:
            print("\nTop 5 trades by Net P&L:")
            print(f"  {'#':<5} {'Dir':<6} {'Entry Date':<22} {'Entry $':>10} "
                  f"{'Exit Date':<22} {'Exit $':>10} {'Net P&L':>10} {'Type':<10}")
            print(f"  {'─' * 95}")
            sorted_trades = sorted(trades, key=lambda x: x.get('net_pnl', 0), reverse=True)
            for t in sorted_trades[:5]:
                print(f"  {str(t.get('trade_number','')):<5} "
                      f"{str(t.get('direction','')):<6} "
                      f"{str(t.get('entry_datetime','')):<22} "
                      f"${t.get('entry_price', 0):>9,.1f} "
                      f"{str(t.get('exit_datetime','')):<22} "
                      f"${t.get('exit_price', 0):>9,.1f} "
                      f"${t.get('net_pnl', 0):>9,.2f} "
                      f"{str(t.get('entry_type','')):<10}")

            print("\nBottom 5 trades by Net P&L:")
            print(f"  {'#':<5} {'Dir':<6} {'Entry Date':<22} {'Entry $':>10} "
                  f"{'Exit Date':<22} {'Exit $':>10} {'Net P&L':>10} {'Type':<10}")
            print(f"  {'─' * 95}")
            for t in sorted_trades[-5:]:
                print(f"  {str(t.get('trade_number','')):<5} "
                      f"{str(t.get('direction','')):<6} "
                      f"{str(t.get('entry_datetime','')):<22} "
                      f"${t.get('entry_price', 0):>9,.1f} "
                      f"{str(t.get('exit_datetime','')):<22} "
                      f"${t.get('exit_price', 0):>9,.1f} "
                      f"${t.get('net_pnl', 0):>9,.2f} "
                      f"{str(t.get('entry_type','')):<10}")

        print(f"\nValidation CSV: output/renko_validation_trades.csv")
        print("Open this file and paste the first 15 rows for chart validation.")

    except Exception:
        print("\nFATAL ERROR:")
        traceback.print_exc()
        sys.exit(1)
