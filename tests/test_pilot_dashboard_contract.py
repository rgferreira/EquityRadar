from pathlib import Path


def test_whaleseeker_and_pilot_sit_between_portfolio_and_watchlist():
    dashboard = Path("pages/1_Dashboard.py").read_text(encoding="utf-8")
    portfolio = dashboard.index('st.markdown("#### Portfolio actions")')
    whales = dashboard.rindex("render_whaleseeker_panel(frame")
    pilot = dashboard.rindex("render_pilot_decisions(frame)")
    watchlist = dashboard.index('st.markdown("#### Watchlist opportunities")')

    assert portfolio < whales < pilot < watchlist
    assert "0% applied Entry/Exit weight" in dashboard
    assert "Official column remains the decision authority" in dashboard
    assert "comparison only" in dashboard
    assert "PILOT_DECISIONS_ENABLED" in dashboard


def test_pilot_module_does_not_persist_shadow_observations_or_change_registry():
    source = Path("src/pilot_deployment.py").read_text(encoding="utf-8")

    assert "technology_potential_shadow_output" in source
    assert "save_shadow_decision_snapshot" not in source
    assert "persist_live_shadow_observation" not in source
    assert "set_active_model" not in source
    assert "register_model" not in source
