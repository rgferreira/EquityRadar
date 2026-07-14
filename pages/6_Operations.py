"""Operational trust, refresh, and recovery console."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.backup import create_verified_backup, verify_backup_manifest
from src.operations import get_operation_runs, provider_health, run_due_maintenance
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
    status_icons = {"Healthy": "🟢", "Stale": "🟠", "Missing": "🔴"}
    health["status"] = health["status"].map(lambda value: f"{status_icons.get(value, '⚪')} {value}")
    st.dataframe(
        zebra_table(health), hide_index=True, width="stretch",
        column_config={"age_hours": st.column_config.NumberColumn("Age (hours)", format="%.1f")},
    )
st.caption("Provider failures remain isolated: missing or stale evidence never becomes directional evidence.")

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
