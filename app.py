"""Personal Equity Radar application shell and top navigation."""

import streamlit as st

from src.data.database import acknowledge_model_gate_modal
from src.model_gate_alerts import process_model_gate_alert
from src.model_registry import COVERAGE_AWARE_SHADOW_VERSION

st.set_page_config(
    page_title="Personal Equity Radar", page_icon="📈", layout="wide",
    initial_sidebar_state="collapsed",
)

try:
    gate_report, gate_alert_state = process_model_gate_alert()
except Exception:
    # Alerting is advisory infrastructure and must never prevent app access.
    gate_report = gate_alert_state = None

if (
    gate_alert_state
    and bool(gate_alert_state["gates_cleared"])
    and gate_alert_state["modal_acknowledged_at"] is None
):
    @st.dialog("Shadow model readiness gates cleared", width="large")
    def show_gate_clearance_modal() -> None:
        st.success("All mandatory Phase 3.9 promotion-readiness gates are green.")
        st.write(
            "The accumulated evidence is now eligible for a deliberate human promotion review. "
            "No model has been promoted or activated automatically."
        )
        for criterion in gate_report["gate"]["criteria"]:
            st.markdown(f"🟢 **{criterion['criterion']}** · {criterion['observed']}")
        email_status = str(gate_alert_state["email_status"])
        if email_status == "sent":
            st.caption("Email notification sent.")
        elif email_status == "configuration_required":
            st.warning("Email delivery is waiting for local SMTP configuration.")
        elif email_status == "failed":
            st.warning("Email delivery failed; the application and model state are unaffected.")
        if st.button("Acknowledge and continue", type="primary", width="stretch"):
            acknowledge_model_gate_modal(COVERAGE_AWARE_SHADOW_VERSION)
            st.rerun()

    show_gate_clearance_modal()

pages = [
    st.Page("pages/1_Dashboard.py", title="Dashboard", icon="📊", url_path="Decision-dashboard", default=True),
    st.Page("pages/2_Portfolio.py", title="Portfolio", icon="💼", url_path="Portfolio"),
    st.Page("pages/3_Company.py", title="Company", icon="🏢", url_path="Company"),
    st.Page("pages/4_Journal.py", title="Journal", icon="📝", url_path="Journal"),
    st.Page("pages/0_Watchlist.py", title="Watchlist", icon="⚙️", url_path="Watchlist"),
    st.Page("pages/5_Model_Tuning.py", title="Model tuning", icon="🧪", url_path="Model-tuning"),
]
navigation = st.navigation(pages, position="sidebar", expanded=False)
navigation.run()
