"""Append-only FINRA daily-flow counterfactuals for saved simulations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from src.backtesting import decision_outcome, latest_model_runs, select_learning_observations
from src.data.database import (
    get_backtest_runs, get_finra_daily_short_volume, get_finra_simulation_enrichments,
    get_watchlist, save_finra_simulation_enrichment,
)
from src.model_registry import TECHNOLOGY_POTENTIAL_SHADOW_VERSION
from src.scoring.daily_short_flow import retrospective_daily_short_flow_evidence
from src.shadow_model import technology_potential_shadow_output


METHODOLOGY_VERSION = "finra-daily-flow-retrospective-counterfactual-v1"


def _source_inputs(run: Mapping[str, object]) -> dict[str, object]:
    try:
        parsed = json.loads(str(run.get("inputs_json") or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_finra_simulation_enrichment(
    run: Mapping[str, object], observations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build one quarantined Shadow counterfactual without changing the source run."""
    ticker = str(run.get("ticker") or "").strip().upper()
    if not ticker or ticker == "BTC-USD":
        raise ValueError("FINRA simulation enrichments require a non-BTC ticker")
    cutoff = str(run["as_of_date"])
    evidence = retrospective_daily_short_flow_evidence(observations, as_of=cutoff)
    if float(evidence["confidence"]) <= 0:
        raise ValueError("Insufficient retrospective FINRA history at cutoff")
    source_inputs = _source_inputs(run)
    current_outputs = {
        "entry_score": float(run["entry_score"]), "entry_signal": str(run["entry_signal"]),
        "exit_score": float(run["exit_score"]), "exit_signal": str(run["exit_signal"]),
    }
    candidate = technology_potential_shadow_output(
        {
            "technology_potential": dict(source_inputs.get("technology_potential") or {}),
            "daily_short_flow": evidence,
        },
        current_outputs,
    )
    original_outcome = decision_outcome(run)
    candidate_outcome = decision_outcome({
        **dict(run), "entry_score": candidate["entry_score"],
        "entry_signal": candidate["entry_signal"],
    })
    metrics = {
        "original_entry_score": current_outputs["entry_score"],
        "counterfactual_entry_score": candidate["entry_score"],
        "original_entry_signal": current_outputs["entry_signal"],
        "counterfactual_entry_signal": candidate["entry_signal"],
        "original_exit_score": current_outputs["exit_score"],
        "counterfactual_exit_score": candidate["exit_score"],
        "shorts_entry_modifier": candidate["shorts_entry_modifier"],
        "shorts_exit_modifier": candidate["shorts_exit_modifier"],
        "technology_entry_modifier": candidate["technology_entry_modifier"],
        "signal_changed": bool(candidate["signal_changed"]),
        "flow_slope_pp_per_session": evidence["slope_pp_per_session"],
        "flow_confidence": evidence["confidence"],
        "flow_coverage": evidence["coverage"],
        "flow_observations": evidence["observations"],
        "latest_trade_date": evidence["latest_trade_date"],
        "original_decision_utility": original_outcome["decision_utility"],
        "counterfactual_decision_utility": candidate_outcome["decision_utility"],
        "utility_delta": round(
            float(candidate_outcome["decision_utility"]) - float(original_outcome["decision_utility"]), 2,
        ) if original_outcome["decision_utility"] is not None else None,
        "outcome_composite": original_outcome["composite"],
        "outcome_maturity": original_outcome["maturity"],
        "outcome_informative": bool(original_outcome["should_evaluate"]),
        "outcome_confirmed": bool(original_outcome["should_learn"]),
        "decision_weight": 0.0,
    }
    eligible = [row for row in observations if str(row.get("trade_date") or "") < cutoff]
    payload_identity = [
        (str(row.get("trade_date")), str(row.get("payload_hash"))) for row in eligible
    ]
    input_references = {
        "policy": "retrospective current-revision replay; strictly before cutoff",
        "historical_availability": "not_point_in_time_verified",
        "cutoff": cutoff, "eligible_observations": len(eligible),
        "latest_observation_ids": [int(row["id"]) for row in eligible[-30:]],
        "latest_trade_dates": [str(row["trade_date"]) for row in eligible[-30:]],
        "provider_name": str(eligible[-1]["provider_name"]),
        "source_fingerprint_sha256": hashlib.sha256(
            json.dumps(payload_identity, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    identity = json.dumps({
        "source_backtest_run_id": int(run["id"]),
        "methodology_version": METHODOLOGY_VERSION,
        "shadow_model_version": TECHNOLOGY_POTENTIAL_SHADOW_VERSION,
        "metrics": metrics, "input_references": input_references,
    }, sort_keys=True, separators=(",", ":"))
    return {
        "enrichment_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "source_backtest_run_id": int(run["id"]), "ticker": ticker,
        "as_of_date": cutoff, "source_model_version": str(run["model_version"]),
        "shadow_model_version": TECHNOLOGY_POTENTIAL_SHADOW_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        "evidence_status": "retrospective_only", "metrics": metrics,
        "input_references": input_references,
    }


def recalculate_finra_simulation_enrichments(
    *, db_path: str | Path | None = None,
) -> dict[str, int]:
    """Append counterfactuals for every eligible active non-BTC simulation cutoff."""
    active_runs = latest_model_runs(get_backtest_runs(db_path=db_path))
    by_ticker = {
        ticker: get_finra_daily_short_volume(ticker, db_path)
        for ticker in get_watchlist(db_path) if ticker != "BTC-USD"
    }
    inserted = eligible = insufficient = already_present = unsupported = 0
    for run in active_runs:
        ticker = str(run["ticker"])
        observations = by_ticker.get(ticker)
        if not observations:
            unsupported += 1
            continue
        try:
            enrichment = build_finra_simulation_enrichment(run, observations)
        except ValueError as exc:
            if "Insufficient retrospective" not in str(exc):
                raise
            insufficient += 1
            continue
        eligible += 1
        if save_finra_simulation_enrichment(enrichment, db_path=db_path):
            inserted += 1
        else:
            already_present += 1
    return {
        "active_runs": len(active_runs), "eligible": eligible, "inserted": inserted,
        "already_present": already_present, "insufficient_history": insufficient,
        "unsupported": unsupported,
    }


def finra_counterfactual_summary(*, db_path: str | Path | None = None) -> dict[str, object]:
    """Summarize quarantined paired results; never expose them as promotion evidence."""
    rows = get_finra_simulation_enrichments(
        methodology_version=METHODOLOGY_VERSION, db_path=db_path,
    )
    independent_ids: set[int] = set()
    for ticker in sorted({str(row["ticker"]) for row in rows}):
        source_runs = [{
            "id": int(row["source_backtest_run_id"]), "ticker": ticker,
            "as_of_date": row["as_of_date"], "entry_signal": row["source_entry_signal"],
            "entry_score": row["source_entry_score"], "outcome_1m": row["outcome_1m"],
            "outcome_3m": row["outcome_3m"], "outcome_6m": row["outcome_6m"],
            "outcome_12m": row["outcome_12m"],
        } for row in rows if str(row["ticker"]) == ticker]
        independent_ids.update(
            int(run["id"]) for run in select_learning_observations(source_runs)
        )
    all_confirmed = [row for row in rows if bool(row["metrics"].get("outcome_confirmed"))]
    confirmed = [
        row for row in rows if int(row["source_backtest_run_id"]) in independent_ids
    ]
    changed = [row for row in rows if bool(row["metrics"].get("signal_changed"))]
    changed_confirmed = [row for row in confirmed if bool(row["metrics"].get("signal_changed"))]

    def accuracy(field: str, sample: list[dict[str, object]]) -> float | None:
        if not sample:
            return None
        return round(100 * sum(float(row["metrics"][field]) > 0 for row in sample) / len(sample), 1)

    utility_deltas = [float(row["metrics"]["utility_delta"]) for row in confirmed]
    return {
        "methodology_version": METHODOLOGY_VERSION, "evidence_status": "retrospective_only",
        "overlays": len(rows), "confirmed": len(confirmed),
        "all_confirmed_before_independence_gate": len(all_confirmed),
        "signal_changes": len(changed),
        "confirmed_signal_changes": len(changed_confirmed),
        "original_accuracy_pct": accuracy("original_decision_utility", confirmed),
        "counterfactual_accuracy_pct": accuracy("counterfactual_decision_utility", confirmed),
        "accuracy_delta_pp": (
            None if not confirmed else round(
                float(accuracy("counterfactual_decision_utility", confirmed) or 0)
                - float(accuracy("original_decision_utility", confirmed) or 0), 1,
            )
        ),
        "average_utility_delta": (
            round(sum(utility_deltas) / len(utility_deltas), 2) if utility_deltas else None
        ),
        "promotion_eligible": False,
    }
