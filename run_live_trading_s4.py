# run_live_trading_s4.py
# S4 RenkoSMIIOSupertrend Live Trading Bot
# Subaccount : S4RenkoSMIOsuptrend
# Testnet    : True (forward test)

import time, os, math, json
# REMOVED: post_signal call
from dotenv import load_dotenv
load_dotenv()
import logging
import requests
import pandas as pd
from datetime import datetime, timezone

from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
from engine.order_manager import OrderManager

# ===========================================================================
# CONFIG
# ===========================================================================
API_KEY    = os.getenv('S4_API_KEY')
API_SECRET = os.getenv('S4_API_SECRET')
TESTNET    = True
LOT_SIZE   = 100  # default - overridden by algo_config.json

def get_lot_size():
    try:
        cfg = json.load(open('dashboard/algo_config.json'))
        for a in cfg.get('algos', []):
            if a.get('name') == 'S4':
                return int(a.get('lots', 100))
    except:
        pass
    return LOT_SIZE
CSV_PATH   = 'data/btc_1m_delta.csv'
LOG_PATH   = 'logs/live_trading_s4.log'
SYMBOL     = 'BTCUSD'
SLEEP_SEC  = 60          # fallback only
CANDLE_SEC = 7200        # 2H candle = 7200 seconds

def sleep_until_next_candle_close(candle_seconds, buffer_sec=5):
    """Sleep until next candle close + buffer. Matches backtest entry timing exactly."""
    now = datetime.now(timezone.utc).timestamp()
    next_close = (math.floor(now / candle_seconds) + 1) * candle_seconds
    sleep_secs = next_close - now + buffer_sec
    next_close_dt = datetime.fromtimestamp(next_close, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    logging.info(f'[SLEEP] Next candle close: {next_close_dt} | Sleeping {sleep_secs:.0f}s')
    time.sleep(max(sleep_secs, 1))

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
    df_csv['timestamp'] = pd.to_datetime(df_csv['Date'] + ' ' + df_csv['Time'], format='mixed')
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

        _strat_init = RenkoSMIIOSupertrendStrategy(
            data_dict={'2h': _df_2h_init},
            lot_size=LOT_SIZE,
            renko_box_pct=0.001,
            renko_timeframe='2h',
            st_atr_length=10,
            st_factor=2.0,
            smiio_shortlen=20,
            smiio_siglen=7,
        )
        _sigs_init = _strat_init.generate_signals()
        last_known_ts = _sigs_init[-1].get('timestamp') if _sigs_init else None
        logging.info(f'[STARTUP] last_known_ts={last_known_ts} | total signals={len(_sigs_init)}')
    except Exception as _e:
        last_known_ts = None
        logging.warning(f'[STARTUP] Pre-load failed: {_e}')

    # Load last_known_ts from file if exists (survives restart)
    try:
        _ts_file = 'logs/last_known_ts_s4.txt'
        if os.path.exists(_ts_file):
            _saved_ts = open(_ts_file).read().strip()
            if _saved_ts and (last_known_ts is None or str(_saved_ts) > str(last_known_ts)):
                last_known_ts = _saved_ts
                logging.info(f'[STARTUP] Loaded last_known_ts from file: {last_known_ts}')
    except Exception as _e2:
        logging.warning(f'[STARTUP] Could not load ts file: {_e2}')

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

                # Sync new candles to CSV so backtest uses identical data


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
                renko_box_pct=0.001,
                renko_timeframe='2h',
                st_atr_length=10,
                st_factor=2.0,
                smiio_shortlen=20,
                smiio_siglen=7,
            )
            signals = strategy.generate_signals()
            logging.info(f'[SIGNALS] total={len(signals)}')

            # --- Only process signals newer than last known ts ---
            new_signals = [
                s for s in signals
                if last_known_ts is None or str(s.get('timestamp', '')) > str(last_known_ts)
            ]

            if new_signals:
                # Process signals IN ORDER - EXIT first then ENTRY
                for sig in new_signals:
                    sig_type   = sig.get('signal_type')
                    direction  = sig.get('direction')
                    entry_type = sig.get('entry_type', '')
                    exit_type  = sig.get('exit_type', '')
                    sig_ts     = sig.get('timestamp')

                    if sig_type == 'EXIT' and position is not None:
                        # Save ts BEFORE order to prevent duplicate on crash/restart
                        last_known_ts = sig_ts
                        open('logs/last_known_ts_s4.txt','w').write(str(sig_ts))
                        if position == 'long':
                            result = order_manager.close_position(get_lot_size(), 'sell')
                            if result.get('success'):
                                logging.info(f'[ORDER] EXIT sell {LOT_SIZE} lots | type={exit_type} | ts={sig_ts}')
                            else:
                                logging.error(f'[ORDER] EXIT sell FAILED | error={result.get("error")} | ts={sig_ts}')
                                break
                        elif position == 'short':
                            result = order_manager.close_position(get_lot_size(), 'buy')
                            if result.get('success'):
                                logging.info(f'[ORDER] EXIT buy {LOT_SIZE} lots | type={exit_type} | ts={sig_ts}')
                            else:
                                logging.error(f'[ORDER] EXIT buy FAILED | error={result.get("error")} | ts={sig_ts}')
                                break
                        if result.get('success'):
                            position = None

                    elif sig_type == 'ENTRY' and position is None:
                        # Save ts BEFORE order to prevent duplicate on crash/restart
                        last_known_ts = sig_ts
                        open('logs/last_known_ts_s4.txt','w').write(str(sig_ts))
                        if direction == 'long':
                            result = order_manager.place_market_order('buy', get_lot_size())
                            if result.get('success'):
                                position = 'long'
                                logging.info(f'[ORDER] ENTRY buy {LOT_SIZE} lots | type={entry_type} | ts={sig_ts}')
                            else:
                                logging.error(f'[ORDER] ENTRY buy FAILED | error={result.get("error")} | ts={sig_ts}')
                                break
                        elif direction == 'short':
                            result = order_manager.place_market_order('sell', get_lot_size())
                            if result.get('success'):
                                position = 'short'
                                logging.info(f'[ORDER] ENTRY sell {LOT_SIZE} lots | type={entry_type} | ts={sig_ts}')
                            else:
                                logging.error(f'[ORDER] ENTRY sell FAILED | error={result.get("error")} | ts={sig_ts}')
                                break

                    else:
                        logging.info(f'[SKIP] Signal blocked | sig_type={sig_type} | position={position} | ts={sig_ts}')
            else:
                logging.info(f'[WAIT] No new signals since {last_known_ts}')

        except Exception as e:
            logging.error(f'[ERROR] {e}', exc_info=True)

        time.sleep(SLEEP_SEC)


if __name__ == '__main__':
    main()
