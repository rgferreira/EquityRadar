from src.data.database import (
    get_pilot_deployment,
    get_registered_models,
    get_shadow_decision_snapshots,
)
from src.model_registry import technology_potential_shadow_registration
from src.pilot_deployment import (
    PILOT_DEPLOYMENT_KEY,
    PILOT_SURFACE,
    build_pilot_comparison,
    build_pilot_decision,
    pilot_deployment_state,
    pilot_maturity_summary,
    pilot_runtime_enabled,
    set_pilot_opt_in,
)
from src.shadow_model import technology_potential_shadow_output


def test_pilot_opt_in_persists_without_touching_model_or_shadow_registries(tmp_path, monkeypatch):
    database = tmp_path / "pilot.db"
    monkeypatch.delenv("PILOT_DECISIONS_ENABLED", raising=False)
    initial_state = pilot_deployment_state(database)
    models_before = get_registered_models(database)
    shadows_before = get_shadow_decision_snapshots(db_path=database)

    enabled = set_pilot_opt_in(True, database)

    assert initial_state["persisted_opt_in"] is False
    assert enabled["persisted_opt_in"] is True
    assert enabled["effective_enabled"] is True
    assert enabled["official_decision_authority"] is False
    assert get_registered_models(database) == models_before
    assert get_shadow_decision_snapshots(db_path=database) == shadows_before


def test_runtime_kill_switch_overrides_persisted_opt_in(tmp_path):
    database = tmp_path / "pilot-kill-switch.db"
    set_pilot_opt_in(True, database)

    disabled = pilot_deployment_state(
        database, environment={"PILOT_DECISIONS_ENABLED": "false"},
    )

    assert disabled["persisted_opt_in"] is True
    assert disabled["runtime_enabled"] is False
    assert disabled["effective_enabled"] is False
    assert pilot_runtime_enabled({"PILOT_DECISIONS_ENABLED": "0"}) is False
    assert pilot_runtime_enabled({}) is True


def test_pilot_calculation_is_the_exact_registered_shadow_transformation():
    current = {
        "entry_score": 68.0,
        "entry_signal": "Watch",
        "exit_score": 42.0,
        "exit_signal": "Hold",
    }
    technology = {"score": 80.0, "confidence": 1.0, "entry_modifier": 3.0, "coverage": "ready"}
    flow = {
        "confidence": 1.0,
        "entry_modifier": -1.5,
        "exit_modifier": 1.5,
        "slope_pp_per_session": 0.2,
        "coverage": "ready",
    }

    expected = technology_potential_shadow_output(
        {"technology_potential": technology, "daily_short_flow": flow}, current,
    )
    actual = build_pilot_decision(
        current, technology_evidence=technology, daily_flow_evidence=flow,
    )
    comparison = build_pilot_comparison(
        " nvda ", current, technology_evidence=technology, daily_flow_evidence=flow,
    )

    assert actual == expected
    assert comparison["Ticker"] == "NVDA"
    assert comparison["Official"] == "Watch"
    assert comparison["Pilot"] == expected["entry_signal"]
    assert comparison["Pilot score"] == expected["entry_score"]
    assert comparison["Technology adj"] == 3.0
    assert comparison["Daily flow adj"] == -1.5


def test_pilot_deployment_identity_and_empty_maturity_are_explicit(tmp_path):
    database = tmp_path / "pilot-empty.db"
    registration = technology_potential_shadow_registration()
    deployment = get_pilot_deployment(
        PILOT_DEPLOYMENT_KEY,
        candidate_model_version=str(registration["model_version"]),
        surface=PILOT_SURFACE,
        db_path=database,
    )
    maturity = pilot_maturity_summary(database)

    assert deployment["mode"] == "comparison_only"
    assert deployment["user_opt_in"] == 0
    assert maturity["candidate_model_version"] == registration["model_version"]
    assert maturity["pipeline_progress_pct"] == 0
    assert maturity["gate_status"] == "Collecting evidence"
    assert maturity["next_maturity_date"] is None
