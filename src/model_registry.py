"""Deterministic model identity and offline prediction replay."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping

from src.scoring.decision import (
    calculate_coverage_aware_entry_score, calculate_entry_score,
    calculate_exit_review_score, entry_label, exit_review_label,
)
from src.scoring.positioning import apply_positioning_adjustment


PREVIOUS_LIVE_MODEL_VERSION = "backtested-learning-v4-orthogonal-known-at-v1"
PREVIOUS_LIVE_MODEL_CONFIG: dict[str, object] = {
    "entry_model": "absolute-entry-v1",
    "exit_model": "technical-risk-exit-v1",
    "technical_features": "orthogonal-v4",
    "valuation": "transparent-absolute-v1",
    "positioning": "reliability-gated-v1",
    "temporal_policy": "verified-known-at-v1",
    "learning_policy": "diagnostic-only",
}

COVERAGE_AWARE_SHADOW_VERSION = "coverage-aware-renormalized-v1"
COVERAGE_AWARE_SHADOW_CONFIG: dict[str, object] = {
    "entry_model": "coverage-aware-renormalized-v1",
    "verified_weights": {"technical": 0.50, "valuation": 0.30, "risk": 0.20},
    "missing_valuation_weights": {"technical": 5 / 7, "valuation": 0.0, "risk": 2 / 7},
    "industry_calibrated_policy": "observe_current_score_unchanged",
    "positioning": "preserve_frozen_entry_adjustment",
    "thresholds": {"buy_candidate": 70, "watch": 55},
    "role": "inactive_shadow_only",
}

CURRENT_MODEL_VERSION = "coverage-aware-renormalized-v3-live"
COVERAGE_AWARE_PROMOTED = True
CURRENT_MODEL_CONFIG: dict[str, object] = {
    **COVERAGE_AWARE_SHADOW_CONFIG,
    "role": "live_champion",
    "promoted_from": COVERAGE_AWARE_SHADOW_VERSION,
    "previous_live": PREVIOUS_LIVE_MODEL_VERSION,
    "promotion_evidence": {
        "paired_3m_observations": 378,
        "live_accuracy_pct": 43.12,
        "shadow_accuracy_pct": 46.83,
        "gates_passed": 6,
        "gates_total": 6,
        "manual_override": None,
    },
}


def canonical_json(value: Mapping[str, object] | list[object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_hash(value: Mapping[str, object] | list[object]) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def current_model_registration() -> dict[str, object]:
    return {
        "model_version": CURRENT_MODEL_VERSION,
        "config_json": canonical_json(CURRENT_MODEL_CONFIG),
        "config_hash": content_hash(CURRENT_MODEL_CONFIG),
        "status": "champion",
        "is_active": 1,
        "is_champion": 1,
    }


def previous_live_model_registration() -> dict[str, object]:
    return {
        "model_version": PREVIOUS_LIVE_MODEL_VERSION,
        "config_json": canonical_json(PREVIOUS_LIVE_MODEL_CONFIG),
        "config_hash": content_hash(PREVIOUS_LIVE_MODEL_CONFIG),
        "status": "retired",
        "is_active": 0,
        "is_champion": 0,
    }


def coverage_aware_shadow_registration() -> dict[str, object]:
    return {
        "model_version": COVERAGE_AWARE_SHADOW_VERSION,
        "config_json": canonical_json(COVERAGE_AWARE_SHADOW_CONFIG),
        "config_hash": content_hash(COVERAGE_AWARE_SHADOW_CONFIG),
        "status": "candidate",
        "is_active": 0,
        "is_champion": 0,
    }


def prediction_identity(ticker: str, as_of_date: str, model_version: str, config_hash: str) -> str:
    identity = f"{ticker.strip().upper()}|{as_of_date}|{model_version}|{config_hash}"
    return hashlib.sha256(identity.encode()).hexdigest()


def build_prediction_snapshot(
    *, ticker: str, as_of_date: str, model: Mapping[str, object],
    inputs: Mapping[str, object], outputs: Mapping[str, object],
    simulation_source: str = "manual", suggestion_rationale: str | None = None,
) -> dict[str, object]:
    input_hash = content_hash(dict(inputs))
    output_hash = content_hash(dict(outputs))
    config_hash = str(model["config_hash"])
    model_version = str(model["model_version"])
    return {
        "prediction_id": prediction_identity(ticker, as_of_date, model_version, config_hash),
        "input_snapshot_id": input_hash,
        "input_json": canonical_json(dict(inputs)),
        "input_hash": input_hash,
        "ticker": ticker.strip().upper(),
        "as_of_date": as_of_date,
        "model_version": model_version,
        "config_hash": config_hash,
        "output_json": canonical_json(dict(outputs)),
        "output_hash": output_hash,
        "simulation_source": simulation_source,
        "suggestion_rationale": suggestion_rationale,
    }


def replay_prediction(snapshot: Mapping[str, object], tolerance: float = 1e-9) -> dict[str, object]:
    """Recompute a frozen score snapshot and report exact structured differences."""
    inputs = json.loads(str(snapshot["input_json"]))
    expected = json.loads(str(snapshot["output_json"]))
    features = inputs["features"]
    technical = float(features["technical_score"])
    valuation = float(features["valuation_score"])
    risk = float(features["risk_score"])
    positioning = inputs.get("positioning_adjustments") or {}
    promoted = str(snapshot.get("model_version")) == CURRENT_MODEL_VERSION
    base_entry = (
        calculate_coverage_aware_entry_score(
            technical, valuation, risk,
            valuation_available=(inputs.get("temporal_coverage") or {}).get("fundamentals") == "verified_known_at",
        ) if promoted else calculate_entry_score(technical, valuation, risk)
    )
    entry = apply_positioning_adjustment(
        base_entry,
        float(positioning.get("entry_adjustment") or 0),
    )
    exit_score = apply_positioning_adjustment(
        calculate_exit_review_score(technical, risk),
        float(positioning.get("exit_adjustment") or 0),
    )
    actual = {
        "entry_score": entry,
        "exit_score": exit_score,
        "entry_signal": entry_label(entry),
        "exit_signal": exit_review_label(exit_score),
    }
    differences: dict[str, dict[str, object]] = {}
    for field, actual_value in actual.items():
        expected_value = expected.get(field)
        if isinstance(actual_value, (int, float)) and isinstance(expected_value, (int, float)):
            matches = abs(float(actual_value) - float(expected_value)) <= tolerance
        else:
            matches = actual_value == expected_value
        if not matches:
            differences[field] = {"expected": expected_value, "actual": actual_value}
    return {
        "prediction_id": snapshot.get("prediction_id"),
        "status": "exact_match" if not differences else "mismatch",
        "matches": not differences,
        "differences": differences,
        "actual": actual,
    }
