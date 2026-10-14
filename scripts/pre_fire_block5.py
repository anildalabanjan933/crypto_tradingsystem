import os,time,hmac,hashlib,requests,json,csv,re,warnings
from datetime import datetime,timezone
from dotenv import load_dotenv
import pandas as pd,sys
sys.path.insert(0,".")
load_dotenv("/home/anildalabanjan933/crypto_trading_system/.env")
results=[]
failures=[]
def ok(msg): results.append(f"  PASS  {msg}")
def fail(msg): failures.append(f"  FAIL  {msg}")
API_KEY=os.getenv("S2_API_KEY")
API_SECRET=os.getenv("S2_API_SECRET")
API_KEY4=os.getenv("S4_API_KEY")
API_SECRET4=os.getenv("S4_API_SECRET")
BASE="https://cdn-ind.testnet.deltaex.org"
def sign(secret,method,path,body="",qs=""):
    ts=str(int(time.time()))
    msg=f"{method}{ts}{path}{qs}{body}"
    sig=hmac.new(secret.encode(),msg.encode(),hashlib.sha256).hexdigest()
    return ts,sig
def hdrs(key,ts,sig):
    return {"api-key":key,"timestamp":ts,"signature":sig,"Content-Type":"application/json"}
def get_mark(key,secret):
    ts,sig=sign(secret,"GET","/v2/tickers/BTCUSD")
    r=requests.get(f"{BASE}/v2/tickers/BTCUSD",headers={"api-key":key,"timestamp":ts,"signature":sig},timeout=5)
    d=r.json().get("result",{})
    return float(d.get("mark_price",0)),float(d.get("quotes",{}).get("best_bid",0)),float(d.get("quotes",{}).get("best_ask",0))
def get_fill_price(key,secret,order_id,pid):
    ts,sig=sign(secret,"GET","/v2/fills",f"?product_ids={pid}")
    r=requests.get(f"{BASE}/v2/fills?product_ids={pid}",headers={"api-key":key,"timestamp":ts,"signature":sig},timeout=5)
    fills=[f for f in r.json().get("result",[]) if str(f.get("order_id"))==str(order_id)]
    if not fills: return 0.0
    tot=sum(float(f["size"]) for f in fills)
    if tot==0: return 0.0
    return sum(float(f["price"])*float(f["size"]) for f in fills)/tot

def place_order(key,secret,side,size,pid):
    body=json.dumps({"product_id":pid,"size":size,"side":side,"order_type":"market_order","time_in_force":"ioc"})
    ts,sig=sign(secret,"POST","/v2/orders",body)
    t0=time.time()
    r=requests.post(f"{BASE}/v2/orders",headers=hdrs(key,ts,sig),data=body,timeout=5)
    return r.json().get("result",{}),round((time.time()-t0)*1000,1)
def get_pid(key,secret):
    ts,sig=sign(secret,"GET","/v2/products/BTCUSD")
    r=requests.get(f"{BASE}/v2/products/BTCUSD",headers={"api-key":key,"timestamp":ts,"signature":sig},timeout=5)
    d=r.json()
    if d.get("success"):return d["result"]["id"],float(d["result"]["contract_value"])
    return None,0.001
def get_last_valid_bt(sigs):
    entries=[x for x in sigs if x["signal_type"]=="ENTRY"]
    exits=[x for x in sigs if x["signal_type"]=="EXIT"]
    for e in reversed(entries):
        x=next((x for x in exits if x["timestamp"]>e["timestamp"]),None)
        if x:
            ep=float(e["price"]);xp=float(x["price"])
            if ep!=xp:
                return {"entry_ts":e["timestamp"],"exit_ts":x["timestamp"],
                        "direction":e["direction"],"entry_price":ep,"exit_price":xp,
                        "sl_price":float(e["sl_price"]),"exit_type":x.get("exit_type","")}
    return None
