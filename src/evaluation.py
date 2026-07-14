"""Offline purged rolling-origin evaluation of immutable predictions."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Mapping, Sequence

from src.model_registry import canonical_json, content_hash
from src.outcome_labels import RELATIVE_LABEL_VERSION


EVALUATOR_VERSION = "purged-rolling-origin-v1"
DEFAULT_EVALUATION_CONFIG: dict[str, object] = {
    "evaluator_version": EVALUATOR_VERSION,
    "label_version": RELATIVE_LABEL_VERSION,
    "target_horizon": "3M",
    "minimum_training_dates": 3,
    "minimum_test_dates": 3,
    "embargo_calendar_days": 5,
    "watch_tolerance_pct": 3.0,
    "confidence_level": 0.95,
    "baselines": ["base_score", "benchmark", "always_buy", "always_wait", "technical_momentum"],
}


def _json(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value


def _prepared_rows(
    rows: Sequence[Mapping[str, object]], config: Mapping[str, object],
) -> list[dict[str, object]]:
    horizon = str(config["target_horizon"])
    prepared: list[dict[str, object]] = []
    for source in rows:
        if source.get("label_version") != config["label_version"] or source.get("label_status") != "available":
            continue
        outcomes = _json(source.get("outcomes_json") or source.get("outcomes") or {})
        outcome = outcomes.get(horizon) if isinstance(outcomes, dict) else None
        if not isinstance(outcome, dict) or outcome.get("relative_return_after_cost_pct") is None:
            continue
        output = _json(source.get("output_json") or {})
        inputs = _json(source.get("input_json") or {})
        prepared.append({
            **dict(source),
            "as_of_date": str(source["as_of_date"]),
            "label_end_date": str(outcome["end_date"]),
            "relative_return": float(outcome["relative_return_after_cost_pct"]),
            "entry_signal": str(output.get("entry_signal") or "Wait"),
            "entry_score": float(output.get("entry_score") or 50),
            "technical_score": float((inputs.get("features") or {}).get("technical_score") or 50),
        })
    return sorted(prepared, key=lambda row: (row["as_of_date"], row["ticker"], row["prediction_id"]))


def build_purged_folds(
    rows: Sequence[Mapping[str, object]], config: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Build date-grouped folds whose training labels end before the embargo boundary."""
    settings = {**DEFAULT_EVALUATION_CONFIG, **dict(config or {})}
    prepared = _prepared_rows(rows, settings)
    dates = sorted({str(row["as_of_date"]) for row in prepared})
    minimum = int(settings["minimum_training_dates"])
    embargo = int(settings["embargo_calendar_days"])
    folds: list[dict[str, object]] = []
    for test_date in dates[minimum:]:
        embargo_boundary = date.fromisoformat(test_date) - timedelta(days=embargo)
        train = [
            row for row in prepared
            if row["as_of_date"] < test_date
            and date.fromisoformat(str(row["label_end_date"])) < embargo_boundary
        ]
        if len({str(row["as_of_date"]) for row in train}) < minimum:
            continue
        test = [row for row in prepared if row["as_of_date"] == test_date]
        folds.append({
            "test_date": test_date,
            "embargo_boundary": embargo_boundary.isoformat(),
            "train_prediction_ids": [row["prediction_id"] for row in train],
            "test_prediction_ids": [row["prediction_id"] for row in test],
        })
    return folds


def _policy_signal(row: Mapping[str, object], policy: str) -> str:
    if policy == "candidate":
        return str(row["entry_signal"])
    if policy == "base_score":
        score = float(row["entry_score"])
        return "Buy candidate" if score >= 70 else "Watch" if score >= 55 else "Wait"
    if policy == "always_buy":
        return "Buy candidate"
    if policy == "always_wait":
        return "Wait"
    if policy == "technical_momentum":
        return "Buy candidate" if float(row["technical_score"]) >= 70 else "Wait"
    raise ValueError(f"Unknown evaluation policy: {policy}")


def _observation(row: Mapping[str, object], policy: str, tolerance: float) -> dict[str, object]:
    relative = float(row["relative_return"])
    signal = _policy_signal(row, policy)
    if signal == "Buy candidate":
        utility, correct = relative, relative > 0
    elif signal == "Watch":
        utility, correct = -abs(relative), abs(relative) <= tolerance
    else:
        utility, correct = -relative, relative <= 0
    return {"utility": utility, "correct": float(correct), "signal": signal}


