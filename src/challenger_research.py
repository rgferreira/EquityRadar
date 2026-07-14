"""Pre-registered offline challengers that cannot affect live decisions."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence

from src.model_registry import COVERAGE_AWARE_SHADOW_VERSION, canonical_json, content_hash
from src.outcome_labels import RELATIVE_LABEL_VERSION
from src.scoring.decision import entry_label


CHALLENGER_VERSION = COVERAGE_AWARE_SHADOW_VERSION
CONFIRMATION_DATES = ("2025-02-14", "2025-06-16", "2025-10-16", "2026-02-16")
CHALLENGER_CONFIG: dict[str, object] = {
    "challenger_version": CHALLENGER_VERSION,
    "purpose": "test whether unavailable valuation should stop diluting verified price evidence",
    "label_version": RELATIVE_LABEL_VERSION,
    "target_horizon": "3M",
    "confirmation_dates": list(CONFIRMATION_DATES),
    "minimum_independent_dates": 3,
    "weights_when_verified": {"technical": 0.50, "valuation": 0.30, "risk": 0.20},
    "weights_when_valuation_unavailable": {"technical": 5 / 7, "valuation": 0.0, "risk": 2 / 7},
    "positioning_policy": "preserve_frozen_entry_adjustment",
    "thresholds": {"buy_candidate": 70, "watch": 55},
    "watch_tolerance_pct": 3.0,
    "scientific_role": "offline_challenger_only",
}


def _decoded(value: object) -> dict[str, object]:
    if isinstance(value, str):
        return json.loads(value)
    return dict(value or {})


def coverage_aware_prediction(row: Mapping[str, object]) -> dict[str, object]:
    """Re-score frozen inputs without allowing missing valuation to become 50/100 evidence."""
    inputs = _decoded(row.get("input_json"))
    features = dict(inputs.get("features") or {})
    temporal = dict(inputs.get("temporal_coverage") or {})
    positioning = dict(inputs.get("positioning_adjustments") or {})
    technical = float(features["technical_score"])
    valuation = float(features["valuation_score"])
    risk = float(features["risk_score"])
    valuation_verified = temporal.get("fundamentals") == "verified_known_at"
    if valuation_verified:
        base = technical * 0.50 + valuation * 0.30 + risk * 0.20
        mode = "verified_full_composite"
    else:
        base = technical * (5 / 7) + risk * (2 / 7)
        mode = "valuation_unavailable_renormalized"
    score = round(max(0.0, min(100.0, base + float(positioning.get("entry_adjustment") or 0))), 1)
    return {"entry_score": score, "entry_signal": entry_label(score), "coverage_mode": mode}


def _observation(relative: float, signal: str, tolerance: float) -> tuple[float, float]:
    if signal == "Buy candidate":
        return relative, float(relative > 0)
    if signal == "Watch":
        return -abs(relative), float(abs(relative) <= tolerance)
    return -relative, float(relative <= 0)


def _cluster_interval(values: Mapping[str, list[float]]) -> dict[str, object]:
    means = [sum(group) / len(group) for group in values.values() if group]
    if not means:
        return {"estimate": None, "ci_low": None, "ci_high": None, "independent_dates": 0}
    estimate = sum(means) / len(means)
    if len(means) < 2:
        low = high = None
    else:
        variance = sum((value - estimate) ** 2 for value in means) / (len(means) - 1)
        margin = 1.96 * math.sqrt(variance / len(means))
        low, high = estimate - margin, estimate + margin
    return {"estimate": round(estimate, 6),
            "ci_low": round(low, 6) if low is not None else None,
            "ci_high": round(high, 6) if high is not None else None,
            "independent_dates": len(means)}


def evaluate_coverage_challenger(
    rows: Sequence[Mapping[str, object]], config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    settings = {**CHALLENGER_CONFIG, **dict(config or {})}
    allowed_dates = set(settings["confirmation_dates"])
    horizon = str(settings["target_horizon"])
    tolerance = float(settings["watch_tolerance_pct"])
    paired_utility: dict[str, list[float]] = defaultdict(list)
    paired_accuracy: dict[str, list[float]] = defaultdict(list)
    candidate_utility: dict[str, list[float]] = defaultdict(list)
    challenger_utility: dict[str, list[float]] = defaultdict(list)
    coverage_modes: dict[str, int] = defaultdict(int)
    used: list[dict[str, object]] = []
    for row in rows:
        decision_date = str(row["as_of_date"])
        if decision_date not in allowed_dates or row.get("label_status") != "available":
            continue
        outcomes = _decoded(row.get("outcomes_json") or row.get("outcomes"))
        outcome = outcomes.get(horizon)
        if not isinstance(outcome, dict) or outcome.get("relative_return_after_cost_pct") is None:
            continue
        relative = float(outcome["relative_return_after_cost_pct"])
        current = _decoded(row.get("output_json"))
        challenger = coverage_aware_prediction(row)
        current_result = _observation(relative, str(current.get("entry_signal") or "Wait"), tolerance)
        challenger_result = _observation(relative, str(challenger["entry_signal"]), tolerance)
        candidate_utility[decision_date].append(current_result[0])
        challenger_utility[decision_date].append(challenger_result[0])
        paired_utility[decision_date].append(challenger_result[0] - current_result[0])
        paired_accuracy[decision_date].append(challenger_result[1] - current_result[1])
        coverage_modes[str(challenger["coverage_mode"])] += 1
        used.append({"prediction_id": row["prediction_id"], "outcome_hash": row["outcome_hash"]})
    independent_dates = len(paired_utility)
    minimum = int(settings["minimum_independent_dates"])
    report: dict[str, object] = {
        "challenger_version": CHALLENGER_VERSION,
        "status": "evaluated" if independent_dates >= minimum else "insufficient_evidence",
        "reason": None if independent_dates >= minimum else f"requires {minimum} independent confirmation dates",
        "config": settings,
        "config_hash": content_hash(settings),
        "dataset_signature": content_hash(sorted(used, key=lambda item: item["prediction_id"])),
        "coverage": {"observations": len(used), "independent_dates": independent_dates,
                     "coverage_modes": dict(sorted(coverage_modes.items()))},
        "candidate_utility_pct": _cluster_interval(candidate_utility),
        "challenger_utility_pct": _cluster_interval(challenger_utility),
        "paired_utility_delta_pct": _cluster_interval(paired_utility),
        "paired_accuracy_delta": _cluster_interval(paired_accuracy),
        "promotion_decision": None,
        "scientific_note": "Pre-registered offline confirmation only; no live-model effect or alpha claim.",
    }
    report["report_hash"] = hashlib.sha256(canonical_json(report).encode()).hexdigest()
    report["experiment_id"] = hashlib.sha256(
        f"{report['config_hash']}|{report['dataset_signature']}".encode()
    ).hexdigest()
    return report
