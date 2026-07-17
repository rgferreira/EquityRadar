"""Read-only live-versus-shadow evidence summaries for Phase 3.9."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date


MIN_MATURED_DATES = 10
MIN_CHANGED_DATES = 5
MIN_POSITIVE_DATE_SHARE = 0.60
MAX_TICKER_CONCENTRATION = 0.35
WATCH_TOLERANCE_PCT = 3.0
THREE_MONTH_MATURITY_DAYS = 92
PROMOTION_BASELINE = {
    "observations": 378,
    "independent_dates": 21,
    "accuracy_pct": 46.83,
    "former_live_accuracy_pct": 43.12,
}


def _json(value: object) -> dict[str, object]:
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return dict(value) if isinstance(value, Mapping) else {}


def _policy_result(signal: str, relative_return: float) -> tuple[float, float]:
    if signal == "Buy candidate":
        return relative_return, float(relative_return > 0)
    if signal == "Watch":
        return -abs(relative_return), float(abs(relative_return) <= WATCH_TOLERANCE_PCT)
    return -relative_return, float(relative_return <= 0)


def _cluster_summary(values: Mapping[str, Sequence[float]]) -> dict[str, object]:
    means = [sum(items) / len(items) for items in values.values() if items]
    if not means:
        return {"estimate": None, "ci_low": None, "ci_high": None, "independent_dates": 0}
    estimate = sum(means) / len(means)
    if len(means) < 2:
        low = high = None
    else:
        variance = sum((value - estimate) ** 2 for value in means) / (len(means) - 1)
        margin = 1.96 * math.sqrt(variance / len(means))
        low, high = estimate - margin, estimate + margin
    return {
        "estimate": round(estimate, 6),
        "ci_low": round(low, 6) if low is not None else None,
        "ci_high": round(high, 6) if high is not None else None,
        "independent_dates": len(means),
    }


def _technical_regime(inputs: Mapping[str, object]) -> str:
    technical = float((_json(inputs.get("features"))).get("technical_score") or 50)
    if technical >= 70:
        return "Strong technical"
    if technical < 45:
        return "Weak technical"
    return "Mixed technical"


def _prediction_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (
        str(row["ticker"]).upper(), str(row["as_of_date"]),
        str(row["model_version"]), str(row["config_hash"]),
    )


def prepare_shadow_comparisons(
    shadows: Sequence[Mapping[str, object]],
    predictions: Sequence[Mapping[str, object]],
    labels: Sequence[Mapping[str, object]],
    *, horizon: str = "3M",
) -> list[dict[str, object]]:
    """Join immutable shadow observations to versioned relative outcomes."""
    prediction_index = {_prediction_key(row): row for row in predictions}
    label_index = {str(row["prediction_id"]): row for row in labels}
    comparisons: list[dict[str, object]] = []
    frozen_daily: dict[tuple[str, str, str, str, str, str], Mapping[str, object]] = {}
    for shadow in sorted(
        shadows, key=lambda row: (str(row.get("created_at") or ""), str(row["shadow_snapshot_id"])),
    ):
        daily_key = (
            str(shadow["ticker"]).upper(), str(shadow["as_of_date"]),
            str(shadow["current_model_version"]), str(shadow["current_config_hash"]),
            str(shadow["challenger_model_version"]), str(shadow["challenger_config_hash"]),
        )
        frozen_daily.setdefault(daily_key, shadow)
    for shadow in frozen_daily.values():
        current = _json(shadow.get("current_output_json"))
        challenger = _json(shadow.get("challenger_output_json"))
        inputs = _json(shadow.get("input_json"))
        key = (
            str(shadow["ticker"]).upper(), str(shadow["as_of_date"]),
            str(shadow["current_model_version"]), str(shadow["current_config_hash"]),
        )
        prediction = prediction_index.get(key)
        label = label_index.get(str(prediction["prediction_id"])) if prediction else None
        outcome = None
        if label and label.get("status") == "available":
            candidate = _json(label.get("outcomes_json") or label.get("outcomes")).get(horizon)
            outcome = candidate if isinstance(candidate, Mapping) else None
        relative = outcome.get("relative_return_after_cost_pct") if outcome else None
        live_signal = str(current.get("entry_signal") or "Wait")
        shadow_signal = str(challenger.get("entry_signal") or "Wait")
        live_utility = shadow_utility = live_correct = shadow_correct = None
        if isinstance(relative, (int, float)):
            live_utility, live_correct = _policy_result(live_signal, float(relative))
            shadow_utility, shadow_correct = _policy_result(shadow_signal, float(relative))
        comparisons.append({
            "shadow_snapshot_id": shadow["shadow_snapshot_id"],
            "ticker": str(shadow["ticker"]).upper(),
            "as_of_date": str(shadow["as_of_date"]),
            "surface": str(shadow["surface"]),
            "simulation_source": str(prediction.get("simulation_source") or "live") if prediction else "live",
            "coverage_mode": str(shadow["coverage_mode"]),
            "technical_regime": _technical_regime(inputs),
            "live_score": float(current.get("entry_score") or 0),
            "shadow_score": float(challenger.get("entry_score") or 0),
            "score_delta": float(shadow["entry_score_delta"]),
            "live_signal": live_signal,
            "shadow_signal": shadow_signal,
            "signal_changed": bool(shadow["signal_changed"]),
            "label_status": (
                str(label.get("status")) if label else
                "awaiting_outcome" if prediction else "prediction_not_linked"
            ),
            "outcome_end_date": str(outcome.get("end_date")) if outcome else None,
            "relative_return_pct": float(relative) if isinstance(relative, (int, float)) else None,
            "live_utility_pct": live_utility,
            "shadow_utility_pct": shadow_utility,
            "utility_delta_pct": (
                shadow_utility - live_utility
                if shadow_utility is not None and live_utility is not None else None
            ),
            "live_correct": live_correct,
            "shadow_correct": shadow_correct,
            "accuracy_delta": (
                shadow_correct - live_correct
                if shadow_correct is not None and live_correct is not None else None
            ),
            "max_drawdown_6m_pct": (
                float(label["max_drawdown_6m_pct"])
                if label and label.get("max_drawdown_6m_pct") is not None else None
            ),
        })
    return sorted(comparisons, key=lambda row: (str(row["as_of_date"]), str(row["ticker"])))


def _paired_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    matured = [row for row in rows if row.get("utility_delta_pct") is not None]
    utility: dict[str, list[float]] = defaultdict(list)
    accuracy: dict[str, list[float]] = defaultdict(list)
    live: dict[str, list[float]] = defaultdict(list)
    shadow: dict[str, list[float]] = defaultdict(list)
    for row in matured:
        decision_date = str(row["as_of_date"])
        utility[decision_date].append(float(row["utility_delta_pct"]))
        accuracy[decision_date].append(float(row["accuracy_delta"]))
        live[decision_date].append(float(row["live_utility_pct"]))
        shadow[decision_date].append(float(row["shadow_utility_pct"]))
    return {
        "observations": len(matured),
        "utility_delta_pct": _cluster_summary(utility),
        "accuracy_delta": _cluster_summary(accuracy),
        "live_utility_pct": _cluster_summary(live),
        "shadow_utility_pct": _cluster_summary(shadow),
    }


def _grouped(rows: Sequence[Mapping[str, object]], field: str) -> list[dict[str, object]]:
    groups: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row[field])].append(row)
    result = []
    for name, group in sorted(groups.items()):
        paired = _paired_summary(group)
        result.append({
            field: name,
            "snapshots": len(group),
            "matured": paired["observations"],
            "independent_dates": paired["utility_delta_pct"]["independent_dates"],
            "signal_changes": sum(bool(row["signal_changed"]) for row in group),
            "mean_score_delta": round(sum(float(row["score_delta"]) for row in group) / len(group), 2),
            "utility_delta_pct": paired["utility_delta_pct"]["estimate"],
            "accuracy_delta_pp": (
                round(float(paired["accuracy_delta"]["estimate"]) * 100, 2)
                if paired["accuracy_delta"]["estimate"] is not None else None
            ),
        })
    return result


def build_model_tuning_report(
    rows: Sequence[Mapping[str, object]], *, today: date | None = None,
) -> dict[str, object]:
    """Summarize accumulated evidence without making a promotion decision."""
    report_date = today or date.today()
    records = list(rows)
    matured = [row for row in records if row.get("utility_delta_pct") is not None]
    changed = [row for row in records if bool(row.get("signal_changed"))]
    changed_matured = [row for row in matured if bool(row.get("signal_changed"))]
    all_paired = _paired_summary(matured)
    changed_paired = _paired_summary(changed_matured)
    matured_dates = len({str(row["as_of_date"]) for row in matured})
    changed_dates = len({str(row["as_of_date"]) for row in changed_matured})
    lower = changed_paired["utility_delta_pct"]["ci_low"]
    accuracy = changed_paired["accuracy_delta"]["estimate"]
    changed_by_date: dict[str, list[float]] = defaultdict(list)
    for row in changed_matured:
        changed_by_date[str(row["as_of_date"])].append(float(row["utility_delta_pct"]))
    date_deltas = [sum(values) / len(values) for values in changed_by_date.values()]
    positive_date_share = (
        sum(value > 0 for value in date_deltas) / len(date_deltas) if date_deltas else None
    )
    ticker_counts = Counter(str(row["ticker"]) for row in changed_matured)
    ticker_concentration = (
        max(ticker_counts.values()) / len(changed_matured) if changed_matured else None
    )
    pending_changed = [row for row in changed if row.get("utility_delta_pct") is None]
    pending_changed_dates = len({str(row["as_of_date"]) for row in pending_changed})

    def progress(observed: int, required: int) -> int:
        return min(100, round(observed / required * 100)) if required else 100

    captured_changed_dates = sorted({str(row["as_of_date"]) for row in changed})
    matured_changed_dates = {str(row["as_of_date"]) for row in changed_matured}
    pending_maturity_dates = {
        str(row["as_of_date"])
        for row in pending_changed
        if str(row.get("label_status") or "") in {"awaiting_outcome", "pending"}
    }
    maturity_units = 0.0
    for decision_date in captured_changed_dates[:MIN_CHANGED_DATES]:
        if decision_date in matured_changed_dates:
            maturity_units += 1.0
            continue
        if decision_date not in pending_maturity_dates:
            continue
        try:
            elapsed_days = max(0, (report_date - date.fromisoformat(decision_date)).days)
        except ValueError:
            elapsed_days = 0
        maturity_units += min(0.99, elapsed_days / THREE_MONTH_MATURITY_DAYS)
    capture_ratio = min(len(captured_changed_dates), MIN_CHANGED_DATES) / MIN_CHANGED_DATES
    maturity_ratio = maturity_units / MIN_CHANGED_DATES
    changed_pipeline_progress = min(100, round((capture_ratio + maturity_ratio) * 50))
    changed_progress_detail = (
        f"Captured {min(len(captured_changed_dates), MIN_CHANGED_DATES)}/{MIN_CHANGED_DATES} "
        f"changed-signal dates · 3M maturity {maturity_units:.2f}/{MIN_CHANGED_DATES}"
    )
    criteria = [
        {
            "criterion": "Independent outcome maturity",
            "passed": matured_dates >= MIN_MATURED_DATES,
            "observed": f"{matured_dates} dates",
            "required": f"≥ {MIN_MATURED_DATES} matured dates",
            "purpose": "Avoid treating many tickers from a few dates as independent evidence.",
            "available": True,
            "progress_pct": progress(matured_dates, MIN_MATURED_DATES),
            "progress_detail": f"Matured {matured_dates}/{MIN_MATURED_DATES} independent dates",
        },
        {
            "criterion": "Decision-change maturity",
            "passed": changed_dates >= MIN_CHANGED_DATES,
            "observed": f"{changed_dates} dates",
            "required": f"≥ {MIN_CHANGED_DATES} dates with matured signal changes",
            "purpose": "Evaluate dates on which the challenger would actually alter a decision.",
            "available": True,
            "progress_pct": changed_pipeline_progress,
            "progress_detail": changed_progress_detail,
        },
        {
            "criterion": "Utility improvement uncertainty",
            "passed": lower is not None and float(lower) > 0,
            "observed": "Unavailable" if lower is None else f"{float(lower):+.2f}% lower 95% bound",
            "required": "> 0% lower 95% confidence bound",
            "purpose": "Require paired benchmark-relative improvement beyond sampling uncertainty.",
            "available": lower is not None,
            "progress_pct": 100 if lower is not None else changed_pipeline_progress,
            "progress_detail": (
                "Required evidence is calculable" if lower is not None else changed_progress_detail
            ),
        },
        {
            "criterion": "Decision accuracy non-deterioration",
            "passed": accuracy is not None and float(accuracy) >= 0,
            "observed": "Unavailable" if accuracy is None else f"{float(accuracy) * 100:+.2f} pp",
            "required": "≥ 0 pp paired accuracy delta",
            "purpose": "Prevent higher utility from hiding systematically worse diagnostic accuracy.",
            "available": accuracy is not None,
            "progress_pct": 100 if accuracy is not None else changed_pipeline_progress,
            "progress_detail": (
                "Required evidence is calculable" if accuracy is not None else changed_progress_detail
            ),
        },
        {
            "criterion": "Across-date consistency",
            "passed": positive_date_share is not None and positive_date_share >= MIN_POSITIVE_DATE_SHARE,
            "observed": "Unavailable" if positive_date_share is None else f"{positive_date_share:.0%} positive dates",
            "required": f"≥ {MIN_POSITIVE_DATE_SHARE:.0%} positive changed-signal dates",
            "purpose": "Prevent one exceptional cutoff from dominating the conclusion.",
            "available": positive_date_share is not None,
            "progress_pct": 100 if positive_date_share is not None else changed_pipeline_progress,
            "progress_detail": (
                "Required evidence is calculable"
                if positive_date_share is not None else changed_progress_detail
            ),
        },
        {
            "criterion": "Ticker concentration",
            "passed": (
                ticker_concentration is not None
                and len(ticker_counts) >= 3
                and ticker_concentration <= MAX_TICKER_CONCENTRATION
            ),
            "observed": (
                "Unavailable" if ticker_concentration is None
                else f"{ticker_concentration:.0%} largest share across {len(ticker_counts)} tickers"
            ),
            "required": f"≥ 3 tickers and largest share ≤ {MAX_TICKER_CONCENTRATION:.0%}",
            "purpose": "Require the result not to depend mainly on one security.",
            "available": ticker_concentration is not None,
            "progress_pct": 100 if ticker_concentration is not None else changed_pipeline_progress,
            "progress_detail": (
                "Required evidence is calculable"
                if ticker_concentration is not None else changed_progress_detail
            ),
        },
    ]
    passed_count = sum(bool(item["passed"]) for item in criteria)
    if matured_dates < MIN_MATURED_DATES or changed_dates < MIN_CHANGED_DATES:
        gate = "Collecting evidence"
        rationale = "The independent-date coverage gates have not matured yet."
    elif passed_count < len(criteria):
        gate = "Inconclusive"
        rationale = "Coverage exists, but one or more performance or robustness gates remain red."
    else:
        gate = "Eligible for human review"
        rationale = "All preregistered readiness gates are green; this is not approval or automatic promotion."
    return {
        "coverage": {
            "snapshots": len(records),
            "tickers": len({str(row["ticker"]) for row in records}),
            "independent_dates": len({str(row["as_of_date"]) for row in records}),
            "matured_observations": len(matured),
            "matured_dates": matured_dates,
            "signal_changes": len(changed),
            "matured_signal_changes": len(changed_matured),
            "changed_dates": changed_dates,
            "pending_signal_changes": len(pending_changed),
            "pending_changed_dates": pending_changed_dates,
            "captured_changed_dates": len(captured_changed_dates),
            "changed_maturity_units": round(maturity_units, 3),
            "changed_pipeline_progress_pct": changed_pipeline_progress,
            "label_statuses": dict(Counter(str(row["label_status"]) for row in records)),
        },
        "all_paired": all_paired,
        "changed_paired": changed_paired,
        "gate": {
            "status": gate, "rationale": rationale,
            "criteria": criteria, "passed": passed_count, "total": len(criteria),
        },
        "by_ticker": _grouped(records, "ticker"),
        "by_coverage_mode": _grouped(records, "coverage_mode"),
        "by_technical_regime": _grouped(records, "technical_regime"),
        "by_simulation_source": _grouped(records, "simulation_source"),
    }


def cumulative_date_evidence(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Return expanding, date-clustered live and shadow utility estimates."""
    by_date: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        if row.get("live_utility_pct") is not None:
            by_date[str(row["as_of_date"])].append(row)
    live_means: list[float] = []
    shadow_means: list[float] = []
    result = []
    for decision_date, date_rows in sorted(by_date.items()):
        live_means.append(sum(float(row["live_utility_pct"]) for row in date_rows) / len(date_rows))
        shadow_means.append(sum(float(row["shadow_utility_pct"]) for row in date_rows) / len(date_rows))
        result.append({
            "as_of_date": decision_date,
            "live_expanding_utility_pct": round(sum(live_means) / len(live_means), 6),
            "shadow_expanding_utility_pct": round(sum(shadow_means) / len(shadow_means), 6),
            "independent_dates": len(live_means),
        })
    return result


