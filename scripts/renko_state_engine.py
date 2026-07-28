#!/usr/bin/env python3
import os,sys,time,logging,glob,threading,json
try:
    import websocket
    WS_AVAILABLE=True
except ImportError:
    WS_AVAILABLE=False
sys.path.insert(0,"/home/anildalabanjan933/crypto_trading_system")
os.chdir("/home/anildalabanjan933/crypto_trading_system")
from datetime import datetime,timezone,timedelta
import warnings,io,contextlib
import pandas as pd
import numpy as np
warnings.filterwarnings("ignore")
from indicators.renko import RenkoBuilder,SupertrendIndicator
from data.download_market_data import download_or_update
from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy

import datetime as _logdt
class _ISTFormatter(logging.Formatter):
    def formatTime(self,record,datefmt=None):
        ist=_logdt.datetime.utcfromtimestamp(record.created)+_logdt.timedelta(hours=5,minutes=30)
        return ist.strftime("%d-%b-%Y %I:%M:%S %p IST")
_handler=logging.FileHandler("logs/renko_state_engine.log",mode="a")
_handler.setFormatter(_ISTFormatter("%(asctime)s %(levelname)s %(message)s"))
logging.basicConfig(level=logging.INFO,handlers=[_handler])
log=logging.getLogger(__name__)

CSV_PATH="data/btc_1m_delta.csv"
LOT_SIZE=100
SLEEP_SEC=1
S2_PARAMS=dict(renko_box_pct=0.001,renko_timeframe="30m",st_atr_length=10,st_factor=2.0)
S4_PARAMS=dict(renko_box_pct=0.001,renko_timeframe="2h",st_atr_length=5,st_factor=2.0,smiio_shortlen=10,smiio_longlen=10,smiio_siglen=3)

def compute_smiio(closes,short_len=5,long_len=20,signal_len=5):
    n=len(closes); mom=np.zeros(n); abs_mom=np.zeros(n)
    for i in range(1,n): mom[i]=closes[i]-closes[i-1]; abs_mom[i]=abs(mom[i])
    def ema(arr,p):
        out=np.zeros(len(arr)); k=2.0/(p+1); out[0]=arr[0]
        for i in range(1,len(arr)): out[i]=arr[i]*k+out[i-1]*(1-k)
        return out
    e1m=ema(mom,short_len); e2m=ema(e1m,long_len)
    e1a=ema(abs_mom,short_len); e2a=ema(e1a,long_len)
    smi=np.where(e2a!=0,e2m/e2a*100.0,0.0)
    return smi,ema(smi,signal_len)

class StrategyState:
    def __init__(self,label,params):
        self.label=label; self.params=params
        self.candles_1m=None; self.last_1m_ts=None
        self.candles_tf=None  # pre-built 1H or 2H dataframe - built once on startup
        self.current_direction=None; self.last_signal_ts=None; self.last_exit_ts=None
        self.box_size=None



def get_trade_csv(label):
    import glob
    p="output/trade_log_RenkoReversalStrategy_BTCUSD_*.csv" if label=="S2" else "output/trade_log_RenkoSMIIOSupertrendStrategy_BTCUSD_*.csv"
    files=sorted(glob.glob(p),reverse=True)
    return files[0] if files else None

def get_last_csv_row(label):
    try:
        f=get_trade_csv(label)
        if not f: return None
        import pandas as pd
        df=pd.read_csv(f)
        return df.iloc[-1].to_dict() if not df.empty else None
    except: return None

def append_trade_to_csv(trade,label):
    try:
        import pandas as pd
        f=get_trade_csv(label)
        if not f: return False
        df=pd.read_csv(f)
        df=pd.concat([df,pd.DataFrame([trade])],ignore_index=True)
        tmp=f+".tmp"; df.to_csv(tmp,index=False)
        import os; os.replace(tmp,f)
        return True
    except: return False

