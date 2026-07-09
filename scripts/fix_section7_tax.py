import re

new_section7 = """
# ================================================================
# SECTION 7 - OPTIMISATION
# ================================================================
st.markdown("<div class='section-title'>SECTION 7 - OPTIMISATION</div>", unsafe_allow_html=True)

import subprocess, glob, os

col1, col2, col3 = st.columns(3)
with col1:
    opt_strategy = st.selectbox("Select Strategy", [
        "RenkoReversalStrategy",
        "RenkoSMIIOSupertrendStrategy"
    ], key="sec7_strategy")
with col2:
    opt_group = st.selectbox("Select Group", [
        "renko", "supertrend", "smiio"
    ], key="sec7_group")
with col3:
    opt_lots = st.number_input("Lots", min_value=1, max_value=10000, value=100, key="sec7_lots")

col4, col5 = st.columns(2)
with col4:
    opt_start = st.date_input("Start Date", value=datetime.date(2025, 1, 1), key="sec7_start")
with col5:
    opt_end = st.date_input("End Date", value=datetime.date.today(), key="sec7_end")

st.markdown("**Charges Configuration**")
col6, col7, col8 = st.columns(3)
with col6:
    opt_slippage = st.number_input("Slippage/side ($)", min_value=0.0, value=5.0, key="sec7_slip")
with col7:
    opt_taker_fee = st.number_input("Taker Fee % (per side)", min_value=0.0, value=0.05, key="sec7_fee")
with col8:
    opt_tax_rate = st.number_input("Tax Rate %", min_value=0.0, value=30.0, key="sec7_tax")

st.caption(f"Total charges per round trip: Slippage ${opt_slippage*2:.2f} + Taker fee {opt_taker_fee*2:.3f}% + Tax {opt_tax_rate:.1f}% on profit")

if st.button("RUN OPTIMISATION", key="sec7_run"):
    st.info(f"Running optimisation: {opt_strategy} | Group: {opt_group} | Lots: {opt_lots} | Slippage: ${opt_slippage}/side | Fee: {opt_taker_fee}% | Tax: {opt_tax_rate}%")
    with st.spinner("Running optimisation - this may take several minutes..."):
        try:
            cmd = [
                "python", "scripts/run_optimization_cli.py",
                "--strategy", opt_strategy,
                "--group", opt_group,
                "--lots", str(opt_lots),
                "--start", str(opt_start),
                "--end", str(opt_end),
                "--slippage", str(opt_slippage)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                st.success("Optimisation complete")
                st.code(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
            else:
                st.error("Optimisation failed")
                st.code(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        except subprocess.TimeoutExpired:
            st.error("Optimisation timed out after 10 minutes")
        except Exception as e:
            st.error(f"Error: {e}")

st.markdown("---")
st.markdown("**Optimisation Results**")

opt_csv_files = sorted(glob.glob("output/optimization*.csv"), reverse=True)
opt_html_files = sorted(glob.glob("output/optimization*.html"), reverse=True)

col_a, col_b = st.columns(2)
with col_a:
    st.markdown("**CSV Results**")
    if opt_csv_files:
        sel_opt_csv = st.selectbox("Select Optimisation CSV", opt_csv_files, key="sec7_csv_sel")
        if st.button("VIEW RESULTS TABLE", key="sec7_view_csv"):
            try:
                import pandas as pd
                df = pd.read_csv(sel_opt_csv)
                if 'net_pnl' in df.columns:
                    best_idx = df['net_pnl'].idxmax()
                    st.success(f"Best row: index {best_idx}")
                st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.error(f"Error: {e}")
        with open(sel_opt_csv, 'rb') as f:
            st.download_button("DOWNLOAD CSV", f, file_name=os.path.basename(sel_opt_csv), key="sec7_dl_csv")
    else:
        st.info("No optimisation CSV files found in output/ folder")

with col_b:
    st.markdown("**HTML Reports**")
    if opt_html_files:
        sel_opt_html = st.selectbox("Select Optimisation HTML", opt_html_files, key="sec7_html_sel")
        if st.button("VIEW HTML", key="sec7_view_html"):
            try:
                content = open(sel_opt_html, encoding='utf-8').read()
                st.components.v1.html(content, height=600, scrolling=True)
            except Exception as e:
                st.error(f"Error: {e}")
        with open(sel_opt_html, 'rb') as f:
            st.download_button("DOWNLOAD HTML", f, file_name=os.path.basename(sel_opt_html), key="sec7_dl_html")
    else:
        st.info("No optimisation HTML files found in output/ folder")
"""

current = open('dashboard/streamlit_app.py').read()
current = re.sub(r'\n# =+\n# SECTION 7 - OPTIMISATION.*?(?=\n# =+\n# SECTION 8)', '', current, flags=re.DOTALL)
target = '# ================================================================\n# SECTION 8 - BATCH BACKTEST'
new_content = current.replace(target, new_section7 + '\n' + target)
open('dashboard/streamlit_app.py', 'w').write(new_content)
print('SECTION 7 TAX INPUTS FIXED')
