import json

import pytest

from src.data.database import (
    get_registered_models, get_shadow_decision_snapshots, save_prediction_snapshot,
    save_shadow_decision_snapshot,
)
from src.model_registry import build_prediction_snapshot, current_model_registration
from src.shadow_model import (
    backfill_shadow_history, build_shadow_snapshot, coverage_aware_shadow_output,
    meaningful_valuation_available, technology_potential_shadow_output,
)


CURRENT = {
    "entry_score": 66.0, "entry_signal": "Watch",
    "exit_score": 30.0, "exit_signal": "Hold / no review",
}


def inputs(**overrides):
    value = {
        "features": {"technical_score": 80, "valuation_score": 50, "risk_score": 60},
        "positioning_adjustments": {"entry_adjustment": 1, "exit_adjustment": 0},
        "valuation_available": False,
        "industry_calibrated": False,
    }
    value.update(overrides)
    return value


def test_missing_valuation_shadow_changes_only_candidate_output():
    original = dict(CURRENT)
    challenger = coverage_aware_shadow_output(inputs(), CURRENT)

    assert CURRENT == original
    assert challenger["entry_score"] == 75.3
    assert challenger["entry_signal"] == "Buy candidate"
    assert challenger["entry_score_delta"] == 9.3
    assert challenger["signal_changed"] is True


def test_verified_or_industry_calibrated_paths_do_not_invent_a_delta():
    verified = coverage_aware_shadow_output(inputs(valuation_available=True), CURRENT)
    industry = coverage_aware_shadow_output(inputs(industry_calibrated=True), CURRENT)

    assert verified["entry_score"] == 68.0
    assert verified["entry_signal"] == "Watch"
    assert industry["entry_score"] == CURRENT["entry_score"]
    assert industry["entry_signal"] == CURRENT["entry_signal"]
    assert industry["coverage_mode"] == "industry_calibrated_observation_only"


def test_meaningful_valuation_requires_a_positive_multiple():
    assert meaningful_valuation_available(None) is False
    assert meaningful_valuation_available({"forward_pe": None, "trailing_pe": -3}) is False
    assert meaningful_valuation_available({"price_to_sales_ttm": 4.2}) is True


def test_shadow_snapshot_is_immutable_and_models_remain_inactive(tmp_path):
    database = tmp_path / "shadow.db"
    snapshot = build_shadow_snapshot(
        ticker="SYNTH", as_of_date="2026-07-14", surface="test",
        inputs=inputs(), current_outputs=CURRENT,
    )
    save_shadow_decision_snapshot(snapshot, database)
    save_shadow_decision_snapshot(snapshot, database)
    stored = get_shadow_decision_snapshots("SYNTH", database)
    models = get_registered_models(database)

    assert len(stored) == 1
    assert json.loads(stored[0]["current_output_json"])["entry_score"] == 66.0
    assert json.loads(stored[0]["challenger_output_json"])["entry_score"] == 66.0
    assert sum(model["is_active"] for model in models) == 1
    assert next(model for model in models if model["model_version"] == "technology-potential-modifier-v1-shadow")["is_active"] == 0
    with pytest.raises(ValueError, match="Immutable shadow decision conflict"):
        save_shadow_decision_snapshot({**snapshot, "entry_score_delta": 99}, database)


def test_technology_modifier_is_bounded_confidence_gated_and_shadow_only():
    original = dict(CURRENT)
    challenger = technology_potential_shadow_output(inputs(technology_potential={
        "score": 90, "confidence": .75, "entry_modifier": 3.0, "coverage": "ready",
    }), CURRENT)

    assert CURRENT == original
    assert challenger["entry_score"] == 69.0
    assert challenger["technology_entry_modifier"] == 3.0
    assert challenger["coverage_mode"] == "technology_ready+daily_flow_unavailable"


def test_daily_short_flow_slope_is_additive_bounded_and_shadow_only():
    original = dict(CURRENT)
    challenger = technology_potential_shadow_output(inputs(
        technology_potential={
            "score": 90, "confidence": .75, "entry_modifier": 3.0, "coverage": "ready",
        },
        daily_short_flow={
            "slope_pp_per_session": .3, "confidence": .8,
            "entry_modifier": -1.5, "exit_modifier": 1.5, "coverage": "ready",
        },
    ), CURRENT)

    assert CURRENT == original
    assert challenger["entry_score"] == 67.5
    assert challenger["exit_score"] == 31.5
    assert challenger["technology_entry_modifier"] == 3.0
    assert challenger["daily_short_flow_entry_modifier"] == -1.5
    assert challenger["daily_short_flow_exit_modifier"] == 1.5


def test_promoted_shadow_backfill_is_archived(tmp_path):
    database = tmp_path / "backfill.db"
    model = current_model_registration()
    prediction = build_prediction_snapshot(
        ticker="SYNTH", as_of_date="2026-02-16", model=model,
        inputs=inputs(), outputs=CURRENT,
    )
    save_prediction_snapshot(prediction, database)

    first = backfill_shadow_history(database)
    second = backfill_shadow_history(database)

    assert first == {"attempted": 0, "created": 0, "signal_changes": 0}
    assert second == first
    assert get_shadow_decision_snapshots("SYNTH", database) == []