def write_signal_file(label,sig_type,direction,sig_ts):
    import os
    sig_line=f"{sig_type}_{direction.upper()}|{sig_ts}|100"
    sf=f"logs/live_signal_s{label[-1]}.txt"
    tmp=sf+".tmp"; open(tmp,"w").write(sig_line); os.replace(tmp,sf)

def touch_signal_file(label):
    import os
    sf=f"logs/live_signal_s{label[-1]}.txt"
    if os.path.exists(sf): os.utime(sf,None)

def get_csv_last_ts():
    try:
        with open("data/btc_1m_delta.csv","rb") as f:
            f.seek(-300,2)
            ll=f.read().decode("utf-8",errors="ignore").strip().split("\n")[-1]
        pts=ll.split(",")
        if len(pts)>=2:
            import pandas as pd
            return pd.to_datetime(pts[0].strip()+" "+pts[1].strip())
    except: pass
    return None

def resample_to_tf(df_1m,tf):
    import pandas as pd
    rule=tf.replace("H","h").replace("T","min").replace("m","min")
    df=df_1m.copy().set_index("timestamp")
    df_tf=df["Close"].resample(rule).ohlc()
    df_tf.columns=["open","high","low","close"]
    return df_tf.dropna().reset_index()



def load_history(state):
    import pandas as pd
    from datetime import datetime,timezone
    log_msg=f"[{state.label}] Loading full history..."
    log.info(log_msg)
    df=pd.read_csv("data/btc_1m_delta.csv")
    df["timestamp"]=pd.to_datetime(df["Date"]+" "+df["Time"])
    df=df.sort_values("timestamp").reset_index(drop=True)
    now_utc=datetime.now(timezone.utc).replace(second=0,microsecond=0)
    cur=now_utc.strftime("%Y-%m-%d %H:%M:%S")
    df=df[df["timestamp"].astype(str)<cur]
    state.candles_1m=df
    state.last_1m_ts=df["timestamp"].iloc[-1] if not df.empty else None
    # Calculate box_size matching exact backtest formula
    tf=state.params["renko_timeframe"]
    _df_tf=resample_to_tf(df,tf)
    if _df_tf is not None and len(_df_tf)>0:
        _closes=_df_tf["close"].values
        if state.label=="S2":
            # S2 backtest uses iloc[-1] = last close of full history
            state.box_size=max(1,round(_closes[-1]*state.params["renko_box_pct"]))
        else:
            # S4 backtest uses closes[0] = first close of full history
            state.box_size=max(1,round(_closes[0]*state.params["renko_box_pct"]))
        log.info(f"[{state.label}] box_size={state.box_size} (matches backtest exactly)")
    log.info(f"[{state.label}] Loaded {len(df):,} candles | last={state.last_1m_ts}")
    # Pre-build 1H/2H dataframe ONCE - no resample on every signal check
    tf=state.params["renko_timeframe"]
    state.candles_tf=resample_to_tf(df,tf)
    log.info(f"[{state.label}] Pre-built {tf} dataframe: {len(state.candles_tf)} candles")

