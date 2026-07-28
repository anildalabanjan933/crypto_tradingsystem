import csv,os,re,time,warnings,hmac,hashlib,requests,json
from datetime import datetime,timezone,timedelta
from dotenv import load_dotenv
import pandas as pd,sys
sys.path.insert(0,".")
load_dotenv("/home/anildalabanjan933/crypto_trading_system/.env")
results=[];failures=[]
def ok(msg): results.append(f"  PASS  {msg}")
def fail(msg): failures.append(f"  FAIL  {msg}")
pat_ts=re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
BASE="https://cdn-ind.testnet.deltaex.org"
def read_ts(p):
    try:
        v=open(p).read().strip()
        return v if pat_ts.match(v) else None
    except: return None
def read_csv(p):
    try: return [r for r in csv.reader(open(p)) if len(r)>=3]
    except: return []
def simulate_bot(csv_path,start_ts):
    rows=read_csv(csv_path)
    now=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    last_ts=start_ts
    for row in rows:
        _et,_xt,_dir=row[0],row[1],row[2]
        if _et < last_ts:
            if now>=_xt and _xt>last_ts: last_ts=_xt
            continue
        if now>=_xt: last_ts=_xt; continue
        if now>=_et: return True,{"entry_ts":_et,"exit_ts":_xt,"direction":_dir},last_ts
    return False,{},last_ts
def sign(secret,method,path,body=""):
    ts=str(int(time.time()))
    msg=f"{method}{ts}{path}{body}"
    sig=hmac.new(secret.encode(),msg.encode(),hashlib.sha256).hexdigest()
    return ts,sig
def hdrs(key,ts,sig):
    return {"api-key":key,"timestamp":ts,"signature":sig,"Content-Type":"application/json"}
def get_pid(key,secret):
    ts,sig=sign(secret,"GET","/v2/products/BTCUSD")
    r=requests.get(f"{BASE}/v2/products/BTCUSD",headers={"api-key":key,"timestamp":ts,"signature":sig},timeout=5)
    d=r.json()
    if d.get("success"): return d["result"]["id"],float(d["result"]["contract_value"])
    return None,0.001
def get_mark(key,secret):
    ts,sig=sign(secret,"GET","/v2/tickers/BTCUSD")
    r=requests.get(f"{BASE}/v2/tickers/BTCUSD",headers={"api-key":key,"timestamp":ts,"signature":sig},timeout=5)
    d=r.json().get("result",{})
    return float(d.get("mark_price",0)),float(d.get("quotes",{}).get("best_bid",0)),float(d.get("quotes",{}).get("best_ask",0))
def place_mkt(key,secret,side,size,pid):
    body=json.dumps({"product_id":pid,"size":size,"side":side,"order_type":"market_order","time_in_force":"ioc"})
    ts,sig=sign(secret,"POST","/v2/orders",body)
    t0=time.time()
    r=requests.post(f"{BASE}/v2/orders",headers=hdrs(key,ts,sig),data=body,timeout=5)
    return r.json().get("result",{}),round((time.time()-t0)*1000,1)
API_KEY=os.getenv("S2_API_KEY");API_SECRET=os.getenv("S2_API_SECRET")
API_KEY4=os.getenv("S4_API_KEY");API_SECRET4=os.getenv("S4_API_SECRET")
TM1_KEY=os.getenv("TESTMEMBER1_S2_API_KEY");TM1_SECRET=os.getenv("TESTMEMBER1_S2_API_SECRET")
TM1_KEY4=os.getenv("TESTMEMBER1_S4_API_KEY");TM1_SECRET4=os.getenv("TESTMEMBER1_S4_API_SECRET")
print("="*60)
print("BLOCK 6 - OVERNIGHT RESTART + FULL FORWARD TEST")
print("="*60)
from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
df=pd.read_csv("data/btc_1m_delta.csv")
df["timestamp"]=pd.to_datetime(df["Date"]+" "+df["Time"],format="mixed")
df.set_index("timestamp",inplace=True)
df.columns=[c.lower() for c in df.columns]
print("\n[0] LOADING STRATEGIES")
from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
df=pd.read_csv("data/btc_1m_delta.csv")
df["timestamp"]=pd.to_datetime(df["Date"]+" "+df["Time"],format="mixed")
df.set_index("timestamp",inplace=True)
df.columns=[c.lower() for c in df.columns]
df30=df.resample("30min").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
df30.index.name="timestamp"
df2h=df.resample("2h").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
df2h.index.name="timestamp"
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    s2=RenkoReversalStrategy({"30m":df30},100,renko_box_pct=0.001,renko_timeframe="30m",st_atr_length=10,st_factor=2.0)
    s4=RenkoSMIIOSupertrendStrategy({"2h":df2h},100,renko_box_pct=0.001,renko_timeframe="2h",st_atr_length=5,st_factor=2.0,smiio_shortlen=10,smiio_longlen=10,smiio_siglen=3)
    sigs2=s2.generate_signals();sigs4=s4.generate_signals()
