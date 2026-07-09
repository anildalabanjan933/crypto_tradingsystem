import re

section6 = """
# ================================================================
# SECTION 6 - BACKTEST
# ================================================================
st.markdown("<div class='section-title'>SECTION 6 - BACKTEST</div>", unsafe_allow_html=True)

import datetime, subprocess, os, glob

col1, col2 = st.columns(2)
with col1:
    bt_strategy = st.selectbox("Select Strategy", [
        "RenkoReversalStrategy",
        "RenkoSMIIOSupertrendStrategy",
        "RenkoBreakoutStrategy",
        "RenkoTrendlinePullbackStrategy"
    ], key="sec6_strategy")
with col2:
    bt_lots = st.number_input("Lots", min_value=1, max_value=10000, value=100, key="sec6_lots")

col3, col4, col5 = st.columns(3)
with col3:
    bt_start = st.date_input("Start Date", value=datetime.date(2025, 1, 1), key="sec6_start")
with col4:
    bt_end = st.date_input("End Date", value=datetime.date.today(), key="sec6_end")
with col5:
    bt_slippage = st.number_input("Slippage/side ($)", min_value=0.0, value=5.0, key="sec6_slip")

if st.button("RUN BACKTEST", key="sec6_run"):
    st.info(f"Running backtest: {bt_strategy} | Lots: {bt_lots} | {bt_start} to {bt_end}")
    with st.spinner("Running backtest..."):
        try:
            cmd = [
                "python", "run_single_strategy.py",
                "--strategy", bt_strategy,
                "--lots", str(bt_lots),
                "--start", str(bt_start),
                "--end", str(bt_end),
                "--slippage", str(bt_slippage),
                "--symbol", "BTCUSD",
                "--csv", "data/btc_1m_delta.csv"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                st.success("Backtest complete")
                st.code(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
            else:
                st.error("Backtest failed")
                st.code(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        except subprocess.TimeoutExpired:
            st.error("Backtest timed out after 5 minutes")
        except Exception as e:
            st.error(f"Error running backtest: {e}")

st.markdown("---")
st.markdown("**Backtest Reports**")

html_files = sorted(glob.glob("output/*.html"), reverse=True)
csv_files = sorted(glob.glob("output/*.csv"), reverse=True)

col_html, col_csv = st.columns(2)
with col_html:
    st.markdown("**HTML Reports**")
    if html_files:
        selected_html = st.selectbox("Select HTML Report", html_files, key="sec6_html_select")
        if st.button("VIEW HTML REPORT", key="sec6_view_html"):
            try:
                content = open(selected_html, encoding='utf-8').read()
                st.components.v1.html(content, height=600, scrolling=True)
            except Exception as e:
                st.error(f"Error opening report: {e}")
        with open(selected_html, 'rb') as f:
            st.download_button("DOWNLOAD HTML", f, file_name=os.path.basename(selected_html), key="sec6_dl_html")
    else:
        st.info("No HTML reports found in output/ folder")

with col_csv:
    st.markdown("**CSV Results**")
    if csv_files:
        selected_csv = st.selectbox("Select CSV", csv_files, key="sec6_csv_select")
        if st.button("VIEW CSV", key="sec6_view_csv"):
            try:
                import pandas as pd
                df = pd.read_csv(selected_csv)
                st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.error(f"Error opening CSV: {e}")
        with open(selected_csv, 'rb') as f:
            st.download_button("DOWNLOAD CSV", f, file_name=os.path.basename(selected_csv), key="sec6_dl_csv")
    else:
        st.info("No CSV files found in output/ folder")
"""

current = open('dashboard/streamlit_app.py').read()
footer_marker = '# ================================================================\n# FOOTER'
current = re.sub(r'\n# =+\n# SECTION 6.*?(?=\n# =+\n# FOOTER)', '', current, flags=re.DOTALL)
new_content = current.replace(footer_marker, section6 + '\n' + footer_marker)
open('dashboard/streamlit_app.py', 'w').write(new_content)
print('SECTION 6 ADDED')
