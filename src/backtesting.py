"""Point-in-time reconstruction and outcome evaluation for dashboard backtests."""

from __future__ import annotations

from datetime import date
from typing import Mapping

import pandas as pd

from src.scoring.decision import (
    calculate_coverage_aware_entry_score, calculate_exit_review_score,
    entry_label, exit_review_label,
)
from src.scoring.risk import calculate_risk_score
from src.scoring.technical import calculate_technical_score
from src.scoring.valuation import calculate_valuation_score
from src.scoring.positioning import apply_positioning_adjustment, positioning_score_adjustments
from src.scoring.technology import technology_potential_evidence
from src.data.market_data import calculate_metrics
from src.data.temporal import evidence_known_by
from src.model_registry import CURRENT_MODEL_VERSION

MODEL_VERSION = CURRENT_MODEL_VERSION
OUTCOME_HORIZONS = {"1M": 21, "3M": 63, "6M": 126, "12M": 252}
LEARNING_WEIGHTS = {"1M": .50, "3M": .30, "6M": .20}
MINIMUM_CONFIRMED_HORIZON = "3M"
EPISODE_WINDOW_DAYS = 21
WATCH_UPSIDE_TOLERANCE = 3.0


def history_as_of(history: pd.DataFrame, as_of: date | str) -> pd.DataFrame:
    """Return observations no later than as_of, with no future leakage."""
    cutoff = pd.Timestamp(as_of)
    index = pd.to_datetime(history.index)
    if index.tz is not None:
        cutoff = cutoff.tz_localize(index.tz)
    return history.loc[index.normalize() <= cutoff.normalize()].copy()


def evidence_available(record: Mapping[str, object] | None, as_of: date | str) -> bool:
    """Whether a timestamped record was publicly available by the cutoff."""
    return evidence_known_by(record, as_of)


