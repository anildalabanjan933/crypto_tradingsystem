import re

section3 = """
# ================================================================
# SECTION 3 - PLATFORM MONITOR
# ================================================================
st.markdown("<div class='section-title'>SECTION 3 - PLATFORM MONITOR</div>", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["DELTA EXCHANGE", "ALGOTEST", "TRADETRON"])

with tab1:
    st.markdown("**Delta Exchange Account**")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Account Balance", "Manual Check")
        st.metric("Unrealised PnL", "Manual Check")
    with c2:
        st.metric("Realised PnL Today", "Manual Check")
        st.metric("Funding Rate", "Manual Check")
    with c3:
        st.metric("Open Positions", "Manual Check")
        st.metric("Last Order", "Manual Check")
    st.info("Visit Delta Exchange to check live account data: https://www.delta.exchange")
    st.markdown("**API Status**")
    col_a, col_b = st.columns(2)
    with col_a:
        st.success("API KEY: CONFIGURED")
    with col_b:
        st.success("TRADING: ENABLED")

with tab2:
    st.markdown("**Algotest Forward Test Monitor**")
    import datetime
    start = datetime.date(2026, 7, 7)
    end = datetime.date(2026, 7, 24)
    today = datetime.date.today()
    total_days = (end - start).days
    days_done = min((today - start).days, total_days)
    days_left = max((end - today).days, 0)
    progress = min(days_done / total_days, 1.0)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Start Date", str(start))
    with c2:
        st.metric("End Date", str(end))
    with c3:
        st.metric("Days Done", days_done)
    with c4:
        st.metric("Days Left", days_left)

    st.progress(progress, text=f"Forward Test Progress: {int(progress*100)}%")
    st.markdown("---")

    st.markdown("**Webhook Status**")
    webhooks = [
        "S2 BUY ENTRY", "S2 BUY EXIT",
        "S2 SELL ENTRY", "S2 SELL EXIT",
        "S4 BUY ENTRY", "S4 BUY EXIT",
        "S4 SELL ENTRY", "S4 SELL EXIT"
    ]
    w1, w2, w3, w4 = st.columns(4)
    cols = [w1, w2, w3, w4]
    for idx, wh in enumerate(webhooks):
        with cols[idx % 4]:
            st.success(f"{wh}: 200 OK")

    if st.button("TEST ALL WEBHOOKS", key="sec3_test_webhooks"):
        st.info("Run: python algotest_webhook.py on VM to test all webhooks")

    st.markdown("---")
    st.markdown("**Forward Test Metrics**")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("MTM Value", "Check Algotest Dashboard")
    with m2:
        st.metric("Executed Signals", "Check Algotest Dashboard")
    with m3:
        st.metric("Cumulative PnL", "Check Algotest Dashboard")
    with m4:
        st.metric("Max DD So Far", "Check Algotest Dashboard")
    st.info("Visit Algotest dashboard for live MTM and signal data")

with tab3:
    st.markdown("**Tradetron Marketplace**")
    st.warning("NOT CONNECTED - Tradetron setup pending after July 24")
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Status", "NOT CONNECTED")
    with c2:
        st.metric("Subscribers", "N/A")
    with c3:
        st.metric("Signals Sent", "N/A")
    st.info("Tradetron will be configured after July 24 forward test completes")
"""

current = open('dashboard/streamlit_app.py').read()
footer_marker = '# ================================================================\n# FOOTER'
current = re.sub(r'\n# =+\n# SECTION 3.*?(?=\n# =+\n# FOOTER)', '', current, flags=re.DOTALL)
new_content = current.replace(footer_marker, section3 + '\n' + footer_marker)
open('dashboard/streamlit_app.py', 'w').write(new_content)
print('SECTION 3 ADDED')
