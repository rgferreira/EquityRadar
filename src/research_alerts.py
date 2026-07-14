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
        if "model_is_active" in run and not bool(run.get("model_is_active")):
            continue
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


def score_boundary_alerts(runs: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Report explicit Entry/Exit threshold crossings as one auditable event."""
    grouped: dict[str, dict[str, Mapping[str, object]]] = defaultdict(dict)
    for run in runs:
        if "model_is_active" in run and not bool(run.get("model_is_active")):
            continue
        grouped[str(run["ticker"]).upper()][str(run["as_of_date"])] = run
    alerts = []
    for ticker, dated in grouped.items():
        ordered = [dated[key] for key in sorted(dated)]
        if len(ordered) < 2:
            continue
        previous, latest = ordered[-2:]
        crossings = []
        for field, thresholds, label in (
            ("entry_score", (55, 70), "Entry"), ("exit_score", (50, 70), "Exit review"),
        ):
            if previous.get(field) is None or latest.get(field) is None:
                continue
            before, after = float(previous[field]), float(latest[field])
            for threshold in thresholds:
                if (before < threshold <= after) or (before >= threshold > after):
                    direction = "above" if after >= threshold else "below"
                    crossings.append(f"{label} crossed {direction} {threshold}")
        if crossings:
            alerts.append(_alert(
                ticker, "score_boundary", str(latest["as_of_date"]),
                f"{ticker} crossed a decision boundary", " · ".join(crossings),
                {"previous_date": previous["as_of_date"], "crossings": crossings},
            ))
    return alerts


def finra_reversal_alerts(
    histories: Mapping[str, Sequence[Mapping[str, object]]],
) -> list[dict[str, object]]:
    """Flag a material sign reversal in official FINRA short-interest change."""
    alerts = []
    for ticker, rows in histories.items():
        observations = []
        for row in rows:
            if row.get("snapshot_type") != "historical_short_interest":
                continue
            short = row.get("short") if isinstance(row.get("short"), Mapping) else {}
            change = short.get("short_change_pct")
            if isinstance(change, (int, float)):
                observations.append((str(row["snapshot_date"]), float(change)))
        observations.sort()
        if len(observations) < 2:
            continue
        previous, latest = observations[-2:]
        if previous[1] * latest[1] < 0 and abs(latest[1]) >= 5:
            direction = "falling" if latest[1] < 0 else "rising"
            alerts.append(_alert(
                ticker.upper(), "finra_reversal", latest[0],
                f"{ticker.upper()} FINRA short-interest direction reversed",
                f"Reported short interest switched to {direction} ({latest[1]:+.1f}%).",
                {"previous_change_pct": previous[1], "latest_change_pct": latest[1]},
            ))
    return alerts


def provider_recovery_alerts(
    transitions: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    alerts = []
    for transition in transitions:
        if transition.get("previous_status") != "failed" or transition.get("new_status") != "healthy":
            continue
        provider = str(transition["provider_key"]).replace("_", " ").title()
        ticker = str(transition["ticker"]).upper()
        occurred = str(transition["occurred_at"])
        alerts.append(_alert(
            ticker, f"provider_recovery_{transition['provider_key']}", occurred,
            f"{ticker} {provider} provider recovered",
            "Fresh provider evidence is available again; prior cached evidence was preserved during the outage.",
            {"provider": transition["provider_key"]}, severity="info",
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


def build_research_alerts(
    runs: Sequence[Mapping[str, object]], *,
    positioning_histories: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    provider_transitions: Sequence[Mapping[str, object]] = (),
) -> list[dict[str, object]]:
    return (
        diagnostic_change_alerts(runs)
        + score_boundary_alerts(runs)
        + matured_lesson_alerts(runs)
        + finra_reversal_alerts(positioning_histories or {})
        + provider_recovery_alerts(provider_transitions)
    )
