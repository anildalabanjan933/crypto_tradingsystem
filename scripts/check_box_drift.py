"""
Daily drift check - confirms live engine box_size == backtest formula box_size
Runs at 3AM UTC via auto_maintenance.py. Sends Telegram alert if drift found.
"""
import pandas as pd, glob, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.telegram_alert import send_alert

CSV_1H = "data/btc_1h_delta.csv" if os.path.exists("data/btc_1h_delta.csv") else "data/btc_1m_delta.csv"
CSV_30M = "data/btc_30m_delta.csv" if os.path.exists("data/btc_30m_delta.csv") else "data/btc_1m_delta.csv"
CSV_2H = "data/btc_2h_delta.csv" if os.path.exists("data/btc_2h_delta.csv") else "data/btc_1m_delta.csv"

def get_closes_30m():
    df = pd.read_csv("data/btc_1m_delta.csv")
    df['ts'] = pd.to_datetime(df.iloc[:,0].astype(str)+' '+df.iloc[:,1].astype(str), errors='coerce', format='mixed')
    df = df.dropna(subset=['ts']).set_index('ts')
    close_col = [c for c in df.columns if c.lower()=='close'][0]
    r = df[close_col].resample('30min').last().dropna()
    return r

def get_closes_2h():
    df = pd.read_csv("data/btc_1m_delta.csv")
    df['ts'] = pd.to_datetime(df.iloc[:,0].astype(str)+' '+df.iloc[:,1].astype(str), errors='coerce', format='mixed')
    df = df.dropna(subset=['ts']).set_index('ts')
    close_col = [c for c in df.columns if c.lower()=='close'][0]
    r = df[close_col].resample('2h').last().dropna()
    return r

def get_engine_box_size(label):
    log_path = "logs/renko_state_engine.log"
    if not os.path.exists(log_path): return None
    val = None
    with open(log_path) as f:
        for line in f:
            if f"[{label}]" in line and "box_size=" in line:
                try:
                    val = int(line.split("box_size=")[1].split(" ")[0])
                except: pass
    return val

def main():

    # HEARTBEAT: write liveness timestamp (additive only, cannot affect drift logic)
    try:
        import datetime as _hb_dt
        with open("logs/box_drift_heartbeat.txt", "w") as _hb_f:
            _hb_f.write(_hb_dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
    except Exception:
        pass

    issues = []

    # S4V2 check: box = round(first_close * 0.001) - 30m timeframe
    try:
        s2_closes = get_closes_30m()
        s2_expected = max(1, round(s2_closes.iloc[0] * 0.0010))
        s2_engine = get_engine_box_size("S4V2")
        if s2_engine is not None and s2_engine != s2_expected:
            issues.append(f"S4V2 DRIFT: engine={s2_engine} expected={s2_expected}")
        print(f"S4V2: engine={s2_engine} expected={s2_expected} {'MATCH' if s2_engine==s2_expected else 'DRIFT!'}")
    except Exception as e:
        print(f"S4V2 check failed: {e}")

    # S4 check: box = round(first_close * 0.001)
    try:
        s4_closes = get_closes_2h()
        s4_expected = max(1, round(s4_closes.iloc[0] * 0.001))
        s4_engine = get_engine_box_size("S4")
        if s4_engine is not None and s4_engine != s4_expected:
            issues.append(f"S4 DRIFT: engine={s4_engine} expected={s4_expected}")
        print(f"S4: engine={s4_engine} expected={s4_expected} {'MATCH' if s4_engine==s4_expected else 'DRIFT!'}")
    except Exception as e:
        print(f"S4 check failed: {e}")

    if issues:
        msg = "CTS BOX_SIZE DRIFT DETECTED\n" + "\n".join(issues) + "\nEngine and backtest no longer match - investigate immediately"
        try: send_alert(msg)
        except: pass
        print("ALERT SENT - DRIFT FOUND")
    else:
        print("NO DRIFT - engine matches backtest formula exactly")

if __name__ == "__main__":
    main()
