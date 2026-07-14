"""Meaningful, non-executing research alerts."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence


def _alert(
    ticker: str, alert_type: str, evidence_date: str, title: str, detail: str,
    evidence: Mapping[str, object], severity: str = "attention",
) -> dict[str, object]:
    identity = f"{ticker}|{alert_type}|{evidence_date}"
    return {
        "alert_id": hashlib.sha256(identity.encode()).hexdigest(),
        "ticker": ticker,
        "alert_type": alert_type,
        "severity": severity,
        "title": title,
        "detail": detail,
        "evidence_date": evidence_date,
        "evidence_json": json.dumps(dict(evidence), sort_keys=True, separators=(",", ":")),
    }


def diagnostic_change_alerts(runs: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Alert only when a persisted diagnostic category changes, never for price noise."""
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for run in runs:
        grouped[str(run["ticker"]).upper()].append(run)
    alerts = []
    for ticker, ticker_runs in grouped.items():
        ordered = sorted(ticker_runs, key=lambda row: str(row["as_of_date"]))
        if len(ordered) < 2:
            continue
        previous, latest = ordered[-2:]
        entry_changed = previous.get("entry_signal") != latest.get("entry_signal")
        exit_changed = previous.get("exit_signal") != latest.get("exit_signal")
        if not entry_changed and not exit_changed:
            continue
        transitions = []
        if entry_changed:
            transitions.append(f"Entry: {previous.get('entry_signal')} → {latest.get('entry_signal')}")
        if exit_changed:
            transitions.append(f"Exit review: {previous.get('exit_signal')} → {latest.get('exit_signal')}")
        alerts.append(_alert(
            ticker, "diagnostic_change", str(latest["as_of_date"]),
            f"{ticker} diagnostic changed", " · ".join(transitions),
            {"previous_date": previous["as_of_date"], "transitions": transitions},
        ))
    return alerts


def matured_lesson_alerts(runs: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    alerts = []
    for run in runs:
        if run.get("outcome_3m") is None or not run.get("outcome_refreshed_at"):
            continue
        alerts.append(_alert(
            str(run["ticker"]).upper(), "matured_lesson", str(run["as_of_date"]),
            f"{str(run['ticker']).upper()} 3M lesson matured",
            "A saved decision now has a three-month outcome available for review.",
            {"simulation_source": run.get("simulation_source"), "model_version": run.get("model_version")},
            severity="info",
        ))
    return alerts


def build_research_alerts(runs: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return diagnostic_change_alerts(runs) + matured_lesson_alerts(runs)
