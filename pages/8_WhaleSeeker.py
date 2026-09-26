"""Congressional-disclosure research and provider coverage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pandas as pd
import streamlit as st

from src.data.congress_trading import FMPCongressTradingProvider
from src.data.database import (
    get_provider_health_states,
    get_whale_backfill_states,
    get_whale_disclosures,
    init_db,
)
from src.ui import inject_app_styles, page_header, zebra_table
from src.utils.config import FMP_API_KEY
from src.whaleseeker import (
    add_since_trade_returns,
    disclosure_feed,
    empty_disclosure_message,
    normalize_trade_filter,
    politician_profiles,
    run_historical_backfill_step,
    whaleseeker_runtime_enabled, whale_ingestion_summary, whale_catchup_states,
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
ingestion_summary = whale_ingestion_summary()
profiles = politician_profiles(observations)
last_provider_check = str(ingestion_summary["last_provider_check"] or "")
try:
    last_provider_check_at = datetime.fromisoformat(last_provider_check.replace("Z", "+00:00"))
except ValueError:
    last_provider_check_at = None

if not FMP_API_KEY:
    st.warning(
        "Automatic WhaleSeeker refresh is unavailable because no congressional-data provider is configured. "
        "Displayed disclosures may be incomplete."
    )
elif last_provider_check_at is None:
    st.warning("WhaleSeeker has never completed a provider check. Automatic refresh will retry in the background.")
elif datetime.now(timezone.utc) - last_provider_check_at.astimezone(timezone.utc) > timedelta(hours=12):
    st.warning(
        "WhaleSeeker data has not been checked with the provider for more than 12 hours. "
        "Displayed disclosures may be incomplete; automatic refresh will retry in the background."
    )
else:
    st.caption(f"Latest provider check: {last_provider_check_at.astimezone().strftime('%Y-%m-%d %H:%M %Z')}")

metric_columns = st.columns(4)
metric_columns[0].metric("Current disclosures", len(observations))
metric_columns[1].metric("Politicians observed", len(profiles))
metric_columns[2].metric(
    "Equity tickers", len({str(row["ticker"]) for row in observations if row.get("ticker")}),
)
metric_columns[3].metric("Latest filing", max((str(row.get("filed_date") or "") for row in observations), default="—"))
st.caption("Congressional disclosures · delayed public filings, not real-time institutional order flow.")
with st.expander("Institutional futures positioning · CFTC"):
    from src.data.institutional_positioning import institutional_summary
    institutional = institutional_summary()
    if institutional["records"]:
        st.dataframe(pd.DataFrame(institutional["records"]), hide_index=True, width="stretch")
    else:
        st.info("Institutional positioning has not been captured yet; automatic refresh is independent of the congressional provider.")
    st.caption("Weekly asset-manager and leveraged-money net positions as a share of open interest. Delayed positioning, not dollar flows. "
               "This separate source does not fill the FMP congressional history gap. No model score contribution.")
catchup = whale_catchup_states()
if any(row["status"] == "pending" for row in catchup):
    st.warning("Latest data is available, but recovery of the earlier gap is still in progress.")
if any(row["status"] == "blocked_entitlement" for row in catchup):
    st.warning("FMP subscription permits the latest page but blocks older pages (HTTP 402). The historical gap is incomplete; latest checks continue.")

recent_tab, politicians_tab, data_tab = st.tabs([
    "Recent disclosures", "Politicians", "Data & ingestion",
], on_change="rerun", key="whale_active_tab")

with recent_tab:
    if recent_tab.open:
        st.subheader("Observed public disclosures")
        st.caption(
            "Sorted from newest to oldest trade. Filing and first-observed time remain visible because "
            "transaction date never substitutes for public availability."
        )
        selected_trade = st.segmented_control(
            "Transaction type",
            options=("All", "Purchase", "Sale"),
            default="All",
            key="whaleseeker_trade_filter",
        )
        transaction_types = normalize_trade_filter(selected_trade)
        feed = disclosure_feed(
            observations, transaction_types=transaction_types, order_by="trade",
        )
        if not feed:
            if observations:
                st.info(empty_disclosure_message(
                    selected_trade, restricted_to_universe=False,
                ))
            else:
                st.info("No congressional data has been imported yet. Open Data & ingestion to fetch one bounded batch.")
        else:
            feed = feed[:100]
            if st.checkbox("Calculate descriptive returns for these 100 disclosures", value=False):
                feed = add_since_trade_returns(feed)
            else:
                feed = [{**row, "Since trade %": None} for row in feed]
            display = pd.DataFrame(feed)[[
                "Ticker", "Asset", "Ticker quality", "Since trade %", "Trade", "Traded", "Politician", "Chamber",
                "Amount", "Filed", "Filing lag (days)", "First seen by app", "App lag (days)",
                "Owner", "Source",
            ]]
            st.dataframe(
                zebra_table(display),
                hide_index=True,
                width="stretch",
                column_config={
                    "Ticker": st.column_config.TextColumn(
                        help="Provider-reported security symbol. Share classes are preserved; GOOGL is not rewritten as GOOG.",
                        width=80,
                    ),
                    "Asset": st.column_config.TextColumn(width=240),
                    "Since trade %": st.column_config.NumberColumn(format="%+.1f"),
                    "Trade": st.column_config.TextColumn(width=90),
                    "Source": st.column_config.LinkColumn("Official source", display_text="Open"),
                    "Filing lag (days)": st.column_config.NumberColumn(format="%d"),
                    "App lag (days)": st.column_config.NumberColumn(format="%d"),
                },
            )
            st.caption(
                "Ticker is the reported security symbol; Asset supplies issuer and share-class context. "
                "Ticker quality flags unusual formats for review without guessing a replacement. "
                "Since trade % uses the first available adjusted close on or after the reported trade date "
                "and the latest close; it is not the politician's execution price or a copyable return. "
                "App lag is expected to be large during historical bootstrap."
            )

with politicians_tab:
    if politicians_tab.open:
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
    if data_tab.open:
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

        st.subheader("Gap recovery")
        st.dataframe(pd.DataFrame(catchup), hide_index=True, width="stretch")
        st.caption(f"Raw batches retained: {ingestion_summary['batches']}")
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
        st.caption(
            "Latest House and Senate pages refresh automatically every six hours while the server runs, with bounded gap recovery. "
            "Historical cursor imports remain manual and independent."
        )
