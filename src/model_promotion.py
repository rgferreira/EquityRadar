"""Additive materialization of the explicitly promoted coverage-aware policy."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from src.data.database import (
    get_backtest_runs, get_outcome_labels, get_prediction_snapshots,
    get_shadow_decision_snapshots, save_backtest_run, save_outcome_label,
    save_prediction_snapshot,
)
from src.model_registry import (
    COVERAGE_AWARE_SHADOW_VERSION, PREVIOUS_LIVE_MODEL_VERSION,
    build_prediction_snapshot, evidence_policy_previous_live_registration,
)
from src.outcome_labels import clone_outcome_label


def _key(row: Mapping[str, object]) -> tuple[str, str]:
    return str(row["ticker"]).upper(), str(row["as_of_date"])


def materialize_promoted_history(
    db_path: str | Path | None = None,
) -> dict[str, int]:
    """Create new-version predictions/runs without rewriting legacy or shadow evidence."""
    predictions = {
        (_key(row), str(row["model_version"])): row
        for row in get_prediction_snapshots(db_path=db_path)
    }
    runs = {
        (_key(row), str(row["model_version"])): row
        for row in get_backtest_runs(db_path=db_path)
    }
    labels = {
        str(row["prediction_id"]): row for row in get_outcome_labels(db_path=db_path)
    }
    model = evidence_policy_previous_live_registration()
    seen: set[tuple[str, str]] = set()
    created_predictions = created_runs = created_labels = 0
    for shadow in get_shadow_decision_snapshots(db_path=db_path):
        key = _key(shadow)
        if key in seen or str(shadow["challenger_model_version"]) != COVERAGE_AWARE_SHADOW_VERSION:
            continue
        if str(shadow["current_model_version"]) != PREVIOUS_LIVE_MODEL_VERSION:
            continue
        source_prediction = predictions.get((key, PREVIOUS_LIVE_MODEL_VERSION))
        source_run = runs.get((key, PREVIOUS_LIVE_MODEL_VERSION))
        if not source_prediction or not source_run:
            continue
        seen.add(key)
        outputs = json.loads(str(shadow["challenger_output_json"]))
        current_outputs = json.loads(str(shadow["current_output_json"]))
        outputs.setdefault("exit_score", current_outputs.get("exit_score"))
        outputs.setdefault("exit_signal", current_outputs.get("exit_signal"))
        snapshot = build_prediction_snapshot(
            ticker=key[0], as_of_date=key[1], model=model,
            inputs=json.loads(str(source_prediction["input_json"])), outputs=outputs,
            simulation_source=str(source_prediction.get("simulation_source") or "manual"),
            suggestion_rationale=source_prediction.get("suggestion_rationale"),
        )
        already = (key, str(model["model_version"])) in predictions
        save_prediction_snapshot(snapshot, db_path)
        created_predictions += int(not already)
        source_label = labels.get(str(source_prediction["prediction_id"]))
        if source_label:
            save_outcome_label(
                clone_outcome_label(source_label, prediction_id=str(snapshot["prediction_id"])),
                db_path,
            )
            created_labels += int(not already)
        promoted_run = {
            **source_run,
            "entry_score": outputs["entry_score"],
            "entry_signal": outputs["entry_signal"],
            "exit_score": outputs["exit_score"],
            "exit_signal": outputs["exit_signal"],
            "model_version": model["model_version"],
        }
        save_backtest_run(promoted_run, db_path)
        created_runs += int(not already)
    return {
        "predictions": created_predictions,
        "runs": created_runs,
        "labels": created_labels,
        "eligible_pairs": len(seen),
    }
