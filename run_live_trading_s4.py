# run_live_trading_s4.py
# S4 RenkoSMIIOSupertrend Live Trading Bot
# Subaccount : S4RenkoSMIOsuptrend
# Testnet    : True (forward test)

import time, os
# REMOVED: post_signal call
from dotenv import load_dotenv
load_dotenv()
import logging
import requests
import pandas as pd
from datetime import datetime, timezone

from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
from engine.order_manager import OrderManager
from config.symbol_config import get_renko_box_size

# ===========================================================================
# CONFIG
# ===========================================================================
API_KEY    = os.getenv('S4_API_KEY')
API_SECRET = os.getenv('S4_API_SECRET')
TESTNET    = True
LOT_SIZE   = 100
CSV_PATH   = 'data/btc_1m_delta.csv'
LOG_PATH   = 'logs/live_trading_s4.log'
SYMBOL     = 'BTCUSD'
SLEEP_SEC  = 60

BASE_URL = 'https://cdn-ind.testnet.deltaex.org' if TESTNET else 'https://api.india.delta.exchange'

# ===========================================================================
# LOGGING
# ===========================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
    ]
)

# ===========================================================================
# LIVE CANDLE FETCH
# ===========================================================================
def fetch_new_candles(start_ts: int, end_ts: int) -> list:
    url = f'{BASE_URL}/v2/history/candles'
    params = {'symbol': SYMBOL, 'resolution': '1m', 'start': start_ts, 'end': end_ts}
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    return data.get('result', [])