def append_new_candles(state):
    import pandas as pd
    from datetime import datetime,timezone
    try:
        # Read only last 200 lines - cheap operation
        with open("data/btc_1m_delta.csv","rb") as f:
            f.seek(0,2); fsize=f.tell()
            f.seek(max(0,fsize-20000),0)
            tail=f.read().decode("utf-8",errors="ignore")
        lines=[l for l in tail.split("\n") if l.strip() and not l.startswith("Date")]
        if not lines: return False
        rows=[]
        for l in lines:
            pts=l.split(",")
            if len(pts)>=6:
                try:
                    ts=pd.to_datetime(pts[0].strip()+" "+pts[1].strip())
                    rows.append({"timestamp":ts,"Open":float(pts[2]),"High":float(pts[3]),"Low":float(pts[4]),"Close":float(pts[5])})
                except: pass
        if not rows: return False
        df_new=pd.DataFrame(rows)
        now_utc=datetime.now(timezone.utc).replace(second=0,microsecond=0)
        cur=now_utc.strftime("%Y-%m-%d %H:%M:%S")
        df_new=df_new[df_new["timestamp"].astype(str)<cur]
        new_rows=df_new[df_new["timestamp"]>state.last_1m_ts]
        if new_rows.empty: return False
        state.candles_1m=pd.concat([state.candles_1m,new_rows],ignore_index=True)
        state.last_1m_ts=state.candles_1m["timestamp"].iloc[-1]
        log.info(f"[{state.label}] +{len(new_rows)} candles | last={state.last_1m_ts}")
        # Update pre-built tf dataframe incrementally - append only new rows
        tf=state.params["renko_timeframe"]
        new_tf=resample_to_tf(new_rows,tf)
        if new_tf is not None and not new_tf.empty:
            state.candles_tf=pd.concat([state.candles_tf,new_tf],ignore_index=True)
            state.candles_tf=state.candles_tf.drop_duplicates(subset=["timestamp"],keep="last").reset_index(drop=True)
        return True
    except Exception as e:
        log.error(f"[{state.label}] append error: {e}",exc_info=True)
        return False



def check_and_fire(state,is_s4=False):
    import pandas as pd
    from datetime import datetime,timezone
    try:
        p=state.params
        tf=p["renko_timeframe"]
        # Use pre-built tf dataframe - built once on startup - zero resample cost
        df_tf=state.candles_tf
        if df_tf is None or len(df_tf)<10: return
        # Build data_dict exactly like backtest engine
        df_tf_indexed=df_tf.copy()
        if "timestamp" in df_tf_indexed.columns:
            df_tf_indexed=df_tf_indexed.set_index("timestamp")
        data_dict={tf:df_tf_indexed}
        # Call EXACT same strategy class as backtest - single source of truth
        if not is_s4:
            strategy=RenkoReversalStrategy(data_dict,LOT_SIZE,**p)
        else:
            strategy=RenkoSMIIOSupertrendStrategy(data_dict,LOT_SIZE,**p)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with contextlib.redirect_stdout(io.StringIO()):
                signals=strategy.generate_signals()
        if not signals: return
        now_utc=datetime.now(timezone.utc)
        # Collect ALL new signals after last_signal_ts - oldest first
        new_sigs=[]
        for sig in signals:
            ts=sig.get("timestamp","")
            if not ts: continue
            if state.last_signal_ts and ts<=state.last_signal_ts: continue
            if ts==state.last_exit_ts: continue
            new_sigs.append(sig)
        if not new_sigs: return
        # Fire ONE signal at a time - EXIT before ENTRY - oldest first
        for sig in new_sigs:
            ts=sig.get("timestamp","")
            sig_type=sig.get("signal_type","")
            direction=sig.get("direction","")
            price=float(sig.get("price",0))
            box=state.box_size if state.box_size else 100
            if sig_type=="EXIT" and state.current_direction==direction:
                _fire(state,ts,price,direction,"EXIT",box,now_utc,signals); return
            elif sig_type in ("BUY_A","BUY_B","SELL_A","SELL_B","ENTRY") and state.current_direction is None:
                _fire(state,ts,price,direction,"ENTRY",box,now_utc,signals); return
    except Exception as e:
        log.error(f"[{state.label}] check error: {e}",exc_info=True)

