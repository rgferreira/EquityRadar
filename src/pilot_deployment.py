"""Comparison-only exposure for an immature, registered shadow model."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path

from src.data.database import (
    get_outcome_labels,
    get_pilot_deployment,
    get_prediction_snapshots,
    get_shadow_decision_snapshots,
    save_pilot_deployment_opt_in,
)
from src.model_registry import technology_potential_shadow_registration
from src.model_tuning import build_model_tuning_report, prepare_shadow_comparisons
from src.shadow_model import technology_potential_shadow_output


PILOT_DEPLOYMENT_KEY = "decision-dashboard-technology-daily-flow-v1"
PILOT_SURFACE = "decision_dashboard"
PILOT_ENVIRONMENT_VARIABLE = "PILOT_DECISIONS_ENABLED"
FALSE_VALUES = {"0", "false", "no", "off", "disabled"}


def pilot_runtime_enabled(environment: Mapping[str, str] | None = None) -> bool:
    """Return the reversible runtime availability switch, enabled by default."""
    source = os.environ if environment is None else environment
    return str(source.get(PILOT_ENVIRONMENT_VARIABLE, "true")).strip().lower() not in FALSE_VALUES


def pilot_deployment_state(
    db_path: str | Path | None = None, *, environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Resolve persisted opt-in and runtime availability without model authority."""
    registration = technology_potential_shadow_registration()
    deployment = get_pilot_deployment(
        PILOT_DEPLOYMENT_KEY,
        candidate_model_version=str(registration["model_version"]),
        surface=PILOT_SURFACE,
        db_path=db_path,
    )
    runtime_enabled = pilot_runtime_enabled(environment)
    persisted_opt_in = bool(deployment["user_opt_in"])
    return {
        **deployment,
        "runtime_enabled": runtime_enabled,
        "persisted_opt_in": persisted_opt_in,
        "effective_enabled": runtime_enabled and persisted_opt_in,
        "official_decision_authority": False,
    }


def set_pilot_opt_in(
    enabled: bool, db_path: str | Path | None = None,
) -> dict[str, object]:
    """Persist the user's comparison preference independently of model promotion."""
    registration = technology_potential_shadow_registration()
    save_pilot_deployment_opt_in(
        PILOT_DEPLOYMENT_KEY,
        enabled,
        candidate_model_version=str(registration["model_version"]),
        surface=PILOT_SURFACE,
        db_path=db_path,
    )
    return pilot_deployment_state(db_path)


def build_pilot_decision(
    current_outputs: Mapping[str, object], *,
    technology_evidence: Mapping[str, object] | None,
    daily_flow_evidence: Mapping[str, object] | None,
) -> dict[str, object]:
    """Run the exact registered shadow transformation without persistence."""
    return technology_potential_shadow_output(
        {
            "technology_potential": dict(technology_evidence or {}),
            "daily_short_flow": dict(daily_flow_evidence or {}),
        },
        current_outputs,
    )


def build_pilot_comparison(
    ticker: str, current_outputs: Mapping[str, object], *,
    technology_evidence: Mapping[str, object] | None,
    daily_flow_evidence: Mapping[str, object] | None,
) -> dict[str, object]:
    """Create a display-only Live-versus-Pilot row."""
    pilot = build_pilot_decision(
        current_outputs,
        technology_evidence=technology_evidence,
        daily_flow_evidence=daily_flow_evidence,
    )
    return {
        "Ticker": ticker.strip().upper(),
        "Official": str(current_outputs.get("entry_signal") or "Wait"),
        "Pilot": str(pilot["entry_signal"]),
        "Official score": float(current_outputs["entry_score"]),
        "Pilot score": float(pilot["entry_score"]),
        "Delta": float(pilot["entry_score_delta"]),
        "Technology adj": float(pilot["technology_entry_modifier"]),
        "Daily flow adj": float(pilot["daily_short_flow_entry_modifier"]),
        "Coverage": str(pilot["coverage_mode"]),
        "Decision changed": "Yes" if bool(pilot["signal_changed"]) else "No",
    }


def pilot_maturity_summary(
    db_path: str | Path | None = None, *, today: date | None = None,
) -> dict[str, object]:
    """Summarize current-candidate evidence as maturity, never as success odds."""
    version = str(technology_potential_shadow_registration()["model_version"])
    shadows = [
        row for row in get_shadow_decision_snapshots(db_path=db_path)
        if str(row["challenger_model_version"]) == version
    ]
    comparisons = prepare_shadow_comparisons(
        shadows,
        get_prediction_snapshots(db_path=db_path),
        get_outcome_labels(db_path=db_path),
    )
    report = build_model_tuning_report(comparisons, today=today)
    coverage = dict(report["coverage"])
    pending_changed_dates = sorted({
        str(row["as_of_date"])
        for row in comparisons
        if bool(row.get("signal_changed")) and row.get("utility_delta_pct") is None
    })
    next_maturity_date = None
    if pending_changed_dates:
        try:
            next_maturity_date = (
                date.fromisoformat(pending_changed_dates[0]) + timedelta(days=92)
            ).isoformat()
        except ValueError:
            next_maturity_date = None
    return {
        "candidate_model_version": version,
        "gate_status": report["gate"]["status"],
        "gates_passed": int(report["gate"]["passed"]),
        "gates_total": int(report["gate"]["total"]),
        "pipeline_progress_pct": int(coverage["changed_pipeline_progress_pct"]),
        "snapshots": int(coverage["snapshots"]),
        "independent_dates": int(coverage["independent_dates"]),
        "matured_observations": int(coverage["matured_observations"]),
        "signal_changes": int(coverage["signal_changes"]),
        "matured_signal_changes": int(coverage["matured_signal_changes"]),
        "pending_changed_dates": int(coverage["pending_changed_dates"]),
        "next_maturity_date": next_maturity_date,
    }
