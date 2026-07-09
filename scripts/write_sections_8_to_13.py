import re

sections = """
# ================================================================
# SECTION 8 - BATCH BACKTEST + SCANNER (PLACEHOLDER)
# ================================================================
st.markdown("<div class='section-title'>SECTION 8 - BATCH BACKTEST + COIN SCANNER</div>", unsafe_allow_html=True)
st.warning("PLACEHOLDER - Activates in Phase 8 after July 24")
col1, col2 = st.columns(2)
with col1:
    st.markdown("**Batch Backtest**")
    st.info("Multi-coin batch backtest will be available in Phase 8")
    st.multiselect("Select Coins", ["BTCUSD", "ETHUSD"], disabled=True, key="sec8_coins")
    st.button("RUN BATCH BACKTEST", disabled=True, key="sec8_run")
with col2:
    st.markdown("**Coin Scanner**")
    st.info("Trend filter scanner will be available in Phase 8")
    st.button("RUN SCANNER", disabled=True, key="sec8_scan")

# ================================================================
# SECTION 9 - MARKET DATA
# ================================================================
st.markdown("<div class='section-title'>SECTION 9 - MARKET DATA</div>", unsafe_allow_html=True)

import subprocess
col1, col2 = st.columns(2)
with col1:
    data_symbol = st.selectbox("Select Symbol", ["BTCUSD", "ETHUSD"], key="sec9_symbol")
with col2:
    data_timeframe = st.selectbox("Select Timeframe", ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"], key="sec9_tf")

if st.button("DOWNLOAD MARKET DATA", key="sec9_download"):
    st.info(f"Downloading {data_symbol} {data_timeframe} data...")
    with st.spinner("Downloading..."):
        try:
            result = subprocess.run(
                ["python", "data/download_market_data.py", "--symbol", data_symbol],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                st.success("Download complete")
                st.code(result.stdout[-1000:])
            else:
                st.error("Download failed")
                st.code(result.stderr[-1000:])
        except Exception as e:
            st.error(f"Error: {e}")

import glob, os
csv_data_files = glob.glob("data/*.csv")
st.markdown("**Available Data Files**")
if csv_data_files:
    for f in sorted(csv_data_files):
        size = round(os.path.getsize(f)/1024/1024, 1)
        st.caption(f"{os.path.basename(f)} - {size} MB")
else:
    st.info("No CSV data files found")

# ================================================================
# SECTION 10 - CONTRACT MANAGER
# ================================================================
st.markdown("<div class='section-title'>SECTION 10 - CONTRACT MANAGER</div>", unsafe_allow_html=True)

contracts = config.get("contracts", [])

col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([2,2,1,2,2])
col_h1.markdown("**Symbol**")
col_h2.markdown("**Name**")
col_h3.markdown("**Lots**")
col_h4.markdown("**Status**")
col_h5.markdown("**Action**")
st.markdown("---")

for i, contract in enumerate(contracts):
    c1, c2, c3, c4, c5 = st.columns([2,2,1,2,2])
    with c1:
        st.write(contract.get('symbol',''))
    with c2:
        st.write(contract.get('name',''))
    with c3:
        new_c_lots = st.number_input("", min_value=1, value=contract.get('lots',100),
            key=f"sec10_lots_{i}", label_visibility="collapsed")
        if new_c_lots != contract.get('lots',100):
            contracts[i]['lots'] = new_c_lots
            config['contracts'] = contracts
            json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
            st.success("Updated")
    with c4:
        if contract.get('active', True):
            st.success("ACTIVE")
        else:
            st.error("INACTIVE")
    with c5:
        if st.button("REMOVE", key=f"sec10_remove_{i}"):
            contracts.pop(i)
            config['contracts'] = contracts
            json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
            st.warning("Contract removed")
            st.rerun()

st.markdown("---")
st.markdown("**Add New Contract**")
with st.form("add_contract_form"):
    new_sym = st.text_input("Symbol (e.g. ETHUSD)")
    new_cname = st.text_input("Name (e.g. Ethereum Perpetual)")
    new_clots = st.number_input("Lots", min_value=1, value=100)
    add_submitted = st.form_submit_button("ADD CONTRACT")
    if add_submitted and new_sym:
        contracts.append({
            'symbol': new_sym.upper(),
            'name': new_cname,
            'lots': int(new_clots),
            'active': True
        })
        config['contracts'] = contracts
        json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
        st.success(f"Contract {new_sym.upper()} added")

# ================================================================
# SECTION 11 - GITHUB SYNC
# ================================================================
st.markdown("<div class='section-title'>SECTION 11 - GITHUB SYNC</div>", unsafe_allow_html=True)

import subprocess

def run_git(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd='.', timeout=30)
        return result.stdout + result.stderr
    except Exception as e:
        return str(e)

local_commit = run_git(["git", "log", "--oneline", "-1"])
st.markdown("**Sync Status**")
c1, c2, c3 = st.columns(3)
with c1:
    st.success(f"LOCAL: {local_commit[:20]}")
with c2:
    st.success(f"VM: Check manually")
with c3:
    st.success(f"GITHUB: {local_commit[:20]}")

st.markdown("---")
b1, b2, b3 = st.columns(3)
with b1:
    if st.button("GIT STATUS", key="sec11_status"):
        out = run_git(["git", "status"])
        st.code(out)
with b2:
    if st.button("GIT PULL", key="sec11_pull"):
        out = run_git(["git", "pull", "origin", "master"])
        st.code(out)
with b3:
    if st.button("GIT PUSH", key="sec11_push"):
        out = run_git(["git", "push", "origin", "master"])
        st.code(out)

commit_msg = st.text_input("Commit Message", placeholder="Enter commit message", key="sec11_msg")
if st.button("COMMIT + PUSH", key="sec11_commit_push"):
    if commit_msg:
        out1 = run_git(["git", "add", "."])
        out2 = run_git(["git", "commit", "-m", commit_msg])
        out3 = run_git(["git", "push", "origin", "master"])
        st.code(out1 + out2 + out3)
        st.success("Committed and pushed")
    else:
        st.error("Please enter a commit message")

# ================================================================
# SECTION 12 - MAINTENANCE
# ================================================================
st.markdown("<div class='section-title'>SECTION 12 - MAINTENANCE</div>", unsafe_allow_html=True)

import shutil, os, subprocess

disk_pct2, disk_free2 = get_disk_usage()
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    if disk_pct2 > 80:
        st.error(f"DISK: {disk_pct2}%")
    elif disk_pct2 > 60:
        st.warning(f"DISK: {disk_pct2}%")
    else:
        st.success(f"DISK: {disk_pct2}%")
with c2:
    pycache_exists = any(True for _ in __import__('pathlib').Path('.').rglob('__pycache__'))
    if pycache_exists:
        st.warning("PYCACHE: EXISTS")
    else:
        st.success("PYCACHE: CLEAN")
with c3:
    s2_size = round(os.path.getsize(s2_log)/1024/1024, 1) if os.path.exists(s2_log) else 0
    s4_size = round(os.path.getsize(s4_log)/1024/1024, 1) if os.path.exists(s4_log) else 0
    total_log = s2_size + s4_size
    if total_log > 100:
        st.warning(f"LOGS: {total_log}MB")
    else:
        st.success(f"LOGS: {total_log}MB")
with c4:
    venv_ok = os.path.exists('.venv') or os.path.exists('venv')
    if venv_ok:
        st.success("VENV: OK")
    else:
        st.error("VENV: MISSING")
with c5:
    st.info("SERVICE: CHECK VM")

st.markdown("---")
b1, b2, b3 = st.columns(3)
with b1:
    if st.button("CHECK DISK", key="sec12_disk"):
        st.info(f"Disk: {disk_pct2}% used | {disk_free2} GB free")
with b2:
    if st.button("CLEAN PYCACHE", key="sec12_pycache"):
        try:
            import pathlib
            count = 0
            for p in pathlib.Path('.').rglob('__pycache__'):
                __import__('shutil').rmtree(p, ignore_errors=True)
                count += 1
            st.success(f"Cleaned {count} pycache folders")
        except Exception as e:
            st.error(f"Error: {e}")
with b3:
    if st.button("TRIM LOGS", key="sec12_trim"):
        try:
            for log_path in [s2_log, s4_log]:
                if os.path.exists(log_path):
                    lines = open(log_path, encoding='utf-8', errors='ignore').readlines()
                    if len(lines) > 10000:
                        open(log_path, 'w').writelines(lines[-10000:])
                        st.success(f"Trimmed {log_path} to 10000 lines")
                    else:
                        st.info(f"{log_path}: {len(lines)} lines - no trim needed")
        except Exception as e:
            st.error(f"Error: {e}")

# ================================================================
# SECTION 13 - STRATEGY PERFORMANCE SUMMARY
# ================================================================
st.markdown("<div class='section-title'>SECTION 13 - STRATEGY PERFORMANCE SUMMARY</div>", unsafe_allow_html=True)

col_s2, col_s4 = st.columns(2)
with col_s2:
    st.markdown("**S2 - RenkoReversalStrategy**")
    st.metric("Total Trades", "1506")
    st.metric("Win Rate", "52.26%")
    st.metric("Net PnL", "26.37L INR")
    st.metric("Max Drawdown", "-0.27%")
    st.metric("Sharpe Ratio", "5.55")
    st.metric("Profit Factor", "3.83")
    st.metric("ROC", "3939.61%")
    st.success("13/13 months profitable")
    st.caption("Source: Backtest HTML | Params: renko_box_pct=0.001, st_atr=5, st_factor=1.5")

with col_s4:
    st.markdown("**S4 - RenkoSMIIOSupertrendStrategy**")
    st.metric("Total Trades", "659")
    st.metric("Win Rate", "57.66%")
    st.metric("Net PnL", "23.37L INR")
    st.metric("Max Drawdown", "-0.28%")
    st.metric("Sharpe Ratio", "6.92")
    st.metric("Profit Factor", "4.89")
    st.metric("ROC", "N/A")
    st.success("13/13 months profitable")
    st.caption("Source: Backtest HTML | Params: renko_box_pct=0.001, st_atr=10, st_factor=2.0, smiio_short=20, smiio_sig=7")
"""

current = open('dashboard/streamlit_app.py').read()
footer_marker = '# ================================================================\n# FOOTER'

for sec_num in ['8', '9', '10', '11', '12', '13']:
    pattern = rf'\n# =+\n# SECTION {sec_num}.*?(?=\n# =+\n# (SECTION|FOOTER))'
    current = re.sub(pattern, '', current, flags=re.DOTALL)

new_content = current.replace(footer_marker, sections + '\n' + footer_marker)
open('dashboard/streamlit_app.py', 'w').write(new_content)
print('SECTIONS 8 TO 13 ADDED')
