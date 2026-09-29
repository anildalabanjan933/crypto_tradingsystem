p="scripts/renko_state_engine.py"; s=open(p).read()
def rep(old,new,n=1):
    global s
    assert s.count(old)==n,(old[:50],s.count(old)); s=s.replace(old,new)
rep('def _trim_tf(df_tf):\n    import pandas as pd\n    if df_tf is None or len(df_tf)<=TF_BAR_CAP:\n        return df_tf\n    return df_tf.sort_values("timestamp").tail(TF_BAR_CAP).reset_index(drop=True)',
    'def _trim_tf(df_tf,cap=TF_BAR_CAP):\n    import pandas as pd\n    if df_tf is None or cap is None or len(df_tf)<=cap:\n        return df_tf\n    return df_tf.sort_values("timestamp").tail(cap).reset_index(drop=True)')
rep('self.candles_tf=None  # pre-built','self.bar_cap=None if label=="S4V3" else TF_BAR_CAP\n        self.candles_tf=None  # pre-built')
rep('_trim_tf(state.candles_tf)','_trim_tf(state.candles_tf,state.bar_cap)',3)
rep('_trim_tf(resample_to_tf(df,tf))','_trim_tf(resample_to_tf(df,tf),state.bar_cap)')
rep('            new_sigs.append(sig)\n',
    '            if state.label=="S4V3" and sig.get("direction","")=="long":\n'
    '                log.critical(f"[S4V3] LONG signal ts={ts} type={sig.get(\'signal_type\')} REJECTED - BT is short-only (wrong state-machine phase)")\n'
    '                continue\n            new_sigs.append(sig)\n')
open(p,"w").write(s); print("patched")
