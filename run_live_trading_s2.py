# run_live_trading_s2.py — S2: RenkoReversalStrategy
import time, logging, pandas as pd
from engine.order_manager import OrderManager
from strategies.renko_reversal_strategy import RenkoReversalStrategy
from config.symbol_config import get_renko_box_size

logging.basicConfig(
    filename='logs/live_trading_s2.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
log = logging.getLogger(__name__)

SYMBOL     = 'BTCUSD'
LOT_SIZE   = 100
CSV_PATH   = 'data/btc_1m_delta.csv'
CYCLE_SEC  = 60
API_KEY    = 'your_api_key_here'
API_SECRET = 'your_api_secret_here'

om = OrderManager(api_key=API_KEY, api_secret=API_SECRET, testnet=True)

log.info("[STARTUP] Loading 1M CSV history...")
df_1m = pd.read_csv(CSV_PATH)
df_1m['timestamp'] = pd.to_datetime(df_1m['Date'] + ' ' + df_1m['Time'])
df_1m = df_1m.rename(columns={
    'Open': 'open', 'High': 'high',
    'Low': 'low', 'Close': 'close', 'Volume': 'volume'
})
df_1m = df_1m.set_index('timestamp').sort_index()
log.info(f"[STARTUP] Loaded {len(df_1m)} 1M candles ({df_1m.index[0]} to {df_1m.index[-1]})")

def fetch_latest_1m(since):
    import requests
    since_ts = int(since.timestamp())
    now_ts   = int(time.time())
    url      = 'https://cdn-ind.testnet.deltaex.org/v2/history/candles'
    params   = {'symbol': SYMBOL, 'resolution': '1m', 'start': since_ts, 'end': now_ts}
    resp     = requests.get(url, params=params, timeout=10)
    data     = resp.json()
    if not data.get('success') or not data.get('result'):
        return None
    rows = []
    for c in data['result']:
        from datetime import datetime
        rows.append({
            'timestamp': datetime.fromtimestamp(c['time']),
            'open': c['open'], 'high': c['high'],
            'low': c['low'],   'close': c['close'], 'volume': c['volume']
        })
    df = pd.DataFrame(rows).set_index('timestamp').sort_index()
    return df

def build_2h(df):
    return df.resample('2h').agg(
        open=('open','first'), high=('high','max'),
        low=('low','min'),     close=('close','last'),
        volume=('volume','sum')
    ).dropna()

# --- Position state ---
pos = om.get_position()
if pos.get('success') and pos.get('direction') == 'LONG':
    position = 'long'
elif pos.get('success') and pos.get('direction') == 'SHORT':
    position = 'short'
else:
    position = None
log.info(f"[STARTUP] Position synced from exchange: {position}")

# --- Track last executed signal timestamp to avoid re-execution ---
last_executed_ts = None

while True:
    try:
        last_ts     = df_1m.index[-1]
        new_candles = fetch_latest_1m(since=last_ts)
        if new_candles is not None and len(new_candles) > 0:
            new_candles = new_candles[new_candles.index > last_ts]
            if len(new_candles) > 0:
                df_1m = pd.concat([df_1m, new_candles]).sort_index()
                log.info(f"[DATA] Appended {len(new_candles)} candles. Total={len(df_1m)}")

        df_2h = build_2h(df_1m)
        log.info(f"[DATA] 2H candles={len(df_2h)}")

        box_size = get_renko_box_size(SYMBOL, float(df_2h['close'].iloc[-1]))
        strategy = RenkoReversalStrategy(
            data_dict={'2H': df_2h}, lot_size=LOT_SIZE, renko_box=box_size
        )
        signals = strategy.generate_signals()
        log.info(f"[SIGNALS] total={len(signals)}")

        # --- Execute last new signal only (skip already executed) ---
        if signals:
            # Find last signal not yet executed
            last_signal = None
            for sig in reversed(signals):
                if sig.get('timestamp') != last_executed_ts:
                    last_signal = sig
                    break

            if last_signal:
                stype = last_signal.get('signal_type')
                sdir  = last_signal.get('direction', '')

                if stype == 'ENTRY' and position is None:
                    side = 'buy' if sdir == 'long' else 'sell'
                    om.place_market_order(side=side, size=LOT_SIZE)
                    position = sdir
                    last_executed_ts = last_signal.get('timestamp')
                    log.info(f"[ORDER] ENTRY {side} {LOT_SIZE} lots | type={last_signal.get('entry_type')} | ts={last_executed_ts}")

                elif stype == 'EXIT' and position is not None:
                    side = 'sell' if position == 'long' else 'buy'
                    om.close_position(size=LOT_SIZE, side=side)
                    position = None
                    last_executed_ts = last_signal.get('timestamp')
                    log.info(f"[ORDER] EXIT {side} {LOT_SIZE} lots | type={last_signal.get('exit_type')} | ts={last_executed_ts}")

    except Exception as e:
        log.error(f"[ERROR] {e}", exc_info=True)

    time.sleep(CYCLE_SEC)