def _cluster_summary(values: Mapping[str, list[float]]) -> dict[str, object]:
    cluster_means = [sum(cluster) / len(cluster) for cluster in values.values() if cluster]
    if not cluster_means:
        return {"estimate": None, "ci_low": None, "ci_high": None, "independent_dates": 0}
    estimate = sum(cluster_means) / len(cluster_means)
    if len(cluster_means) < 2:
        low = high = None
    else:
        variance = sum((value - estimate) ** 2 for value in cluster_means) / (len(cluster_means) - 1)
        margin = 1.96 * math.sqrt(variance / len(cluster_means))
        low, high = estimate - margin, estimate + margin
    return {
        "estimate": round(estimate, 6),
        "ci_low": round(low, 6) if low is not None else None,
        "ci_high": round(high, 6) if high is not None else None,
        "independent_dates": len(cluster_means),
    }


def _policy_summary(rows: Sequence[Mapping[str, object]], policy: str, tolerance: float) -> dict[str, object]:
    utilities: dict[str, list[float]] = defaultdict(list)
    accuracy: dict[str, list[float]] = defaultdict(list)
    if policy == "benchmark":
        for row in rows:
            utilities[str(row["as_of_date"])].append(0.0)
        return {
            "observations": len(rows), "utility_pct": _cluster_summary(utilities),
            "accuracy": {"estimate": None, "ci_low": None, "ci_high": None,
                         "independent_dates": len(utilities)},
            "note": "The benchmark is the zero-relative-return reference; decision accuracy is not applicable.",
        }
    for row in rows:
        result = _observation(row, policy, tolerance)
        decision_date = str(row["as_of_date"])
        utilities[decision_date].append(float(result["utility"]))
        accuracy[decision_date].append(float(result["correct"]))
    return {
        "observations": len(rows),
        "utility_pct": _cluster_summary(utilities),
        "accuracy": _cluster_summary(accuracy),
    }


def evaluate_predictions(
    rows: Sequence[Mapping[str, object]], config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Evaluate candidate and frozen baselines on identical purged test windows."""
    settings = {**DEFAULT_EVALUATION_CONFIG, **dict(config or {})}
    prepared = _prepared_rows(rows, settings)
    folds = build_purged_folds(prepared, settings)
    test_ids = {prediction_id for fold in folds for prediction_id in fold["test_prediction_ids"]}
    test_rows = [row for row in prepared if row["prediction_id"] in test_ids]
    tolerance = float(settings["watch_tolerance_pct"])
    policies = ["candidate", *list(settings["baselines"])]
    summaries = {policy: _policy_summary(test_rows, policy, tolerance) for policy in policies}
    independent_dates = len({str(row["as_of_date"]) for row in test_rows})
    required = int(settings["minimum_test_dates"])
    ticker_rows: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in test_rows:
        ticker_rows[str(row["ticker"])].append(row)
    diagnostics = {
        ticker: _policy_summary(ticker_data, "candidate", tolerance)
        for ticker, ticker_data in sorted(ticker_rows.items())
    }
    dataset_signature = content_hash([{
        "prediction_id": row["prediction_id"], "outcome_hash": row.get("outcome_hash"),
    } for row in prepared])
    report: dict[str, object] = {
        "evaluator_version": EVALUATOR_VERSION,
        "status": "evaluated" if independent_dates >= required else "insufficient_evidence",
        "reason": None if independent_dates >= required else f"requires {required} independent test dates",
        "config": settings,
        "config_hash": content_hash(settings),
        "dataset_signature": dataset_signature,
        "coverage": {
            "input_rows": len(rows), "eligible_rows": len(prepared),
            "test_rows": len(test_rows), "independent_test_dates": independent_dates,
            "folds": len(folds),
        },
        "folds": folds,
        "policies": summaries,
        "ticker_diagnostics": diagnostics,
        "promotion_decision": None,
        "scientific_note": "Offline diagnostic only; no alpha or promotion claim.",
    }
    report["report_hash"] = hashlib.sha256(canonical_json(report).encode()).hexdigest()
    report["evaluation_id"] = hashlib.sha256(
        f"{report['config_hash']}|{dataset_signature}".encode()
    ).hexdigest()
    return report