def build_post_promotion_report(
    predictions: Sequence[Mapping[str, object]],
    labels: Sequence[Mapping[str, object]], *, model_version: str, promoted_at: str,
    horizon: str = "3M",
) -> dict[str, object]:
    """Measure only genuinely prospective evidence created after promotion.

    Historical rows materialized during promotion are deliberately excluded by
    their creation timestamp.  The frozen promotion baseline is a comparison
    anchor, never recomputed from the mutable application database.
    """
    label_index = {str(row["prediction_id"]): row for row in labels}
    by_date_accuracy: dict[str, list[float]] = defaultdict(list)
    by_date_utility: dict[str, list[float]] = defaultdict(list)
    matured = 0
    for prediction in predictions:
        if str(prediction.get("model_version")) != model_version:
            continue
        if str(prediction.get("created_at") or "") <= promoted_at:
            continue
        label = label_index.get(str(prediction.get("prediction_id")))
        if not label or label.get("status") != "available":
            continue
        outcome = _json(label.get("outcomes_json") or label.get("outcomes")).get(horizon)
        if not isinstance(outcome, Mapping):
            continue
        relative = outcome.get("relative_return_after_cost_pct")
        if not isinstance(relative, (int, float)):
            continue
        output = _json(prediction.get("output_json"))
        utility, correct = _policy_result(str(output.get("entry_signal") or "Wait"), float(relative))
        decision_date = str(prediction["as_of_date"])
        by_date_accuracy[decision_date].append(correct)
        by_date_utility[decision_date].append(utility)
        matured += 1
    accuracy = _cluster_summary(by_date_accuracy)
    utility = _cluster_summary(by_date_utility)
    return {
        "status": "monitoring" if matured else "awaiting_maturity",
        "matured_observations": matured,
        "independent_dates": accuracy["independent_dates"],
        "accuracy_pct": (
            round(float(accuracy["estimate"]) * 100, 2)
            if accuracy["estimate"] is not None else None
        ),
        "utility_pct": utility["estimate"],
        "accuracy_interval": accuracy,
        "utility_interval": utility,
        "frozen_baseline": dict(PROMOTION_BASELINE),
    }
