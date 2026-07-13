"""Investment journal page."""

from datetime import date

import pandas as pd
import streamlit as st
from src.downloads import download_link
from src.ui import zebra_table

from src.data.database import (
    add_journal_entry,
    delete_journal_entry,
    get_journal_entries,
    get_watchlist,
    init_db,
    update_journal_entry,
)

ACTIONS = ["watch", "buy_candidate", "reject", "sell_review"]
JOURNAL_FIELDS = (
    "ticker", "entry_date", "action", "thesis", "catalyst", "main_risk",
    "invalidation_condition", "target_price", "time_horizon", "conviction", "notes",
)


def entry_payload(**values):
    return {field: values[field] for field in JOURNAL_FIELDS}


st.set_page_config(page_title="Journal | Personal Equity Radar", page_icon="📝", layout="wide")
init_db()
st.title("Investment journal")
tickers = get_watchlist()
if not tickers:
    st.info("Add a ticker on the Decision dashboard first.")
    st.stop()

with st.form("journal_entry", clear_on_submit=True):
    ticker = st.selectbox("Ticker", tickers, key="new_ticker")
    entry_date = st.date_input("Date", value=date.today(), key="new_date")
    action = st.selectbox("Action", ACTIONS, key="new_action")
    thesis = st.text_area("Thesis", key="new_thesis")
    catalyst = st.text_area("Catalyst", key="new_catalyst")
    main_risk = st.text_area("Main risk", key="new_risk")
    invalidation = st.text_area("Invalidation condition", key="new_invalidation")
    target_price = st.number_input("Target price", min_value=0.0, value=0.0, step=0.01, key="new_target")
    time_horizon = st.text_input("Time horizon", placeholder="12–24 months", key="new_horizon")
    conviction = st.slider("Conviction level", 1, 5, 3, key="new_conviction")
    notes = st.text_area("Notes", key="new_notes")
    save = st.form_submit_button("Save journal entry", type="primary")

if save:
    add_journal_entry(entry_payload(
        ticker=ticker, entry_date=entry_date.isoformat(), action=action, thesis=thesis,
        catalyst=catalyst, main_risk=main_risk, invalidation_condition=invalidation,
        target_price=target_price or None, time_horizon=time_horizon,
        conviction=conviction, notes=notes,
    ))
    st.success("Journal entry saved.")
    st.rerun()

st.subheader("Previous entries")
selected = st.selectbox("Filter by ticker", ["All"] + tickers)
filter_columns = st.columns(2)
selected_action = filter_columns[0].selectbox("Filter by action", ["All", *ACTIONS])
selected_conviction = filter_columns[1].selectbox("Filter by conviction", ["All", 1, 2, 3, 4, 5])
entries = get_journal_entries(
    ticker=None if selected == "All" else selected,
    action=None if selected_action == "All" else selected_action,
    conviction=None if selected_conviction == "All" else selected_conviction,
)
if entries:
    st.dataframe(
        zebra_table(entries),
        hide_index=True,
        use_container_width=True,
        column_config={"target_price": st.column_config.NumberColumn("Target price", format="$%.2f")},
    )
    csv_data = pd.DataFrame(entries).to_csv(index=False)
    st.markdown(download_link("Export filtered entries as CSV", csv_data, "investment-journal.csv", "text/csv"))

    st.subheader("Edit or delete an entry")
    entry_labels = {
        f"#{entry['id']} · {entry['entry_date']} · {entry['ticker']} · {entry['action']}": entry
        for entry in entries
    }
    selected_label = st.selectbox("Entry", list(entry_labels))
    selected_entry = entry_labels[selected_label]
    edit_key = str(selected_entry["id"])
    with st.form("edit_journal_entry"):
        edit_ticker = st.selectbox("Ticker", tickers, index=tickers.index(selected_entry["ticker"]), key=f"edit_ticker_{edit_key}")
        edit_date = st.date_input("Date", value=date.fromisoformat(selected_entry["entry_date"]), key=f"edit_date_{edit_key}")
        edit_action = st.selectbox("Action", ACTIONS, index=ACTIONS.index(selected_entry["action"]), key=f"edit_action_{edit_key}")
        edit_thesis = st.text_area("Thesis", value=selected_entry.get("thesis") or "", key=f"edit_thesis_{edit_key}")
        edit_catalyst = st.text_area("Catalyst", value=selected_entry.get("catalyst") or "", key=f"edit_catalyst_{edit_key}")
        edit_risk = st.text_area("Main risk", value=selected_entry.get("main_risk") or "", key=f"edit_risk_{edit_key}")
        edit_invalidation = st.text_area("Invalidation condition", value=selected_entry.get("invalidation_condition") or "", key=f"edit_invalidation_{edit_key}")
        edit_target = st.number_input("Target price", min_value=0.0, value=float(selected_entry.get("target_price") or 0), step=0.01, key=f"edit_target_{edit_key}")
        edit_horizon = st.text_input("Time horizon", value=selected_entry.get("time_horizon") or "", key=f"edit_horizon_{edit_key}")
        edit_conviction = st.slider("Conviction level", 1, 5, int(selected_entry["conviction"]), key=f"edit_conviction_{edit_key}")
        edit_notes = st.text_area("Notes", value=selected_entry.get("notes") or "", key=f"edit_notes_{edit_key}")
        update = st.form_submit_button("Update entry", type="primary")
    if update:
        update_journal_entry(selected_entry["id"], entry_payload(
            ticker=edit_ticker, entry_date=edit_date.isoformat(), action=edit_action,
            thesis=edit_thesis, catalyst=edit_catalyst, main_risk=edit_risk,
            invalidation_condition=edit_invalidation, target_price=edit_target or None,
            time_horizon=edit_horizon, conviction=edit_conviction, notes=edit_notes,
        ))
        st.success("Journal entry updated.")
        st.rerun()

    confirm_delete = st.checkbox("I understand this permanently deletes the selected entry")
    if st.button("Delete selected entry", disabled=not confirm_delete):
        delete_journal_entry(selected_entry["id"])
        st.success("Journal entry deleted.")
        st.rerun()
else:
    st.caption("No journal entries match these filters.")
