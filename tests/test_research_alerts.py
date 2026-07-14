from src.research_alerts import build_research_alerts


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