def _fire(state,ts,cl,direction,sig_type,box,now_utc,signals=None):
    from datetime import datetime,timezone
    # INSTANT CSV append - no full backtest rerun
    # Append only new signal row directly to signals CSV
    try:
        import csv as _csv, os as _os
        sig_label = state.label[-1]  # "2" or "4"
        sig_csv = f"logs/signals_s{sig_label}.csv"
        # Read existing signals
        existing = []
        if _os.path.exists(sig_csv):
            with open(sig_csv,"r") as _f:
                existing = list(_csv.reader(_f))
        # Only append if this signal not already in CSV
        already = any(len(r)>=2 and r[0]==ts for r in existing)
        if not already and sig_type=="ENTRY" and signals:
            # Find matching exit from signals list
            exit_ts = None
            for _sig in signals:
                if _sig.get("timestamp","") > ts and _sig.get("signal_type","") in ("EXIT","SELL_A","SELL_B","BUY_A","BUY_B"):
                    exit_ts = _sig.get("timestamp","")
                    break
            if exit_ts:
                tmp = sig_csv+".tmp"
                with open(tmp,"w",newline="") as _f:
                    _w = _csv.writer(_f)
                    for r in existing:
                        _w.writerow(r)
                    _w.writerow([ts, exit_ts, direction, 100, round(float(cl),2)])
                _os.replace(tmp, sig_csv)
                log.info(f"[{state.label}] INSTANT CSV append: {ts},{exit_ts},{direction}")
            else:
                log.warning(f"[{state.label}] No exit found for {ts} - signal file only")
        elif sig_type=="EXIT":
            log.info(f"[{state.label}] EXIT signal - CSV already has entry row")
    except Exception as _e:
        log.error(f"[{state.label}] CSV append failed: {_e}")
    write_signal_file(state.label,sig_type,direction,ts)
    if sig_type == "ENTRY":
        try:
            _ep = float(cl) if cl else 0.0
            _exit_ts_alert = exit_ts if exit_ts else ""
            _xp = 0.0
            if _exit_ts_alert and signals:
                for _s in signals:
                    if _s.get("timestamp","") == _exit_ts_alert:
                        _xp = float(_s.get("price", 0.0))
                        break
            _send_bt_signal_alert(state.label, direction, ts, _exit_ts_alert, _ep, _xp)
        except Exception as _ae:
            log.warning(f"[TELEGRAM] BT alert error: {_ae}")
    state.last_signal_ts=ts
    if sig_type=="EXIT": state.last_exit_ts=ts
    state.current_direction=direction if sig_type=="ENTRY" else None
    log.info(f"[{state.label}] {sig_type} {direction} at {ts}")




def update_market_data():
    import io,contextlib
    from data.download_market_data import download_or_update
    try:
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            download_or_update("BTC")
        log.info("[ENGINE] Market data updated")
    except Exception as e:
        log.error(f"[ENGINE] update error: {e}")

