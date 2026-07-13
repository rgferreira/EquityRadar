"""Personal Equity Radar application shell and top navigation."""

import streamlit as st

st.set_page_config(
    page_title="Personal Equity Radar", page_icon="📈", layout="wide",
    initial_sidebar_state="collapsed",
)

pages = [
    st.Page("pages/1_Dashboard.py", title="Dashboard", icon="📊", url_path="Decision-dashboard", default=True),
    st.Page("pages/2_Portfolio.py", title="Portfolio", icon="💼", url_path="Portfolio"),
    st.Page("pages/3_Company.py", title="Company", icon="🏢", url_path="Company"),
    st.Page("pages/4_Journal.py", title="Journal", icon="📝", url_path="Journal"),
    st.Page("pages/0_Watchlist.py", title="Watchlist", icon="⚙️", url_path="Watchlist"),
]
navigation = st.navigation(pages, position="sidebar", expanded=False)
navigation.run()
