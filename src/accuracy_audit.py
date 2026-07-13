"""Read-only comparison between the frozen legacy and current accuracy evaluators."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Iterable, Mapping

from src.backtesting import LEARNING_WEIGHTS, latest_model_runs, select_learning_observations


def _composite(run: Mapping[str, object]) -> tuple[float, float] | None:
    monthly: dict[str, float] = {}
    for label, months in (("1M", 1), ("3M", 3), ("6M", 6)):
        value = run.get(f"outcome_{label.lower()}")
        if value is not None:
            monthly[label] = float(value) / months
    if not monthly:
        return None
    coverage = sum(LEARNING_WEIGHTS[label] for label in monthly)
    value = sum(monthly[label] * LEARNING_WEIGHTS[label] for label in monthly) / coverage
    return value, coverage


def legacy_observations(runs: list[Mapping[str, object]]) -> list[dict[str, object]]:
    """Reconstruct the evaluator used immediately before confirmed episodes."""
    selected: list[dict[str, object]] = []
    signatures: list[tuple[str, float, float]] = []
    for run in sorted(latest_model_runs(runs), key=lambda row: str(row.get("as_of_date") or "")):
        result = _composite(run)
        if result is None:
            continue
        composite, coverage = result
        if coverage < .50 or abs(composite) < .75:
            continue
        signature = (str(run.get("entry_signal")), float(run.get("entry_score") or 0), composite)
        if any(
            signature[0] == previous[0] and abs(signature[1] - previous[1]) < 3
            and abs(signature[2] - previous[2]) < .5 for previous in signatures
        ):
            continue
        signatures.append(signature)
        utility = composite if run.get("entry_signal") == "Buy candidate" else -composite
        selected.append({**dict(run), "composite": composite, "decision_utility": utility})
    return selected


def _accuracy(rows: list[Mapping[str, object]]) -> float | None:
    return 100 * sum(float(row["decision_utility"]) > 0 for row in rows) / len(rows) if rows else None


def _weighted_curve(rows: Iterable[tuple[str, Mapping[str, object]]], window: int = 3) -> list[dict[str, object]]:
    grouped: dict[str, list[bool]] = defaultdict(list)
    for _, row in rows:
        grouped[str(row.get("as_of_date") or "")].append(float(row["decision_utility"]) > 0)
    dates = sorted(grouped)
    curve: list[dict[str, object]] = []
    for index, cutoff in enumerate(dates):
        window_dates = dates[max(0, index - window + 1):index + 1]
        observations = [result for date in window_dates for result in grouped[date]]
        curve.append({
            "as_of_date": cutoff,
            "moving_accuracy": round(100 * sum(observations) / len(observations), 1),
            "observations": len(observations),
        })
    return curve


def compare_accuracy_models(runs_by_ticker: Mapping[str, list[Mapping[str, object]]]) -> dict[str, object]:
    """Compare legacy/live accuracy without mutating or persisting any data."""
    ticker_rows: list[dict[str, object]] = []
    legacy_all: list[tuple[str, Mapping[str, object]]] = []
    current_all: list[tuple[str, Mapping[str, object]]] = []
    for ticker, runs in sorted(runs_by_ticker.items()):
        legacy = legacy_observations(runs)
        current = select_learning_observations(runs)
        if not legacy and not current:
            continue
        legacy_accuracy, current_accuracy = _accuracy(legacy), _accuracy(current)
        ticker_rows.append({
            "ticker": ticker,
            "legacy_accuracy": legacy_accuracy,
            "legacy_observations": len(legacy),
            "current_accuracy": current_accuracy,
            "current_observations": len(current),
            "delta_pp": None if legacy_accuracy is None or current_accuracy is None else current_accuracy - legacy_accuracy,
        })
        legacy_all.extend((ticker, row) for row in legacy)
        current_all.extend((ticker, row) for row in current)

    same_episode_legacy_utilities = [
        float(row["composite"]) if row.get("entry_signal") == "Buy candidate" else -float(row["composite"])
        for _, row in current_all
    ]
    return {
        "tickers": ticker_rows,
        "legacy_micro_accuracy": _accuracy([row for _, row in legacy_all]),
        "current_micro_accuracy": _accuracy([row for _, row in current_all]),
        "legacy_macro_accuracy": mean(row["legacy_accuracy"] for row in ticker_rows if row["legacy_accuracy"] is not None),
        "current_macro_accuracy": mean(row["current_accuracy"] for row in ticker_rows if row["current_accuracy"] is not None),
        "legacy_observations": len(legacy_all),
        "current_observations": len(current_all),
        "same_episode_legacy_accuracy": (
            100 * sum(value > 0 for value in same_episode_legacy_utilities) / len(same_episode_legacy_utilities)
            if same_episode_legacy_utilities else None
        ),
        "same_episode_current_accuracy": _accuracy([row for _, row in current_all]),
        "legacy_moving_curve": _weighted_curve(legacy_all),
        "current_moving_curve": _weighted_curve(current_all),
    }