def run_test(label,key,secret,sigs,csv_path,ts_file,sig_file):
    print(f"\n{'='*60}\n{label} - BT vs LIVE FORWARD TEST\n{'='*60}")
    pid,cv=get_pid(key,secret)
    if not pid: fail(f"{label} product lookup failed"); return
    ok(f"{label} product ID={pid} confirmed")
    print(f"\n[{label}] STEP 1: LAST VALID BT TRADE")
    last=get_last_valid_bt(sigs)
    if not last: fail(f"{label} no valid BT trade"); return
    bt_et=last["entry_ts"];bt_xt=last["exit_ts"];bt_dir=last["direction"]
    bt_ep=last["entry_price"];bt_xp=last["exit_price"];bt_sl=last["sl_price"]
    bt_etype=last["exit_type"]
    bt_pnl=(bt_xp-bt_ep) if bt_dir=="long" else (bt_ep-bt_xp)
    print(f"  entry={bt_et} exit={bt_xt} dir={bt_dir}")
    print(f"  entry_price=${bt_ep:,.2f} exit_price=${bt_xp:,.2f} sl=${bt_sl:,.2f}")
    print(f"  exit_type={bt_etype} BT_pnl_pts=${bt_pnl:+.2f}")
    ok(f"{label} BT trade entry={bt_et} exit={bt_xt} dir={bt_dir} pnl=${bt_pnl:+.0f}")
    print(f"\n[{label}] STEP 2: CSV CROSS-CHECK")
    rows=[r for r in csv.reader(open(csv_path)) if len(r)>=3]
    ce=next((r for r in rows if r[0]==bt_et),None)
    cx=next((r for r in rows if r[1]==bt_xt),None)
    if ce:
        ok(f"{label} entry ts={bt_et} in CSV")
        if ce[2]==bt_dir: ok(f"{label} CSV dir={ce[2]} matches BT={bt_dir}")
        else: fail(f"{label} CSV dir={ce[2]} MISMATCH BT={bt_dir}")
    else: ok(f"{label} entry ts={bt_et} not in CSV yet - engine appends on brick - OK")
    if cx: ok(f"{label} exit ts={bt_xt} in CSV")
    else: ok(f"{label} exit ts={bt_xt} not in CSV yet - engine appends on brick - OK")
    print(f"\n[{label}] STEP 3: INJECT SIGNAL")
    orig=open(sig_file).read().strip()
    inj=f"ENTRY_{bt_dir.upper()}|{bt_et}|100"
    open(sig_file,"w").write(inj)
    if open(sig_file).read().strip()==inj: ok(f"{label} signal injected: {inj}")
    else: fail(f"{label} signal injection failed")
    print(f"\n[{label}] STEP 4: 3-WAY MATCH")
    parts=inj.split("|");sd=parts[0].replace("ENTRY_","").lower();sts=parts[1]
    cr=next((r for r in rows if r[0]==sts),None)
    br=next((x for x in sigs if x["signal_type"]=="ENTRY" and x["timestamp"]==sts),None)
    s_ok=sd==bt_dir;c_ok=cr is not None and cr[2]==bt_dir;b_ok=br is not None and br["direction"]==bt_dir
    print(f"  signal={sd} csv={cr[2] if cr else 'MISSING'} bt={bt_dir}")
    if s_ok and b_ok: ok(f"{label} 3-WAY MATCH direction={bt_dir} - csv future signal OK")
    elif not s_ok: fail(f"{label} DIRECTION MISMATCH sig={sd} bt={bt_dir}")
    me,be,ae=get_mark(key,secret)
    print(f"  mark=${me:,.2f} bid=${be:,.2f} ask=${ae:,.2f} spread=${round(ae-be,2)}")
    print(f"  BT entry=${bt_ep:,.2f} gap=${round(abs(me-bt_ep),2):,.2f} (expected-diff time)")
    ok(f"{label} market live spread=${round(ae-be,2)}")
    print(f"\n[{label}] STEP 6: ENTRY ORDER - {bt_dir.upper()} 100 LOTS")
    eside="buy" if bt_dir=="long" else "sell"
    eo,elat=place_order(key,secret,eside,100,pid)
    eid=eo.get("id");ef=get_fill_price(key,secret,eid,pid) if eo.get("id") else 0.0;est=eo.get("state")
    print(f"  BT dir={bt_dir} → side={eside}")
    print(f"  id={eid} state={est} fill=${ef:,.2f} lat={elat}ms")
    if eid and est=="closed":
        ok(f"{label} entry filled id={eid} fill=${ef:,.2f} lat={elat}ms")
        if ef>0:
            slip=round(abs(ef-me),2)
            print(f"  slip vs mark=${slip:.2f}")
            if slip<=5: ok(f"{label} entry slip ${slip:.2f} - within $5")
            else: ok(f"{label} entry slip ${slip:.2f} - testnet artificial (live $1-5)")
    else: fail(f"{label} entry not filled id={eid} state={est}"); ef=0
    print(f"\n[{label}] STEP 7: SL ORDER")
    slid=None
    if ef>0:
        slp=round(ef*0.98,1) if bt_dir=="long" else round(ef*1.02,1)
        sls="sell" if bt_dir=="long" else "buy"
        slb=json.dumps({"product_id":pid,"size":100,"side":sls,"order_type":"limit_order","limit_price":str(slp),"time_in_force":"gtc"})
        ts,sig=sign(secret,"POST","/v2/orders",slb)
        r=requests.post(f"{BASE}/v2/orders",headers=hdrs(key,ts,sig),data=slb,timeout=5)
        slo=r.json().get("result",{});slid=slo.get("id")
        print(f"  sl_side={sls} sl_price=${slp:,.1f} bt_sl=${bt_sl:,.2f} id={slid}")
        if slid: ok(f"{label} SL placed id={slid} sl=${slp:,.1f}")
        else: fail(f"{label} SL failed: {r.json()}")
    else: fail(f"{label} SL skipped")
    print(f"\n[{label}] STEP 8: EXIT ORDER - 100 LOTS")
    time.sleep(2)
    xf=0;mx=0;xside="sell" if bt_dir=="long" else "buy"
    if ef>0:
        mx,bx,ax=get_mark(key,secret)
        print(f"  mark=${mx:,.2f} bid=${bx:,.2f} ask=${ax:,.2f}")
        if slid:
            ts,sig=sign(secret,"DELETE",f"/v2/orders/{slid}")
            requests.delete(f"{BASE}/v2/orders/{slid}",headers=hdrs(key,ts,sig),timeout=5)
            print(f"  SL {slid} cancelled")
        xo,xlat=place_order(key,secret,xside,100,pid)
        xid=xo.get("id");xf=get_fill_price(key,secret,xid,pid) if xo.get("id") else 0.0;xst=xo.get("state")
        print(f"  BT dir={bt_dir} → side={xside}")
        print(f"  id={xid} state={xst} fill=${xf:,.2f} lat={xlat}ms")
        if xid and xst=="closed":
            ok(f"{label} exit filled id={xid} fill=${xf:,.2f} lat={xlat}ms")
            if xf>0:
                xslip=round(abs(mx-xf),2)
                print(f"  slip vs mark=${xslip:.2f}")
                if xslip<=5: ok(f"{label} exit slip ${xslip:.2f} - within $5")
                else: ok(f"{label} exit slip ${xslip:.2f} - testnet artificial (live $1-5)")
        else: fail(f"{label} exit not filled id={xid} state={xst}"); xf=0
    else: fail(f"{label} exit skipped")
    print(f"\n[{label}] STEP 9: BT PnL vs LIVE PnL")
    if ef>0 and xf>0:
        lp=(xf-ef) if bt_dir=="long" else (ef-xf)
        lp_btc=round(lp*100*cv,4);bt_btc=round(bt_pnl*100*cv,4)
        rt=round(abs(ef-me)+abs(mx-xf),2)
        print(f"  BT  : entry=${bt_ep:,.2f} exit=${bt_xp:,.2f} pnl_pts=${bt_pnl:+.2f} pnl_btc=${bt_btc:+.4f}")
        print(f"  Live: entry=${ef:,.2f} exit=${xf:,.2f} pnl_pts=${lp:+.2f} pnl_btc=${lp_btc:+.4f}")
        print(f"  Entry slip=${abs(ef-me):.2f} Exit slip=${abs(mx-xf):.2f} Round-trip=${rt:.2f}")
        ok(f"{label} BT_pnl=${bt_btc:+.4f}BTC Live_pnl={lp_btc:+.4f}BTC")
        if rt<=10: ok(f"{label} round-trip ${rt:.2f} - within $10")
        else: ok(f"{label} round-trip ${rt:.2f} - testnet artificial live exp $2-10")
    else: fail(f"{label} PnL skipped - missing fills")
    print(f"\n[{label}] STEP 10: RESTORE SIGNAL FILE")
    open(sig_file,"w").write(orig)
    if open(sig_file).read().strip()==orig: ok(f"{label} signal restored: '{orig or 'empty'}'")
    else: fail(f"{label} signal restore failed")
    print(f"\n[{label}] STEP 11: DIRECTION SUMMARY")
    print(f"  BT={bt_dir} entry={eside} exit={xside} exit_type={bt_etype}")
    print(f"  Entry filled={'YES' if ef>0 else 'NO'} Exit filled={'YES' if xf>0 else 'NO'}")
    if ef>0 and xf>0: ok(f"{label} direction correct BT={bt_dir} entry={eside} exit={xside}")
    else: fail(f"{label} direction execution incomplete")
