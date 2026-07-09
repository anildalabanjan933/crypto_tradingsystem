import re

section2 = """
# ================================================================
# SECTION 2 - BOT CONTROL
# ================================================================
st.markdown("<div class='section-title'>SECTION 2 - BOT CONTROL</div>", unsafe_allow_html=True)

algos = config.get("algos", [])

col_h1, col_h2, col_h3, col_h4, col_h5, col_h6 = st.columns([1,2,2,1,2,2])
col_h1.markdown("**Algo**")
col_h2.markdown("**Strategy**")
col_h3.markdown("**Symbol**")
col_h4.markdown("**Lots**")
col_h5.markdown("**Status**")
col_h6.markdown("**Action**")
st.markdown("---")

for i, algo in enumerate(algos):
    c1, c2, c3, c4, c5, c6 = st.columns([1,2,2,1,2,2])
    with c1:
        st.markdown(f"**{algo['name']}**")
    with c2:
        st.caption(algo.get('strategy',''))
    with c3:
        st.caption(algo.get('symbol','BTCUSD'))
    with c4:
        new_lots = st.number_input(
            "", min_value=1, max_value=10000,
            value=algo.get('lots', 100),
            key=f"sec2_lots_{i}", label_visibility="collapsed"
        )
        if new_lots != algo.get('lots', 100):
            algos[i]['lots'] = new_lots
            config['algos'] = algos
            json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
            st.success("Lots updated")
    with c5:
        if algo.get('active', True):
            st.success("ACTIVE")
        else:
            st.error("INACTIVE")
    with c6:
        col_on, col_off = st.columns(2)
        with col_on:
            if st.button("ON", key=f"sec2_on_{i}"):
                algos[i]['active'] = True
                config['algos'] = algos
                json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
                st.success(f"{algo['name']} activated")
        with col_off:
            if st.button("OFF", key=f"sec2_off_{i}"):
                algos[i]['active'] = False
                config['algos'] = algos
                json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
                st.warning(f"{algo['name']} deactivated")

st.markdown("---")
b1, b2, b3, b4 = st.columns(4)
with b1:
    if st.button("START ALL BOTS", key="sec2_start"):
        st.info("Connect to VM to start bots - use SSH terminal")
with b2:
    if st.button("STOP ALL BOTS", key="sec2_stop"):
        st.warning("Connect to VM to stop bots - use SSH terminal")
with b3:
    if st.button("RESTART ALL BOTS", key="sec2_restart"):
        st.info("Connect to VM to restart - use SSH terminal")
with b4:
    if st.button("ADD NEW ALGO", key="sec2_add"):
        st.session_state['show_add_algo'] = True

if st.session_state.get('show_add_algo', False):
    st.markdown("**Add New Algo**")
    with st.form("add_algo_form"):
        new_name = st.text_input("Algo Name (e.g. S5)")
        new_file = st.text_input("Script File (e.g. run_live_trading_s5.py)")
        new_strategy = st.text_input("Strategy Name")
        new_symbol = st.selectbox("Symbol", ["BTCUSD", "ETHUSD"])
        new_lots = st.number_input("Lots", min_value=1, value=100)
        new_direction = st.selectbox("Direction", ["BOTH", "LONG", "SHORT"])
        col_save, col_cancel = st.columns(2)
        with col_save:
            submitted = st.form_submit_button("SAVE")
        with col_cancel:
            cancelled = st.form_submit_button("CANCEL")
        if submitted and new_name:
            algos.append({
                'name': new_name,
                'file': new_file,
                'strategy': new_strategy,
                'symbol': new_symbol,
                'lots': int(new_lots),
                'direction': new_direction,
                'active': True
            })
            config['algos'] = algos
            json.dump(config, open('dashboard/algo_config.json','w'), indent=2)
            st.success(f"Algo {new_name} added")
            st.session_state['show_add_algo'] = False
        if cancelled:
            st.session_state['show_add_algo'] = False
"""

current = open('dashboard/streamlit_app.py').read()
footer_marker = '# ================================================================\n# FOOTER'
current = re.sub(r'\n# =+\n# SECTION 2 - BOT CONTROL.*?(?=\n# =+\n# FOOTER)', '', current, flags=re.DOTALL)
new_content = current.replace(footer_marker, section2 + '\n' + footer_marker)
open('dashboard/streamlit_app.py', 'w').write(new_content)
print('SECTION 2 FIXED AND ADDED')
