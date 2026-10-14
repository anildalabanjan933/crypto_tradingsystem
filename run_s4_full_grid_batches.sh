#!/bin/bash
cd ~/crypto_trading_system
source .venv/bin/activate
for i in 1 2 3 4 5 6; do
  echo "=== BATCH $i/6 STARTING: $(date) ===" >> logs/optimization_s4_fullgrid.log
  nice -n 19 ionice -c3 .venv/bin/python3 scripts/run_optimization_cli.py \
    --strategy RenkoSMIIOSupertrendStrategy \
    --group s4_full_grid_box$i \
    --lots 100 --start 2024-01-01 --end 2026-08-31 \
    --slippage 5 --symbol BTCUSD --csv data/btc_1m_delta.csv \
    >> logs/optimization_s4_fullgrid.log 2>&1
  echo "=== BATCH $i/6 FINISHED: $(date) ===" >> logs/optimization_s4_fullgrid.log
  free_mb=$(free -m | awk '/^Mem:/{print $7}')
  echo "=== AVAILABLE RAM AFTER BATCH $i: ${free_mb}Mi ===" >> logs/optimization_s4_fullgrid.log
  sleep 10
done
echo "=== ALL 6 BATCHES COMPLETE: $(date) ===" >> logs/optimization_s4_fullgrid.log
