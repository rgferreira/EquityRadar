"""Congressional-disclosure research and provider coverage."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data.congress_trading import FMPCongressTradingProvider
from src.data.database import (
    get_provider_health_states,
    get_whale_backfill_states,
    get_whale_disclosures,
    get_whale_raw_payloads,
    init_db,
)
from src.ui import inject_app_styles, page_header, zebra_table
from src.utils.config import FMP_API_KEY
from src.whaleseeker import (
    disclosure_feed,
    politician_profiles,
    run_historical_backfill_step,
    whaleseeker_runtime_enabled,
)


st.set_page_config(page_title="WhaleSeeker | Personal Equity Radar", page_icon="🐋", layout="wide")
init_db()
inject_app_styles()
page_header(
    "Public-disclosure intelligence", "WhaleSeeker",
    "Inspect who traded, when the filing became observable, and whether the evidence is copyable.",
    "Research only · 0% model weight",
)

if not whaleseeker_runtime_enabled():
    st.warning("WhaleSeeker is disabled by WHALESEEKER_ENABLED. Existing lineage remains stored locally.")
    st.stop()

observations = get_whale_disclosures(latest_only=True)
raw_payloads = get_whale_raw_payloads()
feed = disclosure_feed(observations)
profiles = politician_profiles(observations)

metric_columns = st.columns(4)
metric_columns[0].metric("Current disclosures", len(observations))
metric_columns[1].metric("Politicians observed", len(profiles))
metric_columns[2].metric(
    "Equity tickers", len({str(row["ticker"]) for row in observations if row.get("ticker")}),
)
metric_columns[3].metric("Raw batches retained", len(raw_payloads))

recent_tab, politicians_tab, data_tab = st.tabs([
    "Recent disclosures", "Politicians", "Data & ingestion",
])

with recent_tab:
    st.subheader("Observed public disclosures")
    st.caption(
        "Sorted by filing and first-observed time. Transaction date never substitutes for public availability."
    )
    if not feed:
        st.info("No congressional data has been imported yet. Open Data & ingestion to fetch one bounded batch.")
    else:
        st.dataframe(
            zebra_table(pd.DataFrame(feed)),
            hide_index=True,
            width="stretch",
            column_config={
                "Source": st.column_config.LinkColumn("Official source", display_text="Open"),
                "Filing lag (days)": st.column_config.NumberColumn(format="%d"),
                "App lag (days)": st.column_config.NumberColumn(format="%d"),
            },
        )
        st.caption(
            "App lag is expected to be large during historical bootstrap. Those rows remain retrospective; "
            "future polling will create the prospective cohort."
        )

with politicians_tab:
    st.subheader("Politician profiles")
    st.caption(
        "Activity and disclosure behavior from the locally observed sample. Returns remain pending until "
        "the copyable next-session outcome policy is preregistered and implemented."
    )
    if not profiles:
        st.info("Politician profiles will appear after the first imported batch.")
    else:
        st.dataframe(zebra_table(pd.DataFrame(profiles)), hide_index=True, width="stretch")

with data_tab:
    st.subheader("Historical bootstrap")
    st.caption(
        "Each action requests at most one 25-row page from House and one from Senate. Cursors advance "
        "only after atomic persistence, protecting both quota and lineage."
    )
    message = st.session_state.pop("whaleseeker_import_message", None)
    if message:
        (st.success if message["ok"] else st.warning)(message["text"])
    backfill = get_whale_backfill_states("fmp_congress")
    st.dataframe(
        zebra_table(pd.DataFrame(backfill)), hide_index=True, width="stretch",
        column_config={
            "provider_key": "Provider", "chamber": "Chamber", "next_page": "Next page",
            "status": "Status", "last_rows_received": "Last rows", "last_error": "Last error",
            "updated_at": "Updated",
        },
    )
    if st.button(
        "Import next historical batch · max 50 rows",
        type="primary",
        disabled=not bool(FMP_API_KEY),
        help="Uses the configured local FMP key. No credential is stored in WhaleSeeker tables or logs.",
    ):
        with st.spinner("Importing one bounded House page and one Senate page…"):
            results = run_historical_backfill_step(FMPCongressTradingProvider(FMP_API_KEY))
        imported = sum(int(row.get("observations_inserted") or 0) for row in results)
        failures = [row for row in results if row.get("status") == "failed"]
        st.session_state["whaleseeker_import_message"] = {
            "ok": not failures,
            "text": (
                f"Historical step committed · {imported} new or amended observations."
                if not failures else
                f"Historical step partially completed · {len(failures)} chamber retry pending."
            ),
        }
        st.rerun()
    if not FMP_API_KEY:
        st.info("Configure FMP_API_KEY locally to enable bounded historical import.")

    st.subheader("Provider state")
    health = [
        row for row in get_provider_health_states()
        if str(row["provider_key"]).endswith("congress")
    ]
    if health:
        st.dataframe(zebra_table(pd.DataFrame(health)), hide_index=True, width="stretch")
    else:
        st.info("No WhaleSeeker provider request has run yet.")
    st.caption(
        "FMP is the initial adapter. Quiver remains optional and will only be retained if a measured "
        "paid bake-off demonstrates better actionable-session latency or material coverage."
    )
