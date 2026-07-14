from src.backtesting import latest_model_runs
from src.data.database import (
    get_backtest_runs, get_prediction_snapshots, save_backtest_run,
    save_prediction_snapshot, save_shadow_decision_snapshot,
)
from src.model_promotion import materialize_promoted_history
from src.model_registry import (
    coverage_aware_shadow_registration,
    build_prediction_snapshot, previous_live_model_registration, replay_prediction,
)
from src.shadow_model import build_shadow_snapshot


def test_promotion_materialization_is_additive_and_idempotent(tmp_path):
    database = tmp_path / "promotion.db"
    inputs = {
        "features": {"technical_score": 80, "valuation_score": 50, "risk_score": 60},
        "positioning_adjustments": {"entry_adjustment": 1, "exit_adjustment": 0},
        "temporal_coverage": {"fundamentals": "missing"},
    }
    outputs = {
        "entry_score": 67, "entry_signal": "Watch",
        "exit_score": 28, "exit_signal": "Hold / no review",
    }
    previous = previous_live_model_registration()
    prediction = build_prediction_snapshot(
        ticker="TEST", as_of_date="2026-02-16", model=previous,
        inputs=inputs, outputs=outputs,
    )
    save_prediction_snapshot(prediction, database)
    save_backtest_run({
        "ticker": "TEST", "as_of_date": "2026-02-16", "coverage": "Price-only reconstruction",
        "entry_score": 67, "exit_score": 28, "entry_signal": "Watch",
        "exit_signal": "Hold / no review", "technical_score": 80,
        "valuation_score": 50, "risk_score": 60, "outcome_1m": 4,
        "outcome_3m": 8, "outcome_6m": None, "outcome_12m": None,
        "inputs_json": "{}", "model_version": previous["model_version"],
        "simulation_source": "manual", "suggestion_rationale": None,
    }, database)
    save_shadow_decision_snapshot(build_shadow_snapshot(
        ticker="TEST", as_of_date="2026-02-16", surface="historical_replay",
        inputs={**inputs, "industry_calibrated": False}, current_outputs=outputs,
        current_model=previous, challenger_model=coverage_aware_shadow_registration(),
    ), database)

    first = materialize_promoted_history(database)
    second = materialize_promoted_history(database)

    assert first == {"predictions": 1, "runs": 1, "labels": 0, "eligible_pairs": 1}
    assert second == {"predictions": 0, "runs": 0, "labels": 0, "eligible_pairs": 1}
    assert len(get_prediction_snapshots("TEST", database)) == 2
    active = latest_model_runs(get_backtest_runs("TEST", database))[0]
    assert active["model_version"] == "coverage-aware-renormalized-v3-live"
    assert active["entry_score"] == 75.3
    promoted = next(
        row for row in get_prediction_snapshots("TEST", database)
        if row["model_version"] == "coverage-aware-renormalized-v3-live"
    )
    assert replay_prediction(promoted)["status"] == "exact_match"
