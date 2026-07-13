"""Dedicated watchlist administration page."""

import pandas as pd
import streamlit as st

from src.data.database import add_ticker, get_watchlist, init_db, remove_ticker
from src.data.industry_refresh import schedule_industry_refresh
from src.data.positioning_refresh import finra_backfill_status, schedule_finra_backfill
from src.data.backtest_refresh import schedule_ticker_backfill, ticker_backfill_status
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
guidance.info("Add or remove symbols here. Decision dashboard and Company will reflect the updated universe immediately.")

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
            schedule_finra_backfill([normalized], max_new=1)
            scheduled_dates = schedule_ticker_backfill(normalized)
            st.success(
                f"Added {normalized}. Peer discovery and backfill across "
                f"{len(scheduled_dates)} saved simulation(s) started automatically."
            )
            st.rerun()
        else:
            st.warning("Enter a ticker symbol.")

with remove_tab:
    st.subheader("Remove a company")
    if not tickers:
        st.info("The watchlist is empty.")
    else:
        with st.container(border=True):
            ticker_to_remove = st.selectbox("Ticker", tickers, key="watchlist_remove_ticker")
            confirm = st.checkbox(
                f"Confirm removal of {ticker_to_remove} from the watchlist",
                key=f"confirm_watchlist_removal_{ticker_to_remove}",
            )
            remove = st.button("Remove selected ticker", disabled=not confirm, type="primary")
        if remove:
            try:
                remove_ticker(ticker_to_remove)
                st.success(f"Removed {ticker_to_remove} from the watchlist.")
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))

if tickers:
    # Recovery trigger: catches tickers added before automatic backfill existed.
    for symbol in tickers:
        schedule_ticker_backfill(symbol)
    schedule_finra_backfill(tickers, max_new=2)

    @st.fragment(run_every=2)
    def render_backfill_status() -> None:
        active = [ticker_backfill_status(symbol) for symbol in tickers]
        relevant = [status for status in active if status["busy"] or status["completed"] < status["total"]]
        for status in relevant:
            if status["busy"]:
                st.status(
                    f"Backtesting {status['ticker']} · {status['completed']}/{status['total']} saved dates completed",
                    state="running",
                )
            elif status["failed"]:
                st.warning(
                    f"{status['ticker']} backfill finished with exclusions · "
                    f"{status['completed']}/{status['total']} dates persisted · {status['failed']} unavailable"
                )

    render_backfill_status()
    finra_pending = [symbol for symbol in tickers if finra_backfill_status(symbol) == "Backfilling"]
    if finra_pending:
        st.caption(f"FINRA history backfilling automatically · {', '.join(finra_pending)}")
    st.subheader("Current research universe")
    grid_width = 3
    cells = [f"{index + 1:02d} · {symbol}" for index, symbol in enumerate(tickers)]
    cells.extend([""] * (-len(cells) % grid_width))
    rows = [cells[index:index + grid_width] for index in range(0, len(cells), grid_width)]
    st.dataframe(
        pd.DataFrame(rows, columns=["1", "2", "3"]),
        hide_index=True,
        width="stretch",
        height=36 + (35 * len(rows)),
        column_config={
            column: st.column_config.TextColumn(column, width="small")
            for column in ("1", "2", "3")
        },
    )