if __name__=="__main__":
    log.info("[ENGINE] Renko State Engine starting - TradingView style")
    log.info("[ENGINE] Loads history ONCE - only new bricks checked - zero recalculation")
    log.info("[ENGINE] Only closed candles - zero repaint - zero false signal")
    log.info("[ENGINE] Backtest files untouched - single source of truth")

    s2=StrategyState("S2",S2_PARAMS)
    s4=StrategyState("S4",S4_PARAMS)
    load_history(s2)
    load_history(s4)
    # Lock last_signal_ts BEFORE startup check - use last SIGNAL ts not market CSV ts
    def _get_signal_ts(path):
        try:
            line=open(path).read().strip()
            if line:
                return line.split("|")[1]
        except:
            pass
        return None
    def _get_csv_last_exit_ts(pattern):
        import glob, csv as _csv
        files=sorted(glob.glob(pattern))
        if not files: return None
        try:
            rows=list(_csv.reader(open(files[-1])))
            for row in reversed(rows):
                if len(row)>4 and row[4] and row[4]!="exit_datetime":
                    return row[4]
        except:
            pass
        return None
    # PRIMARY lock = bot last_known_ts files (always correct)
    # FALLBACK = signal file (only if ts file missing)
    try:
        _ts_s2=open("/home/anildalabanjan933/crypto_trading_system/logs/last_known_ts_s2.txt").read().strip() or None
        if _ts_s2: log.info(f"[ENGINE] S2 lock from bot ts file: {_ts_s2}")
    except: _ts_s2=None
    try:
        _ts_s4=open("/home/anildalabanjan933/crypto_trading_system/logs/last_known_ts_s4.txt").read().strip() or None
        if _ts_s4: log.info(f"[ENGINE] S4 lock from bot ts file: {_ts_s4}")
    except: _ts_s4=None
    _now_lock=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    if not _ts_s2:
        _ts_s2=_now_lock
        log.info(f"[ENGINE] S2 no ts file - lock set to NOW: {_ts_s2}")
    else:
        _ts_s2=max(_ts_s2,_now_lock)
        log.info(f"[ENGINE] S2 lock set to max(ts_file,NOW): {_ts_s2}")
    if not _ts_s4:
        _ts_s4=_now_lock
        log.info(f"[ENGINE] S4 no ts file - lock set to NOW: {_ts_s4}")
    else:
        _ts_s4=max(_ts_s4,_now_lock)
        log.info(f"[ENGINE] S4 lock set to max(ts_file,NOW): {_ts_s4}")
    s2.last_signal_ts=_ts_s2
    log.info(f"[ENGINE] S2 startup lock ts: {_ts_s2}")
    s4.last_signal_ts=_ts_s4
    log.info(f"[ENGINE] S4 startup lock ts: {_ts_s4}")
    _last_dl=time.time()
    _last_ts=get_csv_last_ts()
    _last_csv_regen=time.time()

    # WebSocket for instant candle close detection
    _ws_last_candle_start=None
    _ws_lock=threading.Lock()

    def _ws_on_message(ws,message):
        global _ws_last_candle_start
        try:
            data=json.loads(message)
            if data.get("type")!="candlestick_1m": return
            candle_start=data.get("candle_start_time",0)
            if candle_start==0: return
            with _ws_lock:
                if _ws_last_candle_start is None:
                    _ws_last_candle_start=candle_start
                    return
                if candle_start<=_ws_last_candle_start: return
                _ws_last_candle_start=candle_start
            # Completed candle detected instantly via WebSocket
            log.info(f"[WS] Completed candle detected - updating data")
            _ws_state["last_dl"]=time.time()
            _new_ts=get_csv_last_ts()
            if _new_ts is None: return
            append_new_candles(s2)
            append_new_candles(s4)
            _cur_s2=_last_closed_tf(30)
            if _cur_s2>_ws_state["last_s2_tf"]:
                _ws_state["last_s2_tf"]=_cur_s2
                log.info(f"[WS] New 30m candle closed: {_cur_s2} - checking S2")
                check_and_fire(s2,is_s4=False)
            _cur_s4=_last_closed_tf(120)
            if _cur_s4>_ws_state["last_s4_tf"]:
                _ws_state["last_s4_tf"]=_cur_s4
                log.info(f"[WS] New 2H candle closed: {_cur_s4} - checking S4")
                check_and_fire(s4,is_s4=True)
        except Exception as e:
            log.error(f"[WS] Message error: {e}")

    def _ws_on_error(ws,error): log.error(f"[WS] Error: {error}")
    def _ws_on_close(ws,*a): log.warning("[WS] Closed - polling fallback active")
    def _ws_on_open(ws):
        log.info("[WS] Connected - instant candle detection active")
        ws.send(json.dumps({"type":"subscribe","payload":{"channels":[{"name":"candlestick_1m","symbols":["BTCUSD"]}]}}))

    _ws_fail_count=[0]
    def _ws_thread():
        while True:
            try:
                if WS_AVAILABLE:
                    ws=websocket.WebSocketApp("wss://socket.india.delta.exchange",
                        on_open=_ws_on_open,on_message=_ws_on_message,
                        on_error=_ws_on_error,on_close=_ws_on_close)
                    ws.run_forever(ping_interval=20,ping_timeout=8)
                    _ws_fail_count[0]+=1
                    if _ws_fail_count[0]>=10:
                        try:
                            from engine.telegram_alert import send_alert
                            _msg = "CTS ENGINE WARNING - WebSocket disconnected " + str(_ws_fail_count[0]) + " times. Engine still running via polling. Check VM if alerts stop."
                            send_alert(_msg)
                        except: pass
                        _ws_fail_count[0]=0
            except Exception as e:
                log.error(f"[WS] Thread error: {e}")
            log.warning("[WS] Reconnecting in 5s...")
            time.sleep(5)

    if WS_AVAILABLE:
        _t=threading.Thread(target=_ws_thread,daemon=True)
        _t.start()
        log.info("[ENGINE] WebSocket thread started - instant candle detection")
    else:
        log.warning("[ENGINE] websocket-client not installed - polling only")

    import pandas as _pd2
    from datetime import datetime as _dt2,timezone as _tz2

    def _last_closed_tf(tf_minutes):
        now=_dt2.now(_tz2.utc).replace(second=0,microsecond=0,tzinfo=None)
        import math
        floored=_dt2(now.year,now.month,now.day,
                     (now.hour*60+now.minute)//tf_minutes*tf_minutes//60,
                     (now.hour*60+now.minute)//tf_minutes*tf_minutes%60)
        # last CLOSED candle = one tf before current open
        import datetime as _dtt
        return floored - _dtt.timedelta(minutes=tf_minutes)

    _last_s2_tf=_last_closed_tf(30)
    _last_s4_tf=_last_closed_tf(120)
    # State dict for ws thread - defined after tf vars
    _ws_state={"last_s2_tf":_last_s2_tf,"last_s4_tf":_last_s4_tf,"last_dl":0.0}
    # Startup check - fires only if current time is at 1H/2H boundary
    check_and_fire(s2,is_s4=False)
    check_and_fire(s4,is_s4=True)

    while True:
        try:
            if time.time()-_last_dl>=300 and time.time()-_ws_state.get("last_dl",0)>=30:
                update_market_data()
                _last_dl=time.time()

            csv_last=get_csv_last_ts()
            from datetime import datetime,timezone
            now_m=datetime.now(timezone.utc).replace(second=0,microsecond=0,tzinfo=None)
            if csv_last is not None:
                cl_naive=csv_last.to_pydatetime().replace(tzinfo=None)
                if cl_naive>=now_m: csv_last=None

            if csv_last is not None and csv_last!=_last_ts:
                _last_ts=csv_last
                log.info(f"[ENGINE] New candle: {csv_last}")
                append_new_candles(s2)
                append_new_candles(s4)

                # S2: fire only on new closed 30m candle (shared state with WS)
                cur_s2_tf=_last_closed_tf(30)
                if cur_s2_tf>_ws_state["last_s2_tf"]:
                    _ws_state["last_s2_tf"]=cur_s2_tf
                    log.info(f"[ENGINE] New 30m candle closed: {cur_s2_tf} - checking S2")
                    check_and_fire(s2,is_s4=False)

                # S4: fire only on new closed 2H candle (shared state with WS)
                cur_s4_tf=_last_closed_tf(120)
                if cur_s4_tf>_ws_state["last_s4_tf"]:
                    _ws_state["last_s4_tf"]=cur_s4_tf
                    log.info(f"[ENGINE] New 2H candle closed: {cur_s4_tf} - checking S4")
                    check_and_fire(s4,is_s4=True)

            # Boundary watcher trigger - fires if watcher detected missed boundary
            _trig_s2 = "logs/boundary_trigger_s2.txt"
            _trig_s4 = "logs/boundary_trigger_s4.txt"
            if os.path.exists(_trig_s2):
                _t2 = open(_trig_s2).read().strip()
                os.remove(_trig_s2)
                try:
                    _t2_dt = __import__('datetime').datetime.strptime(_t2, '%Y-%m-%d %H:%M:%S')
                except:
                    _t2_dt = __import__('datetime').datetime.strptime(_t2, '%Y-%m-%dT%H:%M:%S')
                if _t2_dt > _ws_state["last_s2_tf"]:
                    _ws_state["last_s2_tf"] = _t2_dt
                    log.info(f"[ENGINE] Boundary watcher trigger S2: {_t2} - checking S2")
                    append_new_candles(s2)
                    check_and_fire(s2, is_s4=False)
            if os.path.exists(_trig_s4):
                _t4 = open(_trig_s4).read().strip()
                os.remove(_trig_s4)
                try:
                    _t4_dt = __import__('datetime').datetime.strptime(_t4, '%Y-%m-%d %H:%M:%S')
                except:
                    _t4_dt = __import__('datetime').datetime.strptime(_t4, '%Y-%m-%dT%H:%M:%S')
                if _t4_dt > _ws_state["last_s4_tf"]:
                    _ws_state["last_s4_tf"] = _t4_dt
                    log.info(f"[ENGINE] Boundary watcher trigger S4: {_t4} - checking S4")
                    append_new_candles(s4)
                    check_and_fire(s4, is_s4=True)

            touch_signal_file("S2")
            touch_signal_file("S4")

            # Regenerate CSV every 30 minutes regardless of signal - keeps Section 13/14 always fresh
            if time.time()-_last_csv_regen>=1800:
                try:
                    import subprocess as _sp2, io as _io2, contextlib as _ctx2
                    with _ctx2.redirect_stdout(_io2.StringIO()), _ctx2.redirect_stderr(_io2.StringIO()):
                        _sp2.run([".venv/bin/python","scripts/generate_signals.py"],
                                capture_output=True, timeout=120,
                                cwd="/home/anildalabanjan933/crypto_trading_system")
                    _last_csv_regen=time.time()
                    log.info("[ENGINE] Periodic CSV regeneration complete")
                except Exception as _ce:
                    log.error(f"[ENGINE] Periodic CSV regen failed: {_ce}")

        except Exception as e:
            log.error(f"[ENGINE] Error: {e}",exc_info=True)

        # Write heartbeat every cycle - bots check this before placing orders
        try:
            open('logs/engine_heartbeat.txt','w').write(str(__import__('time').time()))
        except:
            pass
        time.sleep(SLEEP_SEC)

def _send_bt_signal_alert(strategy_label, direction, entry_ts, exit_ts, entry_price, exit_price, lots=100, slippage=5.0):
    """Send Telegram alert when backtest signal fires."""
    try:
        from engine.telegram_alert import send_alert
        import datetime as _dt

        def _to_ist(ts_str):
            try:
                dt = _dt.datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
                dt_ist = dt + _dt.timedelta(hours=5, minutes=30)
                return dt_ist.strftime("%d-%b-%Y %I:%M %p IST")
            except:
                return ts_str

        slip_total = slippage * 2 * lots * 0.001
        gross_pnl  = (exit_price - entry_price) if direction == "long" else (entry_price - exit_price)
        gross_pnl  = gross_pnl * lots * 0.001
        net_pnl    = round(gross_pnl - slip_total, 2)
        sign       = "+" if net_pnl >= 0 else ""

        slip10_total = 10.0 * 2 * lots * 0.001
        net_pnl10    = round(gross_pnl - slip10_total, 2)
        sign10       = "+" if net_pnl10 >= 0 else ""
        msg = (
            f"CTS BACKTEST {strategy_label} SIGNAL\n"
            f"Direction : {direction.upper()}\n"
            f"Entry time: {_to_ist(entry_ts)}\n"
            f"Exit time : {_to_ist(exit_ts)}\n"
            f"BT Entry  : ${entry_price:,.2f}\n"
            f"BT Exit   : ${exit_price:,.2f}\n"
            f"Est PnL ($5/side) : {sign}${net_pnl:,.2f}\n"
            f"Est PnL ($10/side): {sign10}${net_pnl10:,.2f}"
        )
        send_alert(msg)
    except Exception as e:
        log.warning(f"[TELEGRAM] BT signal alert failed: {e}")