def reconstruct_signal(
    history: pd.DataFrame, as_of: date | str,
    fundamentals: Mapping[str, object] | None = None,
    positioning_history: list[Mapping[str, object]] | None = None,
    industry_research: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Rebuild the price/risk decision using only data known at the cutoff."""
    point_in_time = history_as_of(history, as_of)
    if len(point_in_time) < 2:
        raise ValueError("Insufficient price history on or before the selected date")
    # Metrics should reflect at most the trailing year at the historical cutoff.
    trailing = point_in_time.tail(253)
    metrics = calculate_metrics(trailing)
    technical = calculate_technical_score(metrics)
    risk = calculate_risk_score(metrics, trailing)
    usable_fundamentals = fundamentals if evidence_available(fundamentals, as_of) else None
    usable_industry_research = (
        industry_research if evidence_available(industry_research, as_of) else None
    )
    technology_evidence = technology_potential_evidence(usable_industry_research)
    valuation = calculate_valuation_score(usable_fundamentals)
    entry = calculate_coverage_aware_entry_score(
        technical, valuation, risk, valuation_available=bool(usable_fundamentals),
    )
    exit_score = calculate_exit_review_score(technical, risk)
    eligible_positioning = [
        row for row in (positioning_history or []) if evidence_available(row, as_of)
        and row.get("snapshot_type") == "historical_short_interest"
    ]
    positioning_modifier = positioning_score_adjustments(
        eligible_positioning[-1] if eligible_positioning else None, eligible_positioning, technical,
    )
    entry = apply_positioning_adjustment(entry, float(positioning_modifier["entry_adjustment"]))
    exit_score = apply_positioning_adjustment(exit_score, float(positioning_modifier["exit_adjustment"]))
    coverage_parts = ["fundamentals" if usable_fundamentals else None,
                      "FINRA" if eligible_positioning else None]
    coverage = "Partial coverage · " + " + ".join(part for part in coverage_parts if part) if any(coverage_parts) else "Price-only reconstruction"
    temporal_coverage = {
        "price": "end_of_day_cutoff",
        "fundamentals": (
            "verified_known_at" if usable_fundamentals else
            "missing" if not fundamentals else "unverified_or_after_cutoff"
        ),
        "finra": (
            "verified_known_at" if eligible_positioning else
            "missing" if not positioning_history else "unverified_or_after_cutoff"
        ),
        "technology_potential": (
            "verified_known_at" if usable_industry_research else
            "missing" if not industry_research else "unverified_or_after_cutoff"
        ),
    }
    input_references = {
        "fundamentals": ({
            field: usable_fundamentals.get(field) for field in (
                "provider_name", "period_end", "published_at", "known_at", "known_at_status",
            )
        } if usable_fundamentals else None),
        "finra": [{
            field: row.get(field) for field in (
                "provider_name", "snapshot_date", "period_end", "reporting_date", "published_at",
                "known_at", "known_at_status",
            )
        } for row in eligible_positioning],
        "technology_potential": ({
            field: usable_industry_research.get(field) for field in (
                "provider_name", "period_end", "published_at", "known_at", "known_at_status",
            )
        } if usable_industry_research else None),
        "prices": {"cutoff": str(as_of), "observations": len(point_in_time), "policy": "end_of_day"},
    }
    return {
        "metrics": metrics, "technical": technical, "valuation": valuation, "risk": risk,
        "entry_score": entry, "exit_score": exit_score,
        "entry_signal": entry_label(entry), "exit_signal": exit_review_label(exit_score),
        "coverage": coverage, "fundamentals_used": bool(usable_fundamentals),
        "positioning_modifier": positioning_modifier,
        "finra_observations_used": len(eligible_positioning),
        "temporal_coverage": temporal_coverage,
        "input_references": input_references,
        "technology_potential": technology_evidence,
        "observations": len(point_in_time), "model_version": MODEL_VERSION,
    }


def evaluate_outcomes(history: pd.DataFrame, as_of: date | str) -> dict[str, float | None]:
    """Measure forward returns after the cutoff; never feed them into reconstruction."""
    index = pd.to_datetime(history.index)
    cutoff = pd.Timestamp(as_of)
    if index.tz is not None:
        cutoff = cutoff.tz_localize(index.tz)
    before = history.loc[index.normalize() <= cutoff.normalize(), "Close"].dropna()
    after = history.loc[index.normalize() > cutoff.normalize(), "Close"].dropna()
    if before.empty:
        return {label: None for label in OUTCOME_HORIZONS}
    base = float(before.iloc[-1])
    return {
        label: round((float(after.iloc[days - 1]) / base - 1) * 100, 2) if len(after) >= days else None
        for label, days in OUTCOME_HORIZONS.items()
    }


def decision_outcome(run: Mapping[str, object]) -> dict[str, object]:
    """Interpret forward returns against the decision that was actually made.

    Horizon returns are converted to comparable monthly rates before applying the
    50/30/20 weights. Missing immature horizons are excluded and the available
    weights are renormalized, while coverage remains visible.
    """
    monthly: dict[str, float] = {}
    for label, months in (("1M", 1), ("3M", 3), ("6M", 6)):
        value = run.get(f"outcome_{label.lower()}")
        if value is not None:
            monthly[label] = float(value) / months
    available_weight = sum(LEARNING_WEIGHTS[label] for label in monthly)
    if not monthly:
        return {"composite": None, "decision_utility": None, "verdict": "Pending outcomes",
                "coverage": 0.0, "should_evaluate": False, "should_learn": False,
                "maturity": "Provisional", "learning_priority": 0,
                "learning_reason": "No 1M/3M/6M outcome has matured"}
    composite = sum(monthly[label] * LEARNING_WEIGHTS[label] for label in monthly) / available_weight
    signal = str(run.get("entry_signal") or "Wait")
    entered = signal == "Buy candidate"
    if entered:
        utility = composite
        verdict = "Correct entry" if composite > 0 else "Unfavorable entry" if composite < 0 else "Neutral entry"
    elif signal == "Watch":
        # Watch is a deliberate intermediate decision: tolerate modest upside
        # while waiting for confirmation, reward caution during flat/down moves.
        utility = WATCH_UPSIDE_TOLERANCE - composite if composite >= 0 else -composite
        verdict = "Correct watch" if utility > 0 else "Missed opportunity" if utility < 0 else "Neutral watch"
    else:
        utility = -composite
        verdict = "Correct avoidance" if composite < 0 else "Missed opportunity" if composite > 0 else "Neutral wait"
    disagreement = utility < 0
    magnitude_points = min(35, abs(composite) * 7)
    score = float(run.get("entry_score") or 50)
    threshold_distance = min(abs(score - 55), abs(score - 70))
    boundary_points = max(0, 20 - threshold_distance * 2)
    priority = round(min(100, (45 if disagreement else 10) + magnitude_points + boundary_points))
    sufficient = available_weight >= .50
    confirmed = run.get("outcome_3m") is not None
    # Directional disagreement matters only when the move clears a small noise
    # floor; otherwise every fractional fluctuation would become a lesson.
    informative = abs(composite) >= .75
    should_evaluate = sufficient and informative
    should_learn = should_evaluate and confirmed
    reason_parts = [verdict, f"{available_weight:.0%} horizon coverage"]
    if not sufficient:
        reason_parts.append("awaiting more outcome coverage")
    elif not informative:
        reason_parts.append("outcome too close to noise")
    elif not confirmed:
        reason_parts.append(f"provisional until {MINIMUM_CONFIRMED_HORIZON} matures")
    else:
        reason_parts.append("decision/outcome evidence retained")
    return {
        "composite": round(composite, 2), "decision_utility": round(utility, 2),
        "verdict": verdict, "coverage": round(available_weight, 2),
        "should_learn": should_learn, "learning_priority": priority,
        "should_evaluate": should_evaluate, "maturity": "Confirmed" if confirmed else "Provisional",
        "learning_reason": " · ".join(reason_parts),
    }


def select_learning_observations(
    runs: list[Mapping[str, object]], confirmed_only: bool = True,
) -> list[dict[str, object]]:
    """Keep informative, independent decision episodes for evaluation."""
    selected: list[dict[str, object]] = []
    signatures: list[tuple[str, float, float]] = []
    for run in sorted(_latest_runs_by_cutoff(runs), key=lambda row: str(row.get("as_of_date") or "")):
        analysis = decision_outcome(run)
        enriched = {**dict(run), **analysis}
        if not (analysis["should_learn"] if confirmed_only else analysis["should_evaluate"]):
            continue
        if selected:
            current_date = pd.Timestamp(str(run.get("as_of_date")))
            previous_date = pd.Timestamp(str(selected[-1].get("as_of_date")))
            same_signal = str(run.get("entry_signal")) == str(selected[-1].get("entry_signal"))
            if same_signal and (current_date - previous_date).days < EPISODE_WINDOW_DAYS:
                enriched["should_learn"] = False
                enriched["learning_reason"] = f"{analysis['learning_reason']} · same decision episode excluded"
                continue
        signature = (str(run.get("entry_signal")), float(run.get("entry_score") or 0), float(analysis["composite"] or 0))
        duplicate = any(
            signature[0] == previous[0] and abs(signature[1] - previous[1]) < 3
            and abs(signature[2] - previous[2]) < .5 for previous in signatures
        )
        if duplicate:
            enriched["should_learn"] = False
            enriched["learning_reason"] = f"{analysis['learning_reason']} · near-duplicate situation excluded"
            continue
        signatures.append(signature)
        selected.append(enriched)
    return selected


def diagnostic_success_rate(
    runs: list[Mapping[str, object]], signal: str, side: str = "entry",
    minimum_samples: int = 3,
) -> dict[str, object]:
    """Measure success for the exact displayed diagnostic using comparable evidence."""
    if side not in {"entry", "exit"}:
        raise ValueError("side must be 'entry' or 'exit'")
    signal_field = "entry_signal" if side == "entry" else "exit_signal"
    comparable = [
        row for row in select_learning_observations(runs)
        if str(row.get(signal_field)) == signal
    ]
    successes = 0
    for row in comparable:
        if side == "entry":
            successful = float(row["decision_utility"]) > 0
        else:
            forward = float(row["composite"])
            successful = forward < 0 if signal in {"Sell review", "Reassess"} else forward > 0
        successes += int(successful)
    sample_size = len(comparable)
    rate = round(successes / sample_size * 100, 1) if sample_size >= minimum_samples else None
    return {
        "signal": signal, "side": side, "sample_size": sample_size,
        "successes": successes, "success_rate": rate,
        "minimum_samples": minimum_samples,
        "available": rate is not None,
    }


def _latest_runs_by_cutoff(runs: list[Mapping[str, object]]) -> list[Mapping[str, object]]:
    latest: dict[str, Mapping[str, object]] = {}
    for index, run in enumerate(runs):
        cutoff = str(run.get("as_of_date") or run.get("created_at") or f"undated-{index}")
        existing = latest.get(cutoff)
        if existing is None or _model_selection_key(run) > _model_selection_key(existing):
            latest[cutoff] = run
    return list(latest.values())


def latest_model_runs(runs: list[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """Select active registered rows; retain explicit legacy fallback by row identity."""
    latest: dict[tuple[str, str], Mapping[str, object]] = {}
    for run in runs:
        key = (str(run.get("ticker") or ""), str(run.get("as_of_date") or ""))
        existing = latest.get(key)
        if existing is None or _model_selection_key(run) > _model_selection_key(existing):
            latest[key] = run
    return sorted(latest.values(), key=lambda row: (str(row.get("as_of_date") or ""), str(row.get("ticker") or "")), reverse=True)


def _model_selection_key(run: Mapping[str, object]) -> tuple[int, str, int]:
    """Rank by explicit registry activity, then immutable row creation identity."""
    return (
        int(run.get("model_is_active") or 0),
        str(run.get("created_at") or ""),
        int(run.get("id") or 0),
    )


def lesson_summary(runs: list[Mapping[str, object]]) -> dict[str, object]:
    """Aggregate only observations the learning-value gate considers useful."""
    latest = _latest_runs_by_cutoff(runs)
    selected = select_learning_observations(runs)
    evaluated = select_learning_observations(runs, confirmed_only=False)
    provisional = [row for row in evaluated if row["maturity"] == "Provisional"]
    if not selected:
        return {"sample_size": 0, "eligible_runs": 0, "total_runs": len(latest), "win_rate": None,
                "average_3m_return": None, "average_composite": None, "decision_accuracy": None,
                "correct_decisions": 0, "confidence": "Insufficient",
                "provisional_runs": len(provisional), "evaluated_runs": len(evaluated)}
    composites = [float(row["composite"]) for row in selected]
    utilities = [float(row["decision_utility"]) for row in selected]
    three_month = [float(row["outcome_3m"]) for row in selected if row.get("outcome_3m") is not None]
    size = len(selected)
    return {
        "sample_size": size, "eligible_runs": size, "total_runs": len(latest),
        "win_rate": round(sum(value > 0 for value in composites) / size * 100, 1),
        "average_3m_return": round(sum(three_month) / len(three_month), 2) if three_month else None,
        "average_composite": round(sum(composites) / size, 2),
        "decision_accuracy": round(sum(value > 0 for value in utilities) / size * 100, 1),
        "correct_decisions": sum(value > 0 for value in utilities),
        "confidence": "Developing" if size < 5 else "Moderate" if size < 15 else "Established",
        "provisional_runs": len(provisional), "evaluated_runs": len(evaluated),
    }


def decision_accuracy_history(runs: list[Mapping[str, object]]) -> list[dict[str, object]]:
    """Return the cumulative confirmed accuracy after each independent episode."""
    correct = 0
    history: list[dict[str, object]] = []
    for index, row in enumerate(select_learning_observations(runs), start=1):
        successful = float(row["decision_utility"]) > 0
        correct += int(successful)
        history.append({
            "as_of_date": str(row.get("as_of_date") or ""),
            "accuracy": round(correct / index * 100, 1),
            "correct_decisions": correct,
            "episodes": index,
            "successful": successful,
            "entry_signal": str(row.get("entry_signal") or ""),
            "verdict": str(row.get("verdict") or ""),
            "composite": row.get("composite"),
            "decision_utility": row.get("decision_utility"),
        })
    return history


def learned_score_adjustments(runs: list[Mapping[str, object]], minimum_samples: int = 3) -> dict[str, object]:
    """Translate ticker outcomes into bounded, auditable Entry/Exit modifiers."""
    lesson = lesson_summary(runs)
    size = int(lesson["sample_size"])
    if size < minimum_samples:
        return {**lesson, "entry_adjustment": 0.0, "exit_adjustment": 0.0,
                "reason": f"Needs {minimum_samples - size} more informative decision-aware observation(s)"}
    average = float(lesson["average_composite"] or 0)
    accuracy = float(lesson["decision_accuracy"] or 50)
    # Positive utility means the historical decision was correct. A negative
    # utility means current Entry scoring needs to move opposite to that decision.
    selected = select_learning_observations(runs)
    directional_correction = sum(
        (-1 if row["entry_signal"] == "Buy candidate" else 1) * max(-1, min(1, -float(row["decision_utility"]) / 3))
        for row in selected
    ) / size
    evidence_signal = directional_correction * .7 + ((accuracy - 50) / 50) * .3
    confidence_weight = min(1.0, size / 15)
    entry_adjustment = round(max(-5, min(5, 5 * evidence_signal * confidence_weight)), 1)
    return {**lesson, "entry_adjustment": entry_adjustment, "exit_adjustment": round(-entry_adjustment, 1),
            "reason": f"{size}/{lesson['total_runs']} confirmed independent episodes · {accuracy:.0f}% confirmed accuracy · {average:+.2f}% weighted monthly outcome"}
