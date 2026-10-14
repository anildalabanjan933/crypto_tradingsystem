import re

section_portfolio = """
# ================================================================
# SECTION 6B - PORTFOLIO BACKTEST
# ================================================================
st.markdown("<div class='section-title'>SECTION 6B - PORTFOLIO BACKTEST</div>", unsafe_allow_html=True)

import subprocess, glob, os

port_tab1, port_tab2 = st.tabs(["PREDEFINED PORTFOLIO", "DYNAMIC PORTFOLIO"])

with port_tab1:
    st.markdown("**Predefined Portfolios**")
    portfolios = {
        'DE-Strangle Intraday': 'Intraday option selling (3 strategies)',
        'DE-Strangle BTST': 'BTST directional option strategies (4 strategies)',
        'Monthly Positional': 'Monthly positional option strategies (3 strategies)'
    }
    for name, desc in portfolios.items():
        st.caption(f"{name}: {desc}")

    col1, col2 = st.columns(2)
    with col1:
        port_start = st.date_input("Start Date", value=datetime.date(2025,1,1), key="port_start")
    with col2:
        port_end = st.date_input("End Date", value=datetime.date.today(), key="port_end")

    port_lots = st.number_input("Lots", min_value=1, value=100, key="port_lots")
    port_slippage = st.number_input("Slippage/side ($)", min_value=0.0, value=5.0, key="port_slip")

    if st.button("RUN PREDEFINED PORTFOLIO", key="port_run_pre"):
        st.info("Running predefined portfolio backtest...")
        with st.spinner("Running..."):
            try:
                result = subprocess.run(
                    ["python", "run_portfolio_backtest.py"],
                    capture_output=True, text=True, timeout=600,
                    input="1\n1\n"
                )
                if result.returncode == 0:
                    st.success("Portfolio backtest complete")
                    st.code(result.stdout[-3000:])
                else:
                    st.error("Portfolio backtest failed")
                    st.code(result.stderr[-2000:])
            except Exception as e:
                st.error(f"Error: {e}")

with port_tab2:
    st.markdown("**Dynamic Portfolio - Select Strategies**")
    available_strategies = [
        "RenkoReversalStrategy",
        "RenkoSMIIOSupertrendStrategy",
        "RenkoBreakoutStrategy",
        "RenkoTrendlinePullbackStrategy"
    ]
    selected_strategies = st.multiselect(
        "Select Strategies",
        available_strategies,
        default=["RenkoReversalStrategy", "RenkoSMIIOSupertrendStrategy"],
        key="port_dyn_strategies"
    )
    col1, col2 = st.columns(2)
    with col1:
        port_dyn_start = st.date_input("Start Date", value=datetime.date(2025,1,1), key="port_dyn_start")
    with col2:
        port_dyn_end = st.date_input("End Date", value=datetime.date.today(), key="port_dyn_end")

    port_dyn_lots = st.number_input("Lots", min_value=1, value=100, key="port_dyn_lots")
    port_dyn_slip = st.number_input("Slippage/side ($)", min_value=0.0, value=5.0, key="port_dyn_slip")

    if st.button("RUN DYNAMIC PORTFOLIO", key="port_run_dyn"):
        if not selected_strategies:
            st.error("Please select at least one strategy")
        else:
            st.info(f"Running dynamic portfolio: {selected_strategies}")
            with st.spinner("Running..."):
                try:
                    strategies_input = "\\n".join([str(i+1) for i in range(len(selected_strategies))])
                    result = subprocess.run(
                        ["python", "run_portfolio_backtest.py"],
                        capture_output=True, text=True, timeout=600,
                        input=f"2\\n{strategies_input}\\n"
                    )
                    if result.returncode == 0:
                        st.success("Dynamic portfolio backtest complete")
                        st.code(result.stdout[-3000:])
                    else:
                        st.error("Dynamic portfolio backtest failed")
                        st.code(result.stderr[-2000:])
                except Exception as e:
                    st.error(f"Error: {e}")

st.markdown("---")
st.markdown("**Portfolio Reports**")
port_html = sorted(glob.glob("output/portfolio*.html"), reverse=True)
port_csv = sorted(glob.glob("output/portfolio*.csv"), reverse=True)

col_a, col_b = st.columns(2)
with col_a:
    st.markdown("**HTML Reports**")
    if port_html:
        sel_port_html = st.selectbox("Select Portfolio HTML", port_html, key="port_html_sel")
        if st.button("VIEW HTML", key="port_view_html"):
            content = open(sel_port_html, encoding='utf-8').read()
            st.components.v1.html(content, height=600, scrolling=True)
        with open(sel_port_html, 'rb') as f:
            st.download_button("DOWNLOAD HTML", f, file_name=os.path.basename(sel_port_html), key="port_dl_html")
    else:
        st.info("No portfolio HTML reports found in output/ folder")

with col_b:
    st.markdown("**CSV Results**")
    if port_csv:
        sel_port_csv = st.selectbox("Select Portfolio CSV", port_csv, key="port_csv_sel")
        if st.button("VIEW CSV", key="port_view_csv"):
            import pandas as pd
            df = pd.read_csv(sel_port_csv)
            st.dataframe(df, use_container_width=True)
        with open(sel_port_csv, 'rb') as f:
            st.download_button("DOWNLOAD CSV", f, file_name=os.path.basename(sel_port_csv), key="port_dl_csv")
    else:
        st.info("No portfolio CSV files found in output/ folder")
"""

current = open('dashboard/streamlit_app.py').read()
footer_marker = '# ================================================================\n# SECTION 7 - OPTIMISATION'
current = re.sub(r'\n# =+\n# SECTION 6B.*?(?=\n# =+\n# SECTION 7)', '', current, flags=re.DOTALL)
new_content = current.replace(footer_marker, section_portfolio + '\n' + footer_marker)
open('dashboard/streamlit_app.py', 'w').write(new_content)
print('SECTION 6B PORTFOLIO ADDED')