# ===========================================================================
# MAIN LOOP
# ===========================================================================
def main():
    # --- STARTUP: Load CSV ---
    logging.info('=' * 60)
    logging.info('S4 RenkoSMIIOSupertrend Live Trading Bot STARTING')
    logging.info(f'Mode      : {"TESTNET" if TESTNET else "LIVE"}')
    logging.info(f'Account   : S4RenkoSMIOsuptrend')
    logging.info(f'Lots      : {LOT_SIZE}')
    logging.info('=' * 60)

    logging.info('[STARTUP] Loading 1M CSV history...')
    df_csv = pd.read_csv(CSV_PATH)
    df_csv['timestamp'] = pd.to_datetime(df_csv['Date'] + ' ' + df_csv['Time'])
    df_csv = df_csv.rename(columns={
        'Open': 'open', 'High': 'high', 'Low': 'low',
        'Close': 'close', 'Volume': 'volume'
    })
    df_csv = df_csv[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    df_csv = df_csv.sort_values('timestamp').reset_index(drop=True)
    logging.info(f'[STARTUP] Loaded {len(df_csv)} 1M candles '
                 f'({df_csv["timestamp"].iloc[0]} to {df_csv["timestamp"].iloc[-1]})')

    df_1m = df_csv.copy()
    last_ts = int(df_1m['timestamp'].iloc[-1].timestamp())

    # --- OrderManager ---
    order_manager = OrderManager(API_KEY, API_SECRET, testnet=TESTNET)

    # --- Box size ---
    current_price = df_1m['close'].iloc[-1]
    box_size = get_renko_box_size(SYMBOL, current_price)

    # --- Position state (persisted across cycles) ---
    pos = order_manager.get_position()
    if pos.get('success') and pos.get('direction') == 'LONG':
        position = 'long'
    elif pos.get('success') and pos.get('direction') == 'SHORT':
        position = 'short'
    else:
        position = None
    logging.info(f'[STARTUP] Position synced from exchange: {position}')

    # --- Fetch live candles first so last_known_ts covers all existing signals ---
    logging.info('[STARTUP] Fetching latest candles before pre-loading signals...')
    try:
        _last_ts = int(df_1m['timestamp'].iloc[-1].timestamp())
        _new = fetch_new_candles(_last_ts + 1, int(datetime.now(timezone.utc).timestamp()))
        if _new:
            _rows = []
            for c in _new:
                _rows.append({
                    'timestamp': pd.to_datetime(c['time'], unit='s', utc=True).tz_localize(None),
                    'open':  float(c['open']),
                    'high':  float(c['high']),
                    'low':   float(c['low']),
                    'close': float(c['close']),
                    'volume': float(c['volume']),
                })
            _df_new = pd.DataFrame(_rows)
            df_1m = pd.concat([df_1m, _df_new], ignore_index=True)
            df_1m = df_1m.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
            last_ts = int(df_1m['timestamp'].iloc[-1].timestamp())
            logging.info(f'[STARTUP] Pre-fetched {len(_df_new)} candles. Total={len(df_1m)}')
    except Exception as _e:
        logging.warning(f'[STARTUP] Pre-fetch failed: {_e}')

    # --- Pre-load signals from full data to get last known ts ---
    logging.info('[STARTUP] Pre-loading signals to find last known timestamp...')
    try:
        _df_1m_idx = df_1m.set_index('timestamp')
        _df_2h_init = _df_1m_idx['close'].resample('2h').ohlc()
        _df_2h_init.columns = ['open', 'high', 'low', 'close']
        _df_2h_init['volume'] = _df_1m_idx['volume'].resample('2h').sum()
        _df_2h_init = _df_2h_init.dropna().reset_index()
        _box_init = get_renko_box_size(SYMBOL, float(_df_2h_init['close'].iloc[-1]))
        _strat_init = RenkoSMIIOSupertrendStrategy(
            data_dict={'2h': _df_2h_init},
            lot_size=LOT_SIZE,
            renko_box=_box_init,
            symbol=SYMBOL,
        )
        _sigs_init = _strat_init.generate_signals()
        last_known_ts = _sigs_init[-1].get('timestamp') if _sigs_init else None
        logging.info(f'[STARTUP] last_known_ts={last_known_ts} | total signals={len(_sigs_init)}')
    except Exception as _e:
        last_known_ts = None
        logging.warning(f'[STARTUP] Pre-load failed: {_e}')

    # --- Main loop ---
    while True:
        try:
            now_ts = int(datetime.now(timezone.utc).timestamp())

            # Fetch new 1M candles
            new_candles = fetch_new_candles(last_ts + 1, now_ts)
            if new_candles:
                rows = []
                for c in new_candles:
                    rows.append({
                        'timestamp': pd.to_datetime(c['time'], unit='s', utc=True).tz_localize(None),
                        'open':  float(c['open']),
                        'high':  float(c['high']),
                        'low':   float(c['low']),
                        'close': float(c['close']),
                        'volume': float(c['volume']),
                    })
                df_new = pd.DataFrame(rows)
                df_1m = pd.concat([df_1m, df_new], ignore_index=True)
                df_1m = df_1m.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
                last_ts = int(df_1m['timestamp'].iloc[-1].timestamp())
                logging.info(f'[DATA] Appended {len(df_new)} candles. Total={len(df_1m)}')

            # Build 2H
            df_1m_indexed = df_1m.set_index('timestamp')
            df_2h = df_1m_indexed['close'].resample('2h').ohlc()
            df_2h.columns = ['open', 'high', 'low', 'close']
            df_2h['volume'] = df_1m_indexed['volume'].resample('2h').sum()
            df_2h = df_2h.dropna().reset_index()
            logging.info(f'[DATA] 2H candles={len(df_2h)}')

            # Generate signals
            strategy = RenkoSMIIOSupertrendStrategy(
                data_dict={'2h': df_2h},
                lot_size=LOT_SIZE,
                renko_box=box_size,
                symbol=SYMBOL,
            )
            signals = strategy.generate_signals()
            logging.info(f'[SIGNALS] total={len(signals)}')

            # --- Only process signals newer than last known ts ---
            new_signals = [
                s for s in signals
                if last_known_ts is None or str(s.get('timestamp', '')) > str(last_known_ts)
            ]

            if new_signals:
                sig        = new_signals[-1]
                sig_type   = sig.get('signal_type')
                direction  = sig.get('direction')
                entry_type = sig.get('entry_type', '')
                exit_type  = sig.get('exit_type', '')
                sig_ts     = sig.get('timestamp')

                if sig_type == 'ENTRY' and position is None:
                    if direction == 'long':
                        order_manager.place_market_order('buy', LOT_SIZE)
# REMOVED: post_signal call
                        position = 'long'
                        last_known_ts = sig_ts
                        logging.info(f'[ORDER] ENTRY buy {LOT_SIZE} lots | type={entry_type} | ts={sig_ts}')
                    elif direction == 'short':
                        order_manager.place_market_order('sell', LOT_SIZE)
# REMOVED: post_signal call
                        position = 'short'
                        last_known_ts = sig_ts
                        logging.info(f'[ORDER] ENTRY sell {LOT_SIZE} lots | type={entry_type} | ts={sig_ts}')

                elif sig_type == 'EXIT' and position is not None:
                    if position == 'long':
                        order_manager.close_position(LOT_SIZE, 'sell')
# REMOVED: post_signal call
                        logging.info(f'[ORDER] EXIT sell {LOT_SIZE} lots | type={exit_type} | ts={sig_ts}')
                    elif position == 'short':
                        order_manager.close_position(LOT_SIZE, 'buy')
# REMOVED: post_signal call
                        logging.info(f'[ORDER] EXIT buy {LOT_SIZE} lots | type={exit_type} | ts={sig_ts}')
                    position = None
                    last_known_ts = sig_ts

                else:
                    logging.info(f'[SKIP] Signal blocked | sig_type={sig_type} | position={position} | ts={sig_ts}')
            else:
                logging.info(f'[WAIT] No new signals since {last_known_ts}')

        except Exception as e:
            logging.error(f'[ERROR] {e}')

        time.sleep(SLEEP_SEC)


if __name__ == '__main__':
    main()
