import re

section5 = """
# ================================================================
# SECTION 5 - LOG MONITOR
# ================================================================
st.markdown("<div class='section-title'>SECTION 5 - LOG MONITOR</div>", unsafe_allow_html=True)

col_sel, col_filter = st.columns([2,3])
with col_sel:
    log_choice = st.selectbox("Select Log", ["S2", "S4", "Both"], key="sec5_log")
with col_filter:
    custom_filter = st.text_input("Custom Filter (type keyword)", value="", key="sec5_custom")

qf1, qf2, qf3, qf4 = st.columns(4)
with qf1:
    if st.button("ORDER", key="sec5_order"):
        st.session_state['sec5_filter'] = "ORDER"
with qf2:
    if st.button("ERROR", key="sec5_error"):
        st.session_state['sec5_filter'] = "ERROR"
with qf3:
    if st.button("ALGOTEST", key="sec5_algotest"):
        st.session_state['sec5_filter'] = "ALGOTEST"
with qf4:
    if st.button("ALL", key="sec5_all"):
        st.session_state['sec5_filter'] = ""

active_filter = custom_filter if custom_filter else st.session_state.get('sec5_filter', '')

def read_log(path, keyword='', last_n=50):
    try:
        if os.path.exists(path):
            lines = open(path, encoding='utf-8', errors='ignore').readlines()
            if keyword:
                lines = [l for l in lines if keyword.upper() in l.upper()]
            return lines[-last_n:]
        return [f"Log not found: {path}"]
    except Exception as e:
        return [f"Error reading log: {e}"]

def format_log_line(line):
    if 'ERROR' in line:
        return f"🔴 {line.strip()}"
    elif 'ORDER' in line:
        return f"🟢 {line.strip()}"
    elif 'ALGOTEST' in line:
        return f"🔵 {line.strip()}"
    else:
        return line.strip()

s2_log_path = system.get('log_path_s2', 'logs/live_trading_s2.log')
s4_log_path = system.get('log_path_s4', 'logs/live_trading_s4.log')

if log_choice == "S2":
    lines = read_log(s2_log_path, active_filter)
    st.markdown(f"**S2 Log** - Filter: `{active_filter if active_filter else 'ALL'}`")
    st.code('\\n'.join([format_log_line(l) for l in lines]), language=None)
elif log_choice == "S4":
    lines = read_log(s4_log_path, active_filter)
    st.markdown(f"**S4 Log** - Filter: `{active_filter if active_filter else 'ALL'}`")
    st.code('\\n'.join([format_log_line(l) for l in lines]), language=None)
else:
    col_s2, col_s4 = st.columns(2)
    with col_s2:
        lines = read_log(s2_log_path, active_filter)
        st.markdown(f"**S2 Log** - Filter: `{active_filter if active_filter else 'ALL'}`")
        st.code('\\n'.join([format_log_line(l) for l in lines]), language=None)
    with col_s4:
        lines = read_log(s4_log_path, active_filter)
        st.markdown(f"**S4 Log** - Filter: `{active_filter if active_filter else 'ALL'}`")
        st.code('\\n'.join([format_log_line(l) for l in lines]), language=None)

col_ref, col_auto = st.columns(2)
with col_ref:
    if st.button("REFRESH LOGS", key="sec5_refresh"):
        st.rerun()
with col_auto:
    auto_refresh = st.checkbox("AUTO REFRESH 30s", key="sec5_autorefresh")
    if auto_refresh:
        import time
        time.sleep(30)
        st.rerun()
"""

current = open('dashboard/streamlit_app.py').read()
footer_marker = '# ================================================================\n# FOOTER'
current = re.sub(r'\n# =+\n# SECTION 5.*?(?=\n# =+\n# FOOTER)', '', current, flags=re.DOTALL)
new_content = current.replace(footer_marker, section5 + '\n' + footer_marker)
open('dashboard/streamlit_app.py', 'w').write(new_content)
print('SECTION 5 ADDED')
