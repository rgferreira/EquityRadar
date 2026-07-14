import json

import pytest

from src.challenger_research import (
    CHALLENGER_CONFIG, CONFIRMATION_DATES, coverage_aware_prediction,
    evaluate_coverage_challenger,
)
from src.data.database import (
    get_challenger_experiments, get_registered_models, save_challenger_experiment,
)


def research_row(identifier, decision_date, relative, fundamentals="missing", signal="Watch"):
    return {
        "prediction_id": identifier, "ticker": "SYNTH", "as_of_date": decision_date,
        "label_status": "available", "outcome_hash": f"outcome-{identifier}",
        "input_json": json.dumps({
            "features": {"technical_score": 80, "valuation_score": 50, "risk_score": 60},
            "temporal_coverage": {"fundamentals": fundamentals},
            "positioning_adjustments": {"entry_adjustment": 1},
        }),
        "output_json": json.dumps({"entry_score": 66, "entry_signal": signal}),
        "outcomes_json": json.dumps({"3M": {
            "end_date": "2026-06-01", "relative_return_after_cost_pct": relative,
        }}),
    }


def test_verified_valuation_preserves_full_composite_and_positioning():
    prediction = coverage_aware_prediction(
        research_row("p1", CONFIRMATION_DATES[0], 5, "verified_known_at")
    )
    assert prediction == {
        "entry_score": 68.0, "entry_signal": "Watch", "coverage_mode": "verified_full_composite",
    }


def test_missing_valuation_is_removed_and_verified_weights_are_renormalized():
    prediction = coverage_aware_prediction(research_row("p2", CONFIRMATION_DATES[0], 5))
    assert prediction["entry_score"] == 75.3
    assert prediction["entry_signal"] == "Buy candidate"
    assert prediction["coverage_mode"] == "valuation_unavailable_renormalized"


def test_confirmation_is_date_clustered_deterministic_and_offline_only():
    rows = [
        research_row(f"p{index}", decision_date, 5 if index % 2 else -2)
        for index, decision_date in enumerate(CONFIRMATION_DATES, 1)
    ]
    rows += [research_row("same-date", CONFIRMATION_DATES[0], 4)]
    first = evaluate_coverage_challenger(rows)
    second = evaluate_coverage_challenger(list(reversed(rows)))

    assert first == second
    assert first["status"] == "evaluated"
    assert first["coverage"]["observations"] == 5
    assert first["coverage"]["independent_dates"] == 4
    assert first["paired_utility_delta_pct"]["independent_dates"] == 4
    assert first["promotion_decision"] is None


def test_non_preregistered_dates_cannot_enter_confirmation_set():
    report = evaluate_coverage_challenger([
        research_row("outside", "2025-08-01", 50),
        research_row("inside", CONFIRMATION_DATES[0], 5),
    ])
    assert report["coverage"]["observations"] == 1
    assert report["status"] == "insufficient_evidence"


def test_experiment_storage_is_immutable_and_cannot_promote(tmp_path):
    database = tmp_path / "challenger.db"
    report = evaluate_coverage_challenger([
        research_row(f"p{index}", decision_date, 5)
        for index, decision_date in enumerate(CONFIRMATION_DATES)
    ])
    before = get_registered_models(database)
    save_challenger_experiment(report, database)
    save_challenger_experiment(report, database)
    after = get_registered_models(database)
    assert len(get_challenger_experiments(database)) == 1
    assert [(row["model_version"], row["is_champion"]) for row in before] == [
        (row["model_version"], row["is_champion"]) for row in after
    ]
    with pytest.raises(ValueError, match="Immutable challenger experiment conflict"):
        save_challenger_experiment({**report, "report_hash": "changed"}, database)