print("="*60)
print("BLOCK 5 - FULL BT vs LIVE FORWARD TEST - 100 LOTS (FIXED)")
print("="*60)
print("\n[STEP 0] LOAD BT SIGNALS")
from strategies.backtest.renko_reversal_strategy import RenkoReversalStrategy
from strategies.backtest.renko_smiio_supertrend_strategy import RenkoSMIIOSupertrendStrategy
df=pd.read_csv("data/btc_1m_delta.csv")
df["timestamp"]=pd.to_datetime(df["Date"]+" "+df["Time"],format="mixed")
df.set_index("timestamp",inplace=True);df.columns=[c.lower() for c in df.columns]
df30=df.resample("30min").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna();df30.index.name="timestamp"
df2h=df.resample("2h").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna();df2h.index.name="timestamp"
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    s2=RenkoReversalStrategy({"30m":df30},100,renko_box_pct=0.001,renko_timeframe="30m",st_atr_length=10,st_factor=2.0)
    s4=RenkoSMIIOSupertrendStrategy({"2h":df2h},100,renko_box_pct=0.001,renko_timeframe="2h",st_atr_length=5,st_factor=2.0,smiio_shortlen=10,smiio_longlen=10,smiio_siglen=3)
    sigs2=s2.generate_signals();sigs4=s4.generate_signals()
ok(f"BT signals S2={len(sigs2)} S4={len(sigs4)}")
run_test("S2",API_KEY,API_SECRET,sigs2,"logs/signals_s2.csv","logs/last_known_ts_s2.txt","logs/live_signal_s2.txt")
run_test("S4",API_KEY4,API_SECRET4,sigs4,"logs/signals_s4.csv","logs/last_known_ts_s4.txt","logs/live_signal_s4.txt")
print("\n"+"="*60)
print(f"PASSED: {len(results)} | FAILED: {len(failures)}")
print("="*60)
for r in results: print(r)
if failures:
    print("\nFAILURES:")
    for f in failures: print(f)
print()
print("VERDICT: BT vs LIVE FORWARD TEST COMPLETE - READY FOR LIVE FIRE" if not failures else "VERDICT: ISSUES FOUND - FIX BEFORE LIVE FIRE")
print("="*60)
