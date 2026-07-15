"""Operational trust, refresh, and recovery console."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.backup import create_verified_backup, run_restore_drill, verify_backup_manifest
from src.operations import (
    get_operation_runs, provider_health, run_due_maintenance, short_interest_evidence_health,
)
from src.data.database import (
    acknowledge_research_alert, get_backtest_runs, get_positioning_history,
    get_provider_health_transitions, get_research_alerts, get_watchlist, save_research_alerts,
)
from src.evidence_monitoring import options_evidence_report
from src.research_alerts import build_research_alerts
from src.ui import inject_app_styles, page_header, zebra_table


st.set_page_config(page_title="Operations | Personal Equity Radar", page_icon="🩺", layout="wide")
inject_app_styles()
page_header(
    "Local reliability", "Operations",
    "See whether research evidence is fresh, background maintenance is running, and recovery is verified.",
    "Local-only · No execution",
)

health = pd.DataFrame(provider_health())
st.subheader("Provider health")
if not health.empty:
    status_icons = {
        "Healthy": "🟢", "Stale": "🟠", "Missing": "🔴", "Failed": "🔴",
        "Running": "🔵", "Pending": "⚪",
    }
    health["status"] = health["status"].map(lambda value: f"{status_icons.get(value, '⚪')} {value}")
    st.dataframe(
        zebra_table(health), hide_index=True, width="stretch",
        column_config={"age_hours": st.column_config.NumberColumn("Age (hours)", format="%.1f")},
    )
st.caption("Provider failures remain isolated: missing or stale evidence never becomes directional evidence.")

st.subheader("Short-interest evidence freshness")
st.caption(
    "Download time and report time are different. FINRA short interest is normally published twice monthly; "
    "only a dated report inside the scoring freshness gate may affect Entry/Exit scores."
)
short_health = pd.DataFrame(short_interest_evidence_health())
if short_health.empty:
    st.info("No watchlist short-interest evidence is available.")
else:
    short_icons = {
        "Current official": "🟢", "Stale — excluded": "🔴",
        "Missing — excluded": "🔴", "Future — excluded": "🔴",
        "Not applicable": "⚪",
    }
    short_health["status"] = short_health["status"].map(
        lambda value: f"{short_icons.get(value, '🔴')} {value}"
    )
    st.dataframe(
        zebra_table(short_health), hide_index=True, width="stretch",
        column_config={
            "ticker": "Ticker", "status": "Evidence status",
            "report_date": st.column_config.DateColumn("Official report date", format="YYYY-MM-DD"),
            "report_age_days": st.column_config.NumberColumn("Report age (days)", format="%d"),
            "used_in_scores": "Used in scores", "source": "Evidence source", "reason": "Rule",
        },
    )

st.subheader("Background maintenance")
runs = get_operation_runs()
if runs:
    run_frame = pd.DataFrame(runs)
    run_frame["detail"] = run_frame["detail_json"].map(
        lambda value: ", ".join(f"{key}: {item}" for key, item in json.loads(value or "{}").items())
    )
    st.dataframe(
        zebra_table(run_frame[["operation_key", "status", "completed_at", "detail", "error"]]),
        hide_index=True, width="stretch",
    )
else:
    st.info("The server-lifetime scheduler has not completed its first cycle yet.")
if st.button("Run due maintenance now"):
    result = run_due_maintenance()
    st.success(f"Maintenance checked · {len(result['refresh_scheduled'])} provider refresh(es) queued.")
    st.rerun()

st.subheader("Verified local recovery")
st.caption(
    "Backups use SQLite's online backup API and receive an integrity-checked SHA-256 manifest. "
    "This page never restores over the live database."
)
backup_col, verify_col = st.columns(2)
with backup_col:
    if st.button("Create verified backup", type="primary"):
        result = create_verified_backup()
        st.success(f"Verified backup created · {result['database_file']}")
        st.code(result["sha256"])
with verify_col:
    manifest_path = st.text_input("Manifest path", placeholder="work/backups/equity-radar-…manifest.json")
    if st.button("Verify existing backup", disabled=not manifest_path.strip()):
        result = verify_backup_manifest(manifest_path.strip())
        (st.success if result["valid"] else st.error)(
            "Backup and manifest are valid." if result["valid"] else "Backup verification failed."
        )
    if st.button("Run isolated restore drill", disabled=not manifest_path.strip()):
        result = run_restore_drill(manifest_path.strip())
        (st.success if result["valid"] else st.error)(
            "Restore drill passed; schema and row counts match and the temporary copy was removed."
            if result["valid"] else "Restore drill failed. The live database was never touched."
        )

st.subheader("Options evidence continuity")
st.caption(
    "Monitoring only. Options evidence remains excluded from live scores until continuity, overlap, "
    "and a separate purged evaluation all pass."
)
positioning_histories = {ticker: get_positioning_history(ticker) for ticker in get_watchlist()}
options_report = pd.DataFrame(options_evidence_report(positioning_histories))
if options_report.empty:
    st.info("No watchlist options history is available yet.")
else:
    options_report["research_ready"] = options_report["research_ready"].map(
        {True: "🟢 Coverage ready", False: "🔴 Accumulating"}
    )
    st.dataframe(zebra_table(options_report), hide_index=True, width="stretch")
    st.caption(
        "Coverage-ready means eligible for an offline experiment—not eligible for scoring or promotion."
    )

st.subheader("Research alerts")
save_research_alerts(build_research_alerts(
    get_backtest_runs(), positioning_histories=positioning_histories,
    provider_transitions=get_provider_health_transitions(),
))
alerts = get_research_alerts()
if not alerts:
    st.success("No unacknowledged material research changes.")
else:
    st.caption("Alerts report persisted evidence changes; they are not trade instructions.")
    for alert in alerts[:20]:
        with st.container(border=True):
            columns = st.columns([5, 1])
            columns[0].markdown(f"**{alert['title']}**")
            columns[0].caption(f"{alert['evidence_date']} · {alert['detail']}")
            if columns[1].button("Acknowledge", key=f"ack-{alert['alert_id']}"):
                acknowledge_research_alert(str(alert["alert_id"]))
                st.rerun()
