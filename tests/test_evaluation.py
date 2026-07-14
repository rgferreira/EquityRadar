import json

import pytest

from src.data.database import get_evaluation_runs, get_registered_models, save_evaluation_run
from src.evaluation import build_purged_folds, evaluate_predictions


def row(
    prediction_id, ticker, decision_date, end_date, relative_return,
    signal="Buy candidate", technical=75,
):
    return {
        "prediction_id": prediction_id,
        "ticker": ticker,
        "as_of_date": decision_date,
        "model_version": "test-model",
        "config_hash": "model-config",
        "output_json": json.dumps({"entry_signal": signal, "entry_score": 75}),
        "input_json": json.dumps({"features": {"technical_score": technical}}),
        "label_version": "benchmark-relative-v1",
        "label_status": "available",
        "outcomes_json": json.dumps({"3M": {
            "end_date": end_date,
            "relative_return_after_cost_pct": relative_return,
        }}),
        "outcome_hash": f"hash-{prediction_id}",
    }


def synthetic_rows():
    return [
        row("p1", "AAA", "2025-01-02", "2025-04-02", 4),
        row("p2", "AAA", "2025-02-03", "2025-05-05", -2),
        row("p3", "AAA", "2025-03-03", "2025-06-03", 3),
        row("p4", "AAA", "2025-07-01", "2025-10-01", 5),
        row("p5", "BBB", "2025-07-01", "2025-10-01", -1, "Wait", 40),
        row("p6", "AAA", "2025-11-03", "2026-02-03", 2),
        row("p7", "BBB", "2025-11-03", "2026-02-03", -3, "Wait", 45),
        row("p8", "AAA", "2026-03-02", "2026-06-02", 1),
        row("p9", "BBB", "2026-03-02", "2026-06-02", 2, "Wait", 45),
    ]


def config(**overrides):
    return {
        "minimum_training_dates": 2,
        "minimum_test_dates": 2,
        "embargo_calendar_days": 5,
        **overrides,
    }


def test_purge_and_embargo_remove_overlapping_training_labels():
    rows = synthetic_rows()
    folds = build_purged_folds(rows, config(minimum_training_dates=1))
    july = next(fold for fold in folds if fold["test_date"] == "2025-07-01")

    assert set(july["train_prediction_ids"]) == {"p1", "p2", "p3"}
    november = next(fold for fold in folds if fold["test_date"] == "2025-11-03")
    assert "p4" in november["train_prediction_ids"]
    assert all(identifier not in november["train_prediction_ids"] for identifier in ("p6", "p7"))


def test_same_date_predictions_are_one_independent_cluster_and_baselines_share_windows():
    report = evaluate_predictions(synthetic_rows(), config())
    coverage = report["coverage"]

    assert coverage["independent_test_dates"] == 3
    assert coverage["test_rows"] == 6
    assert report["policies"]["candidate"]["accuracy"]["independent_dates"] == 3
    assert {summary["observations"] for summary in report["policies"].values()} == {6}


def test_small_or_empty_samples_are_explicitly_insufficient():
    report = evaluate_predictions(synthetic_rows()[:4], config(minimum_test_dates=4))
    empty = evaluate_predictions([], config())

    assert report["status"] == "insufficient_evidence"
    assert report["reason"] == "requires 4 independent test dates"
    assert empty["status"] == "insufficient_evidence"
    assert empty["coverage"]["eligible_rows"] == 0


def test_config_and_dataset_produce_deterministic_report():
    first = evaluate_predictions(synthetic_rows(), config())
    second = evaluate_predictions(list(reversed(synthetic_rows())), config())

    assert first == second
    assert first["promotion_decision"] is None
    assert first["scientific_note"].startswith("Offline diagnostic")


def test_evaluation_registry_is_append_only_and_cannot_promote_model(tmp_path):
    database = tmp_path / "evaluation.db"
    report = evaluate_predictions(synthetic_rows(), config())
    before = get_registered_models(database)
    save_evaluation_run(report, database)
    save_evaluation_run(report, database)
    after = get_registered_models(database)

    assert len(get_evaluation_runs(database)) == 1
    assert [(model["model_version"], model["is_champion"]) for model in before] == [
        (model["model_version"], model["is_champion"]) for model in after
    ]
    with pytest.raises(ValueError, match="Immutable evaluation report conflict"):
        save_evaluation_run({**report, "report_hash": "different"}, database)
