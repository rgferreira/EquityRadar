from src.research_alerts import build_research_alerts
from src.research_alerts import finra_reversal_alerts, provider_recovery_alerts, score_boundary_alerts


def test_alerts_require_a_category_change_not_price_noise():
    unchanged = [
        {"ticker": "AAA", "as_of_date": "2026-01-01", "entry_signal": "Watch", "exit_signal": "Hold"},
        {"ticker": "AAA", "as_of_date": "2026-02-01", "entry_signal": "Watch", "exit_signal": "Hold"},
    ]
    assert build_research_alerts(unchanged) == []
    changed = unchanged + [
        {"ticker": "AAA", "as_of_date": "2026-03-01", "entry_signal": "Buy candidate", "exit_signal": "Hold"},
    ]
    alerts = build_research_alerts(changed)
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "diagnostic_change"


def test_matured_outcome_creates_informational_alert():
    runs = [{
        "ticker": "AAA", "as_of_date": "2026-01-01", "entry_signal": "Watch", "exit_signal": "Hold",
        "outcome_3m": 4.2, "outcome_refreshed_at": "2026-04-02", "model_version": "v1",
        "simulation_source": "manual",
    }]
    alerts = build_research_alerts(runs)
    assert alerts[0]["severity"] == "info"


def test_score_boundary_crossing_is_explicit():
    runs = [
        {"ticker": "AAA", "as_of_date": "2026-01-01", "entry_score": 69, "exit_score": 49},
        {"ticker": "AAA", "as_of_date": "2026-02-01", "entry_score": 71, "exit_score": 51},
    ]
    alerts = score_boundary_alerts(runs)
    assert len(alerts) == 1
    assert "Entry crossed above 70" in alerts[0]["detail"]
    assert "Exit review crossed above 50" in alerts[0]["detail"]


def test_finra_reversal_requires_material_sign_flip():
    histories = {"AAA": [
        {"snapshot_type": "historical_short_interest", "snapshot_date": "2026-01-01", "short": {"short_change_pct": 8}},
        {"snapshot_type": "historical_short_interest", "snapshot_date": "2026-02-01", "short": {"short_change_pct": -6}},
    ]}
    alerts = finra_reversal_alerts(histories)
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "finra_reversal"


def test_provider_recovery_requires_failed_to_healthy_transition():
    alerts = provider_recovery_alerts([{
        "provider_key": "market_price", "ticker": "AAA", "previous_status": "failed",
        "new_status": "healthy", "occurred_at": "2026-07-14 12:00:00",
    }])
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "info"