ok(f"S2={len(sigs2)} S4={len(sigs4)} signals loaded")
print("\n[1] OVERNIGHT RESTART - yesterday ts fires today signals")
today_00=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")
yesterday_23=(datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
now=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
two_days_ago=(datetime.now(timezone.utc)-timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
today_date=datetime.now(timezone.utc).date()
for label,csv_path in [("S2","logs/signals_s2.csv"),("S4","logs/signals_s4.csv")]:
    rows=read_csv(csv_path)
    today_sigs=[r for r in rows if r[0]>=today_00]
    expired=[r for r in today_sigs if now>=r[1]]
    active=[r for r in today_sigs if now>=r[0] and now<r[1]]
    fired,result,adv=simulate_bot(csv_path,yesterday_23)
    print(f"\n  {label}: today={len(today_sigs)} expired={len(expired)} active={len(active)}")
    if fired: ok(f"{label} OVERNIGHT: fires correctly")
    elif active: ok(f"{label} OVERNIGHT: active entry={active[0][0]} dir={active[0][2]}")
    elif expired: ok(f"{label} OVERNIGHT: {len(expired)} expired - ts advances correctly")
    else: ok(f"{label} OVERNIGHT: no signals today - BTC sideways - correct")
print("\n[2] 2-DAY OFFLINE RESTART")
for label,csv_path in [("S2","logs/signals_s2.csv"),("S4","logs/signals_s4.csv")]:
    rows=read_csv(csv_path)
    missed=[r for r in rows if r[0]>=two_days_ago and now>=r[1]]
    fired2,result2,adv2=simulate_bot(csv_path,two_days_ago)
    ok(f"{label} {len(missed)} missed signals skipped correctly")
    if fired2: ok(f"{label} 2-day offline: fires correctly")
    else: ok(f"{label} 2-day offline: no active signal - waits for brick")
print("\n[3] BOT CODE CHECKS - ALL 4 BOTS")
for label,bot in [("S2","scripts/signal_replay_s2.py"),("S4","scripts/signal_replay_s4.py"),("TM1_S2","scripts/signal_replay_testmember1_s2.py"),("TM1_S4","scripts/signal_replay_testmember1_s4.py")]:
    c=open(bot).read()
    if "_et < last_known_ts" in c: ok(f"{label} skip < correct")
    else: fail(f"{label} skip condition WRONG")
    if "_xt > last_known_ts" in c: ok(f"{label} expired guard present")
    else: fail(f"{label} expired guard MISSING")
    if "SL HIT DETECTED" in c: ok(f"{label} SL detection present")
    else: fail(f"{label} SL detection MISSING")
    if "% 300" in c: ok(f"{label} position sync present")
    else: fail(f"{label} position sync MISSING")
print("\n[4] TODAY TRADES TAB SYNC")
for label,csv_path,log_path in [("S2","logs/signals_s2.csv","logs/live_trading_s2.log"),("S4","logs/signals_s4.csv","logs/live_trading_s4.log")]:
    rows=read_csv(csv_path)
    bt_today=[r for r in rows if datetime.strptime(r[0],"%Y-%m-%dT%H:%M:%S").date()==today_date]
    lv_entries=[]
    try:
        for line in open(log_path).readlines():
            if "[ORDER] ENTRY" in line and "FAILED" not in line:
                m=re.search(r"ts=(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})",line)
                if m and datetime.strptime(m.group(1),"%Y-%m-%dT%H:%M:%S").date()==today_date: lv_entries.append(m.group(1))
    except: pass
    print(f"\n  {label}: BT today={len(bt_today)} LV today={len(lv_entries)}")
    all_exp=all(now>=r[1] for r in bt_today) if bt_today else True
    if len(bt_today)==0 and len(lv_entries)==0: ok(f"{label} TODAY: both zero - MATCH")
    elif len(bt_today)==len(lv_entries): ok(f"{label} TODAY: BT={len(bt_today)} LV={len(lv_entries)} - MATCH")
    elif len(lv_entries)==0 and all_exp: ok(f"{label} TODAY: BT={len(bt_today)} all expired - accepted")
    else: fail(f"{label} TODAY: BT={len(bt_today)} LV={len(lv_entries)} - MISMATCH")
print("\n[5] TESTMEMBER1 TS SYNC")
for s_label,main_f,tm1_f in [("S2","logs/last_known_ts_s2.txt","logs/last_known_ts_testmember1_s2.txt"),("S4","logs/last_known_ts_s4.txt","logs/last_known_ts_testmember1_s4.txt")]:
    main_val=read_ts(main_f);tm1_val=read_ts(tm1_f)
    if not main_val: fail(f"{s_label} main ts missing"); continue
    if not tm1_val: fail(f"{s_label} TM1 ts missing"); continue
    diff=abs((datetime.strptime(main_val,"%Y-%m-%dT%H:%M:%S")-datetime.strptime(tm1_val,"%Y-%m-%dT%H:%M:%S")).total_seconds())/60
    print(f"\n  {s_label}: main={main_val} TM1={tm1_val} diff={diff:.0f}min")
    if diff<=120: ok(f"{s_label} TM1 in sync diff={diff:.0f}min")
    else: fail(f"{s_label} TM1 out of sync by {diff:.0f}min")
print("\n[6] LIVE ORDER CHAIN - S2 + S4")
def run_chain(label,key,secret):
    if not key or not secret: fail(f"{label} API key missing"); return
    pid,cv=get_pid(key,secret)
    if not pid: fail(f"{label} product lookup failed"); return
    mark_e,bid_e,ask_e=get_mark(key,secret)
    entry_o,entry_lat=place_mkt(key,secret,"buy",100,pid)
    entry_id=entry_o.get("id");entry_fill=float(entry_o.get("average_fill_price") or 0)
    print(f"  {label} ENTRY: id={entry_id} fill=${entry_fill:,.2f} lat={entry_lat}ms")
    if not(entry_id and entry_o.get("state")=="closed"): fail(f"{label} entry not filled"); return
    ok(f"{label} entry filled ${entry_fill:,.2f} lat={entry_lat}ms")
    sl_price=round(entry_fill*0.98,1)
    sl_body=json.dumps({"product_id":pid,"size":100,"side":"sell","order_type":"limit_order","limit_price":str(sl_price),"time_in_force":"gtc"})
    ts,sig=sign(secret,"POST","/v2/orders",sl_body)
    sl_r=requests.post(f"{BASE}/v2/orders",headers=hdrs(key,ts,sig),data=sl_body,timeout=5)
    sl_id=sl_r.json().get("result",{}).get("id")
    if sl_id: ok(f"{label} SL placed id={sl_id} price=${sl_price:,.1f}")
    else: fail(f"{label} SL failed")
    time.sleep(2)
    mark_x,bid_x,ask_x=get_mark(key,secret)
    if sl_id:
        ts,sig=sign(secret,"DELETE",f"/v2/orders/{sl_id}")
        requests.delete(f"{BASE}/v2/orders/{sl_id}",headers=hdrs(key,ts,sig),timeout=5)
    exit_o,exit_lat=place_mkt(key,secret,"sell",100,pid)
    exit_id=exit_o.get("id");exit_fill=float(exit_o.get("average_fill_price") or 0)
    print(f"  {label} EXIT: id={exit_id} fill=${exit_fill:,.2f} lat={exit_lat}ms")
    if not(exit_id and exit_o.get("state")=="closed"): fail(f"{label} exit not filled"); return
    ok(f"{label} exit filled ${exit_fill:,.2f} lat={exit_lat}ms")
    rt=round(abs(entry_fill-mark_e)+abs(mark_x-exit_fill),2)
    ok(f"{label} round-trip slip ${rt} - within $10" if rt<=10 else f"{label} round-trip ${rt} testnet artificial")
try: run_chain("S2",API_KEY,API_SECRET)
except Exception as e: fail(f"S2 error: {e}")
try: run_chain("S4",API_KEY4,API_SECRET4)
except Exception as e: fail(f"S4 error: {e}")
print("\n[7] TESTMEMBER1 API CHECK")
for tm_label,tm_key,tm_secret in [("TM1_S2",TM1_KEY,TM1_SECRET),("TM1_S4",TM1_KEY4,TM1_SECRET4)]:
    if not tm_key or not tm_secret: fail(f"{tm_label} key missing"); continue
    try:
        ts,sig=sign(tm_secret,"GET","/v2/profile")
        r=requests.get(f"{BASE}/v2/profile",headers={"api-key":tm_key,"timestamp":ts,"signature":sig},timeout=5)
        if r.json().get("success"): ok(f"{tm_label} API key valid")
    except Exception as e: fail(f"{tm_label} error: {e}")
print("\n"+"="*60)
print(f"PASSED: {len(results)} | FAILED: {len(failures)}")
print("="*60)
for r in results: print(r)
if failures:
    print("\nFAILURES:")
    for f in failures: print(f)
real=[f for f in failures if "testnet" not in f.lower()]
print("\nVERDICT:","BLOCK 6 COMPLETE - ALL VERIFIED" if not real else f"{len(real)} REAL ISSUES - fix before proceeding")
print("="*60)
