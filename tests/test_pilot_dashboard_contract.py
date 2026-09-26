from pathlib import Path


def test_decisions_precede_optional_whaleseeker_and_pilot_research():
    dashboard = Path("pages/1_Dashboard.py").read_text(encoding="utf-8")
    portfolio = dashboard.index('st.markdown("#### Portfolio actions")')
    whales = dashboard.rindex("render_whaleseeker_panel(frame")
    pilot = dashboard.rindex("render_pilot_decisions(frame)")
    watchlist = dashboard.index('st.markdown("#### Watchlist opportunities")')

    assert portfolio < watchlist < whales < pilot
    assert 'if research_panel.open:' in dashboard
    assert "0% applied Entry/Exit weight" in dashboard
    assert "Official column remains the decision authority" in dashboard
    assert "comparison only" in dashboard
    assert "PILOT_DECISIONS_ENABLED" in dashboard


def test_whaleseeker_dashboard_table_has_filter_sort_and_descriptive_return_contract():
    dashboard = Path("pages/1_Dashboard.py").read_text(encoding="utf-8")
    whales = Path("src/whaleseeker.py").read_text(encoding="utf-8")

    assert 'options=("All", "Purchase", "Sale")' in dashboard
    assert 'options=("All disclosures", "Portfolio & Watchlist")' in dashboard
    assert 'default="All disclosures"' in dashboard
    assert "@st.fragment\ndef render_whaleseeker_panel" in dashboard
    panel = dashboard[dashboard.index("@st.fragment\ndef render_whaleseeker_panel"):]
    assert panel.count('width="stretch"') >= 2
    assert '"Trade": st.column_config.TextColumn(width=90)' in panel
    assert "filter_column, scope_column = st.columns(2)" not in panel
    assert "normalize_trade_filter" in dashboard
    assert "empty_disclosure_message" in dashboard
    assert '"Ticker", "Asset", "Since trade %", "Trade", "Traded"' in dashboard
    assert "GOOGL is not rewritten as GOOG" in dashboard
    assert "add_since_trade_returns" in dashboard
    assert "not the politician's execution price or a copyable return" in dashboard
    assert 'order_by="trade"' in whales


def test_whaleseeker_page_uses_the_same_trade_table_contract():
    page = Path("pages/8_WhaleSeeker.py").read_text(encoding="utf-8")

    assert 'options=("All", "Purchase", "Sale")' in page
    assert "normalize_trade_filter" in page
    assert "empty_disclosure_message" in page
    assert '"Trade": st.column_config.TextColumn(width=90)' in page
    assert 'order_by="trade"' in page
    assert '"Ticker", "Asset", "Ticker quality", "Since trade %", "Trade", "Traded"' in page
    assert "GOOGL is not rewritten as GOOG" in page
    assert "add_since_trade_returns" in page
    assert "not the politician's execution price or a copyable return" in page


def test_pilot_module_does_not_persist_shadow_observations_or_change_registry():
    source = Path("src/pilot_deployment.py").read_text(encoding="utf-8")

    assert "technology_potential_shadow_output" in source
    assert "save_shadow_decision_snapshot" not in source
    assert "persist_live_shadow_observation" not in source
    assert "set_active_model" not in source
    assert "register_model" not in source
