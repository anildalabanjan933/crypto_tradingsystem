import re

section4 = """
# ================================================================
# SECTION 4 - FORWARD TEST vs BACKTEST COMPARE
# ================================================================
st.markdown("<div class='section-title'>SECTION 4 - FORWARD TEST vs BACKTEST COMPARE</div>", unsafe_allow_html=True)

selected_algo = st.selectbox("Select Strategy", ["S2 - RenkoReversalStrategy", "S4 - RenkoSMIIOSupertrendStrategy"], key="sec4_algo")

if "S2" in selected_algo:
    backtest = {
        "Trade Count": 1506, "Win Rate": 52.26,
        "Total PnL (L)": 26.37, "Max DD (%)": 0.27,
        "Slippage/side ($)": 5.0, "Sharpe": 5.55
    }
    thresholds = {
        "Trade Count": 0, "Win Rate": 3.0,
        "Total PnL (L)": 5.0, "Max DD (%)": 0.05,
        "Slippage/side ($)": 3.0, "Sharpe": 1.0
    }
else:
    backtest = {
        "Trade Count": 659, "Win Rate": 57.66,
        "Total PnL (L)": 23.37, "Max DD (%)": 0.28,
        "Slippage/side ($)": 5.0, "Sharpe": 6.92
    }
    thresholds = {
        "Trade Count": 0, "Win Rate": 3.0,
        "Total PnL (L)": 5.0, "Max DD (%)": 0.05,
        "Slippage/side ($)": 3.0, "Sharpe": 1.0
    }

st.markdown("**Enter Forward Test Values (from Algotest dashboard)**")
forward = {}
c1, c2, c3 = st.columns(3)
with c1:
    forward["Trade Count"] = st.number_input("Trade Count", min_value=0, value=0, key="sec4_tc")
    forward["Win Rate"] = st.number_input("Win Rate (%)", min_value=0.0, value=0.0, key="sec4_wr")
with c2:
    forward["Total PnL (L)"] = st.number_input("Total PnL (L)", value=0.0, key="sec4_pnl")
    forward["Max DD (%)"] = st.number_input("Max DD (%)", min_value=0.0, value=0.0, key="sec4_dd")
with c3:
    forward["Slippage/side ($)"] = st.number_input("Slippage/side ($)", min_value=0.0, value=0.0, key="sec4_slip")
    forward["Sharpe"] = st.number_input("Sharpe", value=0.0, key="sec4_sharpe")

st.markdown("---")
st.markdown("**Comparison Table**")

header = st.columns([2,2,2,1,2])
header[0].markdown("**Metric**")
header[1].markdown("**Backtest**")
header[2].markdown("**Forward**")
header[3].markdown("**Diff**")
header[4].markdown("**Status**")

red_alerts = []
for metric in backtest:
    row = st.columns([2,2,2,1,2])
    bt_val = backtest[metric]
    fw_val = forward[metric]
    diff = abs(fw_val - bt_val)
    threshold = thresholds[metric]
    row[0].write(metric)
    row[1].write(str(bt_val))
    row[2].write(str(fw_val))
    row[3].write(f"{diff:.2f}")
    if fw_val == 0:
        row[4].info("PENDING")
    elif diff <= threshold:
        row[4].success("MATCH")
    else:
        row[4].error("INVESTIGATE")
        red_alerts.append(f"{metric}: diff={diff:.2f} exceeds threshold={threshold}")

if red_alerts:
    st.markdown("---")
    for alert in red_alerts:
        st.markdown(f"<div class='alert-red'>MISMATCH DETECTED: {alert}</div>", unsafe_allow_html=True)
else:
    if any(forward[m] > 0 for m in forward):
        st.markdown("<div class='alert-green'>ALL METRICS MATCH - Forward test healthy</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='alert-yellow'>PENDING - Enter forward test values above to compare</div>", unsafe_allow_html=True)
"""

current = open('dashboard/streamlit_app.py').read()
footer_marker = '# ================================================================\n# FOOTER'
current = re.sub(r'\n# =+\n# SECTION 4.*?(?=\n# =+\n# FOOTER)', '', current, flags=re.DOTALL)
new_content = current.replace(footer_marker, section4 + '\n' + footer_marker)
open('dashboard/streamlit_app.py', 'w').write(new_content)
print('SECTION 4 ADDED')
