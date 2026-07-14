import json

import pandas as pd
import pytest

from src.backtesting import latest_model_runs
from src.data.database import (
    get_prediction_snapshots,
    get_backtest_runs,
    get_registered_models,
    init_db,
    register_model,
    save_prediction_snapshot,
    set_active_model,
)
from src.data.backtest_refresh import _run
from src.model_registry import (
    build_prediction_snapshot,
    content_hash,
    current_model_registration,
    replay_prediction,
)
from src.scoring.decision import calculate_entry_score, calculate_exit_review_score, entry_label, exit_review_label


def sample_snapshot():
    model = current_model_registration()
    inputs = {
        "features": {"technical_score": 70, "valuation_score": 60, "risk_score": 80},
        "positioning_adjustments": {"entry_adjustment": 1.5, "exit_adjustment": -2.0},
        "temporal_coverage": {"price": "end_of_day_cutoff", "fundamentals": "missing", "finra": "missing"},
        "input_references": {"prices": {"cutoff": "2026-05-08", "observations": 253}},
    }
    entry = min(100, calculate_entry_score(70, 60, 80) + 1.5)
    exit_score = max(0, calculate_exit_review_score(70, 80) - 2.0)
    outputs = {
        "entry_score": entry, "exit_score": exit_score,
        "entry_signal": entry_label(entry), "exit_signal": exit_review_label(exit_score),
    }
    return build_prediction_snapshot(
        ticker="TEST", as_of_date="2026-05-08", model=model, inputs=inputs, outputs=outputs,
    )


def test_registry_seeds_active_candidate_without_claiming_champion(tmp_path):
    database = tmp_path / "registry.db"
    init_db(database)
    init_db(database)
    models = get_registered_models(database)

    assert len(models) == 1
    assert models[0]["status"] == "candidate"
    assert models[0]["is_active"] == 1
    assert models[0]["is_champion"] == 0


def test_arbitrary_model_name_cannot_override_registry_activity(tmp_path):
    database = tmp_path / "registry.db"
    init_db(database)
    challenger_config = {"purpose": "test challenger"}
    challenger = {
        "model_version": "zzzz-9999",
        "config_json": json.dumps(challenger_config, sort_keys=True, separators=(",", ":")),
        "config_hash": content_hash(challenger_config),
        "status": "candidate", "is_active": 0, "is_champion": 0,
    }
    register_model(challenger, database)
    rows = [
        {"id": 50, "ticker": "TEST", "as_of_date": "2026-01-01", "model_version": "zzzz-9999", "model_is_active": 0},
        {"id": 1, "ticker": "TEST", "as_of_date": "2026-01-01", "model_version": "registered-active", "model_is_active": 1},
    ]

    assert latest_model_runs(rows)[0]["model_version"] == "registered-active"
    set_active_model("zzzz-9999", champion=True, db_path=database)
    selected = next(model for model in get_registered_models(database) if model["model_version"] == "zzzz-9999")
    assert selected["is_active"] == 1
    assert selected["is_champion"] == 1
    assert selected["status"] == "champion"


def test_prediction_snapshot_is_idempotent_and_immutable(tmp_path):
    database = tmp_path / "registry.db"
    snapshot = sample_snapshot()
    save_prediction_snapshot(snapshot, database)
    save_prediction_snapshot(snapshot, database)
    assert len(get_prediction_snapshots("TEST", database)) == 1

    changed = {**snapshot, "output_json": snapshot["output_json"].replace('"entry_score":', '"entry_score":999,"old":')}
    with pytest.raises(ValueError, match="Immutable prediction snapshot conflict"):
        save_prediction_snapshot(changed, database)
    assert get_prediction_snapshots("TEST", database)[0]["output_json"] == snapshot["output_json"]


def test_replay_reports_exact_match_and_structured_mismatch():
    snapshot = sample_snapshot()
    exact = replay_prediction(snapshot)
    assert exact["status"] == "exact_match"
    assert exact["differences"] == {}

    expected = json.loads(snapshot["output_json"])
    expected["entry_score"] += 1
    mismatch = replay_prediction({**snapshot, "output_json": json.dumps(expected)})
    assert mismatch["status"] == "mismatch"
    assert mismatch["differences"]["entry_score"]["expected"] == expected["entry_score"]


def test_registering_same_version_with_different_config_is_rejected(tmp_path):
    database = tmp_path / "registry.db"
    model = current_model_registration()
    init_db(database)
    with pytest.raises(ValueError, match="different configuration"):
        register_model({**model, "config_hash": "different"}, database)


def test_simulation_worker_writes_replayable_immutable_prediction(tmp_path, monkeypatch):
    database = tmp_path / "registry.db"
    history = pd.DataFrame(
        {"Close": [100 + index * .25 for index in range(420)]},
        index=pd.date_range("2025-01-02", periods=420, freq="B"),
    )
    monkeypatch.setattr("src.data.backtest_refresh.fetch_price_history", lambda *args, **kwargs: history)

    _run("2026-05-08", ["TEST"], database, "suggested", "Synthetic regime transition")

    snapshots = get_prediction_snapshots("TEST", database)
    assert len(snapshots) == 1
    assert snapshots[0]["model_status"] == "candidate"
    assert snapshots[0]["is_active"] == 1
    assert replay_prediction(snapshots[0])["status"] == "exact_match"
    compatibility = get_backtest_runs("TEST", database)[0]
    assert compatibility["has_prediction_snapshot"] == 1


def test_unregistered_legacy_run_remains_explicit_compatibility_data(tmp_path):
    from src.data.database import save_backtest_run

    database = tmp_path / "registry.db"
    legacy = {
        "ticker": "OLD", "as_of_date": "2025-01-01", "coverage": "Price-only reconstruction",
        "entry_score": 50, "exit_score": 50, "entry_signal": "Watch", "exit_signal": "Reassess",
        "technical_score": 50, "valuation_score": 50, "risk_score": 50,
        "outcome_1m": None, "outcome_3m": None, "outcome_6m": None, "outcome_12m": None,
        "inputs_json": "{}", "model_version": "legacy-unregistered-v99",
    }
    save_backtest_run(legacy, database)
    init_db(database)
    row = get_backtest_runs("OLD", database)[0]

    assert row["model_registry_status"] == "legacy_unregistered"
    assert row["has_prediction_snapshot"] == 0
    assert row["entry_score"] == 50
