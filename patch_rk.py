f = "/home/anildalabanjan7/strategies_options/backtest/rk_backtest.py"
s = open(f).read()

OLD1 = '''def trigger(v, strat, basis, legs, marks):
    pnl = raw_pnl(legs, marks)'''
NEW1 = '''def exec_pnl(legs, marks):
    pnl = 0.0
    for l, m in zip(legs, marks):
        if l["role"] == "S":
            pnl += l["fill"] - m * (1 + SLIP)
        else:
            pnl += m * (1 - SLIP) - l["fill"]
    return pnl


def trigger(v, strat, basis, legs, marks):
    pnl = exec_pnl(legs, marks)'''
assert s.count(OLD1) == 1
s = s.replace(OLD1, NEW1, 1)

OLD2 = '''        res = simulate(strat, legs, basis, max(l["fill_ts"] for l in legs), spot_series, spot_px, settle_ts)
        info = " ".join(f"{l['role']}{l['type']}{l['strike']}@{l['raw']:.0f}" for l in legs)
        for v in VARIANTS:
            mode, pnl_raw, fee_raw = res[v]
            tag = f"[{gtag} {v}]"
            if pnl_raw is None:
                print(f"{tag} {exp} submode={mode} day_pnl=$0.00 fees=$0.00 equity=${accs[v].eq:.2f}")
                accs[v].skips[mode] = accs[v].skips.get(mode, 0) + 1
                continue
            net = (pnl_raw - fee_raw) * MULT
            accs[v].trade(exp, net, fee_raw * MULT)
            print(f"{tag} {exp} submode={mode} day_pnl=${net:.2f} fees=${fee_raw * MULT:.2f} "
                  f"equity=${accs[v].eq:.2f} skew={skew} {info}")'''
NEW2 = '''        res = simulate(strat, legs, basis, max(l["fill_ts"] for l in legs), spot_series, spot_px, settle_ts)
        info = " ".join(f"{l['role']}{l['type']}{l['strike']}@{l['raw']:.0f}(d={l['strike']-spot_px:+.0f})" for l in legs)
        strikes = [l["strike"] for l in legs]
        width = max(strikes) - min(strikes)
        entry_date = exp - timedelta(days=dte)
        for v in VARIANTS:
            mode, pnl_raw, fee_raw = res[v]
            tag = f"[{gtag} {v}]"
            tgt_d = (PCT[v] if v in PCT else HOST_TGT) * basis * MULT
            if v in PCT:
                sl_d = PCT[v] * basis * MULT
            elif strat == "strangle":
                sl_d = sum(l["raw"] for l in legs if l["role"] == "S") * MULT
            elif strat in ("straddle", "iron_fly") or strat in CAL_KIND:
                sl_d = HOST_SL * basis * MULT
            elif strat == "iron_condor":
                sl_d = (0.5 * ic_max_loss(legs, basis) * MULT) if IC_HOST_HALF_MAXLOSS_SL else None
            else:
                sl_d = None
            sl_disp = f"${sl_d:.2f}" if sl_d is not None else "NA"
            if pnl_raw is None:
                print(f"{tag} entry={entry_date} exp={exp} dte={dte} {info} width={width} "
                      f"sl={sl_disp} tgt=${tgt_d:.2f} submode={mode} pnl=$0.00 fees=$0.00 equity=${accs[v].eq:.2f}")
                accs[v].skips[mode] = accs[v].skips.get(mode, 0) + 1
                continue
            net = (pnl_raw - fee_raw) * MULT
            accs[v].trade(exp, net, fee_raw * MULT)
            print(f"{tag} entry={entry_date} exp={exp} dte={dte} {info} width={width} "
                  f"sl={sl_disp} tgt=${tgt_d:.2f} submode={mode} pnl=${net:.2f} fees=${fee_raw * MULT:.2f} "
                  f"equity=${accs[v].eq:.2f} skew={skew}")'''
assert s.count(OLD2) == 1
s = s.replace(OLD2, NEW2, 1)

open(f, "w").write(s)
print("PATCHED_OK")
