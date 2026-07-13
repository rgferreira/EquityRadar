"""Point-in-time reconstruction and outcome evaluation for dashboard backtests."""

from __future__ import annotations

from datetime import date
from typing import Mapping

import pandas as pd

from src.scoring.decision import calculate_entry_score, calculate_exit_review_score, entry_label, exit_review_label
from src.scoring.risk import calculate_risk_score
from src.scoring.technical import calculate_technical_score
from src.scoring.valuation import calculate_valuation_score
from src.scoring.positioning import apply_positioning_adjustment, positioning_score_adjustments
from src.data.market_data import calculate_metrics

MODEL_VERSION = "backtested-learning-v2-finra"
OUTCOME_HORIZONS = {"1M": 21, "3M": 63, "6M": 126, "12M": 252}


def history_as_of(history: pd.DataFrame, as_of: date | str) -> pd.DataFrame:
    """Return observations no later than as_of, with no future leakage."""
    cutoff = pd.Timestamp(as_of)
    index = pd.to_datetime(history.index)
    if index.tz is not None:
        cutoff = cutoff.tz_localize(index.tz)
    return history.loc[index.normalize() <= cutoff.normalize()].copy()


def evidence_available(record: Mapping[str, object] | None, as_of: date | str) -> bool:
    """Whether a timestamped record was publicly available by the cutoff."""
    if not record:
        return False
    timestamp = record.get("reporting_date") or record.get("fetched_at")
    if not timestamp:
        return False
    try:
        return pd.Timestamp(str(timestamp)).date() <= pd.Timestamp(as_of).date()
    except (TypeError, ValueError):
        return False


def reconstruct_signal(
    history: pd.DataFrame, as_of: date | str,
    fundamentals: Mapping[str, object] | None = None,
    positioning_history: list[Mapping[str, object]] | None = None,
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
    valuation = calculate_valuation_score(usable_fundamentals)
    entry = calculate_entry_score(technical, valuation, risk)
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
    return {
        "metrics": metrics, "technical": technical, "valuation": valuation, "risk": risk,
        "entry_score": entry, "exit_score": exit_score,
        "entry_signal": entry_label(entry), "exit_signal": exit_review_label(exit_score),
        "coverage": coverage, "fundamentals_used": bool(usable_fundamentals),
        "positioning_modifier": positioning_modifier,
        "finra_observations_used": len(eligible_positioning),
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


def lesson_summary(runs: list[Mapping[str, object]]) -> dict[str, object]:
    """Aggregate completed historical observations without pretending small samples are certainty."""
    latest_by_cutoff: dict[str, Mapping[str, object]] = {}
    for index, run in enumerate(runs):
        cutoff = str(run.get("as_of_date") or run.get("created_at") or f"undated-{index}")
        existing = latest_by_cutoff.get(cutoff)
        if existing is None or str(run.get("model_version") or "") > str(existing.get("model_version") or ""):
            latest_by_cutoff[cutoff] = run
    completed = [r for r in latest_by_cutoff.values() if r.get("outcome_3m") is not None]
    if not completed:
        return {"sample_size": 0, "win_rate": None, "average_3m_return": None, "confidence": "Insufficient"}
    returns = [float(r["outcome_3m"]) for r in completed]
    size = len(returns)
    return {
        "sample_size": size,
        "win_rate": round(sum(value > 0 for value in returns) / size * 100, 1),
        "average_3m_return": round(sum(returns) / size, 2),
        "confidence": "Developing" if size < 5 else "Moderate" if size < 15 else "Established",
    }


def learned_score_adjustments(runs: list[Mapping[str, object]], minimum_samples: int = 3) -> dict[str, object]:
    """Translate ticker outcomes into bounded, auditable Entry/Exit modifiers."""
    lesson = lesson_summary(runs)
    size = int(lesson["sample_size"])
    if size < minimum_samples:
        return {**lesson, "entry_adjustment": 0.0, "exit_adjustment": 0.0,
                "reason": f"Needs {minimum_samples - size} more completed 3M simulation(s)"}
    average = float(lesson["average_3m_return"] or 0)
    win_rate = float(lesson["win_rate"] or 50)
    evidence_signal = ((win_rate - 50) / 50) * .6 + max(-1, min(1, average / 15)) * .4
    confidence_weight = min(1.0, size / 15)
    entry_adjustment = round(max(-5, min(5, 5 * evidence_signal * confidence_weight)), 1)
    return {**lesson, "entry_adjustment": entry_adjustment, "exit_adjustment": round(-entry_adjustment, 1),
            "reason": f"{size} completed observations · {win_rate:.0f}% positive at 3M · {average:+.1f}% average"}
