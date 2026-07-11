"""Dedicated watchlist administration page."""

import streamlit as st

from src.data.database import add_ticker, get_watchlist, init_db, remove_ticker
from src.data.industry_refresh import schedule_industry_refresh
from src.ui import inject_app_styles, page_header

st.set_page_config(page_title="Watchlist | Personal Equity Radar", page_icon="⚙️", layout="wide")
init_db()
inject_app_styles()
page_header(
    "Research universe", "Watchlist management",
    "Keep administration separate from analysis so the research pages retain the full working canvas.",
    "Changes apply across the app",
)

tickers = get_watchlist()
summary, guidance = st.columns([1, 3])
summary.metric("Companies tracked", len(tickers))
guidance.info("Add or remove symbols here. Dashboard and Company will reflect the updated universe immediately.")

add_tab, remove_tab = st.tabs(["Add ticker", "Remove ticker"])
with add_tab:
    st.subheader("Add a company")
    with st.form("watchlist_add", clear_on_submit=True, border=True):
        ticker = st.text_input("Ticker symbol", placeholder="AAPL", max_chars=15)
        submitted = st.form_submit_button("Add to watchlist", type="primary")
    if submitted:
        if ticker.strip():
            normalized = ticker.strip().upper()
            add_ticker(normalized)
            schedule_industry_refresh([normalized], max_new=1)
            st.success(f"Added {normalized}. Peer discovery has started automatically.")
            st.rerun()
        else:
            st.warning("Enter a ticker symbol.")

with remove_tab:
    st.subheader("Remove a company")
    if not tickers:
        st.info("The watchlist is empty.")
    else:
        with st.form("watchlist_remove", border=True):
            ticker_to_remove = st.selectbox("Ticker", tickers)
            confirm = st.checkbox("Confirm removal from the watchlist")
            remove = st.form_submit_button("Remove selected ticker", disabled=not confirm)
        if remove:
            try:
                remove_ticker(ticker_to_remove)
                st.success(f"Removed {ticker_to_remove} from the watchlist.")
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))

if tickers:
    st.subheader("Current research universe")
    columns = st.columns(min(4, len(tickers)))
    for index, symbol in enumerate(tickers):
        columns[index % len(columns)].metric(f"Position {index + 1}", symbol)
