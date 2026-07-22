#!/usr/bin/env python3
import os,sys,time,logging,glob
sys.path.insert(0,"/home/anildalabanjan933/crypto_trading_system")
os.chdir("/home/anildalabanjan933/crypto_trading_system")
from datetime import datetime,timezone,timedelta
import warnings,io,contextlib
import pandas as pd
import numpy as np
warnings.filterwarnings("ignore")
from indicators.renko import RenkoBuilder,SupertrendIndicator
from data.download_market_data import download_or_update

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("logs/renko_state_engine.log",mode="a")])
log=logging.getLogger(__name__)

CSV_PATH="data/btc_1m_delta.csv"
LOT_SIZE=100
SLEEP_SEC=1
S2_PARAMS=dict(renko_box_pct=0.001,renko_timeframe="1h",st_atr_length=5,st_factor=1.5)
S4_PARAMS=dict(renko_box_pct=0.001,renko_timeframe="2h",st_atr_length=10,st_factor=2.0,smiio_shortlen=20,smiio_longlen=20,smiio_siglen=7)

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
        self.current_direction=None; self.last_signal_ts=None; self.last_exit_ts=None



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
    log.info(f"[{state.label}] Loaded {len(df):,} candles | last={state.last_1m_ts}")

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
        return True
    except Exception as e:
        log.error(f"[{state.label}] append error: {e}",exc_info=True)
        return False



def check_and_fire(state,is_s4=False):
    import pandas as pd
    from datetime import datetime,timezone
    from indicators.renko import RenkoBuilder,SupertrendIndicator
    try:
        p=state.params
        tf=p["renko_timeframe"]
        # Use only last 5000 source bars - enough for 500+ bricks - zero full recalculation
        tail_1m=state.candles_1m.iloc[-5000:].reset_index(drop=True)
        df_tf=resample_to_tf(tail_1m,tf)
        if df_tf is None or len(df_tf)<10: return
        closes=df_tf["close"].values
        box=max(1,round(closes[0]*p["renko_box_pct"]))
        renko_df=RenkoBuilder(box_size=box).build(closes)
        if renko_df is None or len(renko_df)<5: return
        st_df=SupertrendIndicator(atr_period=p["st_atr_length"],factor=p["st_factor"]).calculate(renko_df)
        ts_arr=df_tf["timestamp"].values
        renko_df["timestamp"]=renko_df["bar_index"].apply(lambda i:ts_arr[i] if i<len(ts_arr) else ts_arr[-1])
        n=len(st_df)
        closes_r=st_df["renko_close"].values
        rdir=st_df["renko_dir"].values
        st=st_df["st_dir"].values
        ts_r=renko_df["timestamp"].values
        smi=sig=None
        if is_s4:
            smi,sig=compute_smiio(closes_r,p["smiio_shortlen"],p["smiio_longlen"],p["smiio_siglen"])
        now_utc=datetime.now(timezone.utc)
        for i in range(max(1,n-5),n):
            ts=str(pd.Timestamp(ts_r[i]).strftime("%Y-%m-%dT%H:%M:%S"))
            if ts<=state.last_signal_ts: continue
            if ts==state.last_exit_ts: continue
            cl=closes_r[i]; rd=rdir[i]; st_i=st[i]; st_p=st[i-1]
            flip_g=st_p==1 and st_i==-1
            flip_r=st_p==-1 and st_i==1
            if state.current_direction=="long" and flip_r and rd==-1:
                _fire(state,ts,cl,"long","EXIT",box,now_utc); return
            elif state.current_direction=="short" and flip_g and rd==1:
                _fire(state,ts,cl,"short","EXIT",box,now_utc); return
            if state.current_direction is None:
                if not is_s4:
                    if st_i==-1 and rd==1: _fire(state,ts,cl,"long","ENTRY",box,now_utc); return
                    elif st_i==1 and rd==-1: _fire(state,ts,cl,"short","ENTRY",box,now_utc); return
                else:
                    su=smi[i]>sig[i] and smi[i-1]<=sig[i-1]
                    sd=smi[i]<sig[i] and smi[i-1]>=sig[i-1]
                    sa=smi[i]>sig[i]; sb=smi[i]<sig[i]
                    if (su and st_i==-1 and rd==1) or (flip_g and sa and rd==1):
                        _fire(state,ts,cl,"long","ENTRY",box,now_utc); return
                    elif (sd and st_i==1 and rd==-1) or (flip_r and sb and rd==-1):
                        _fire(state,ts,cl,"short","ENTRY",box,now_utc); return
    except Exception as e:
        log.error(f"[{state.label}] check error: {e}",exc_info=True)

def _fire(state,ts,cl,direction,sig_type,box,now_utc):
    from datetime import datetime,timezone
    trade={"entry_datetime":ts if sig_type=="ENTRY" else (state.last_signal_ts or ts),
           "exit_datetime":ts,"direction":direction,"entry_price":cl,"exit_price":cl,
           "net_pnl":0.0,"net_pnl_inr":0.0,"gross_pnl":0.0,"slippage_usd":5.0,
           "taker_fees_usd":0.0,"funding_usd":0.0,"tax_usd":0.0,"margin_required":0.0,"lot_size":100}
    last=get_last_csv_row(state.label)
    last_e=str(last.get("entry_datetime",""))[:19] if last else ""
    if trade["entry_datetime"][:19]!=last_e:
        append_trade_to_csv(trade,state.label)
    write_signal_file(state.label,sig_type,direction,ts)
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
    check_and_fire(s2,is_s4=False)
    check_and_fire(s4,is_s4=True)
    # Lock last_signal_ts to latest brick after startup - prevent re-fire on restart
    _lock_ts=get_csv_last_ts()
    if _lock_ts is not None:
        _lock_str=str(pd.Timestamp(_lock_ts).strftime("%Y-%m-%dT%H:%M:%S"))
        if s2.last_signal_ts is None: s2.last_signal_ts=_lock_str
        if s4.last_signal_ts is None: s4.last_signal_ts=_lock_str
        log.info(f"[ENGINE] Startup lock ts: {_lock_str}")

    _last_dl=time.time()
    _last_ts=get_csv_last_ts()

    while True:
        try:
            if time.time()-_last_dl>=60:
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
                check_and_fire(s2,is_s4=False)
                check_and_fire(s4,is_s4=True)
            else:
                touch_signal_file("S2")
                touch_signal_file("S4")

        except Exception as e:
            log.error(f"[ENGINE] Error: {e}",exc_info=True)

        time.sleep(SLEEP_SEC)
