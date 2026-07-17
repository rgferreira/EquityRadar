"""Inactive shadow-model computation and immutable comparison snapshots."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from src.model_registry import (
    ACTIVE_SHADOW_ENABLED, COVERAGE_AWARE_PROMOTED, build_prediction_snapshot,
    canonical_json, content_hash, coverage_aware_shadow_registration,
    current_model_registration, technology_potential_shadow_registration,
)
from src.scoring.decision import entry_label, exit_review_label
from src.scoring.positioning import apply_positioning_adjustment


def meaningful_valuation_available(record: Mapping[str, object] | None) -> bool:
    if not record:
        return False
    return any(
        isinstance(record.get(field), (int, float)) and float(record[field]) > 0
        for field in ("trailing_pe", "forward_pe", "price_to_sales_ttm")
    )


def coverage_aware_shadow_output(
    inputs: Mapping[str, object], current_outputs: Mapping[str, object],
) -> dict[str, object]:
    """Calculate an offline-only candidate without changing current outputs."""
    features = dict(inputs.get("features") or {})
    temporal = dict(inputs.get("temporal_coverage") or {})
    positioning = dict(inputs.get("positioning_adjustments") or {})
    current_entry = float(current_outputs["entry_score"])
    current_signal = str(current_outputs["entry_signal"])
    if bool(inputs.get("industry_calibrated")):
        score = current_entry
        mode = "industry_calibrated_observation_only"
    else:
        technical = float(features["technical_score"])
        valuation = float(features["valuation_score"])
        risk = float(features["risk_score"])
        valuation_available = bool(inputs.get("valuation_available")) or (
            temporal.get("fundamentals") == "verified_known_at"
        )
        if valuation_available:
            base = technical * 0.50 + valuation * 0.30 + risk * 0.20
            mode = "verified_full_composite"
        else:
            base = technical * (5 / 7) + risk * (2 / 7)
            mode = "valuation_unavailable_renormalized"
        score = apply_positioning_adjustment(
            base, float(positioning.get("entry_adjustment") or 0),
        )
    score = round(score, 1)
    signal = entry_label(score)
    return {
        "entry_score": score,
        "entry_signal": signal,
        "exit_score": current_outputs.get("exit_score"),
        "exit_signal": current_outputs.get("exit_signal"),
        "coverage_mode": mode,
        "entry_score_delta": round(score - current_entry, 1),
        "signal_changed": signal != current_signal,
    }


def technology_potential_shadow_output(
    inputs: Mapping[str, object], current_outputs: Mapping[str, object],
) -> dict[str, object]:
    """Apply the preregistered Technology and daily short-flow shadow modifiers."""
    evidence = dict(inputs.get("technology_potential") or {})
    daily_flow = dict(inputs.get("daily_short_flow") or {})
    current_entry = float(current_outputs["entry_score"])
    current_signal = str(current_outputs["entry_signal"])
    technology_modifier = float(evidence.get("entry_modifier") or 0.0)
    if not evidence or float(evidence.get("confidence") or 0.0) <= 0:
        technology_modifier = 0.0
        technology_mode = "technology_unavailable"
    else:
        technology_modifier = max(-5.0, min(5.0, technology_modifier))
        technology_mode = f"technology_{evidence.get('coverage') or 'limited'}"
    flow_entry_modifier = float(daily_flow.get("entry_modifier") or 0.0)
    flow_exit_modifier = float(daily_flow.get("exit_modifier") or 0.0)
    if not daily_flow or float(daily_flow.get("confidence") or 0.0) <= 0:
        flow_entry_modifier = flow_exit_modifier = 0.0
        flow_mode = "daily_flow_unavailable"
    else:
        flow_entry_modifier = max(-2.0, min(2.0, flow_entry_modifier))
        flow_exit_modifier = max(-2.0, min(2.0, flow_exit_modifier))
        flow_mode = f"daily_flow_{daily_flow.get('coverage') or 'limited'}"
    score = round(max(
        0.0, min(100.0, current_entry + technology_modifier + flow_entry_modifier)
    ), 1)
    signal = entry_label(score)
    current_exit = current_outputs.get("exit_score")
    exit_score = (
        round(max(0.0, min(100.0, float(current_exit) + flow_exit_modifier)), 1)
        if isinstance(current_exit, (int, float)) else current_exit
    )
    return {
        "entry_score": score,
        "entry_signal": signal,
        "exit_score": exit_score,
        "exit_signal": (
            exit_review_label(float(exit_score))
            if isinstance(exit_score, (int, float)) else current_outputs.get("exit_signal")
        ),
        "coverage_mode": f"{technology_mode}+{flow_mode}",
        "technology_score": float(evidence.get("score") or 50.0),
        "technology_confidence": float(evidence.get("confidence") or 0.0),
        "technology_entry_modifier": round(technology_modifier, 1),
        "daily_short_flow_slope": float(daily_flow.get("slope_pp_per_session") or 0.0),
        "daily_short_flow_confidence": float(daily_flow.get("confidence") or 0.0),
        "daily_short_flow_entry_modifier": round(flow_entry_modifier, 1),
        "daily_short_flow_exit_modifier": round(flow_exit_modifier, 1),
        "entry_score_delta": round(score - current_entry, 1),
        "signal_changed": signal != current_signal,
    }


def build_shadow_snapshot(
    *, ticker: str, as_of_date: str, surface: str,
    inputs: Mapping[str, object], current_outputs: Mapping[str, object],
    current_model: Mapping[str, object] | None = None,
    challenger_model: Mapping[str, object] | None = None,
) -> dict[str, object]:
    registered_current = dict(current_model or current_model_registration())
    challenger = dict(challenger_model or technology_potential_shadow_registration())
    challenger_outputs = (
        coverage_aware_shadow_output(inputs, current_outputs)
        if challenger["model_version"] == coverage_aware_shadow_registration()["model_version"]
        else technology_potential_shadow_output(inputs, current_outputs)
    )
    input_json = canonical_json(dict(inputs))
    current_output_json = canonical_json(dict(current_outputs))
    challenger_output_json = canonical_json(challenger_outputs)
    identity = {
        "ticker": ticker.strip().upper(), "as_of_date": as_of_date, "surface": surface,
        "input_hash": hashlib.sha256(input_json.encode()).hexdigest(),
        "current_output_hash": hashlib.sha256(current_output_json.encode()).hexdigest(),
        "challenger_output_hash": hashlib.sha256(challenger_output_json.encode()).hexdigest(),
        "current_model_version": registered_current["model_version"],
        "challenger_model_version": challenger["model_version"],
    }
    return {
        "shadow_snapshot_id": content_hash(identity),
        **identity,
        "current_config_hash": registered_current["config_hash"],
        "challenger_config_hash": challenger["config_hash"],
        "input_json": input_json,
        "current_output_json": current_output_json,
        "challenger_output_json": challenger_output_json,
        "entry_score_delta": challenger_outputs["entry_score_delta"],
        "signal_changed": int(bool(challenger_outputs["signal_changed"])),
        "coverage_mode": challenger_outputs["coverage_mode"],
    }


def persist_live_shadow_observation(
    *, ticker: str, as_of_date: str, surface: str,
    inputs: Mapping[str, object], current_outputs: Mapping[str, object],
    db_path: object = None,
) -> str | None:
    """Freeze the live prediction before its paired shadow observation."""
    if not ACTIVE_SHADOW_ENABLED:
        return None
    from src.data.database import save_prediction_snapshot, save_shadow_decision_snapshot

    model = current_model_registration()
    prediction = build_prediction_snapshot(
        ticker=ticker, as_of_date=as_of_date, model=model,
        inputs=inputs, outputs=current_outputs, simulation_source="live",
    )
    save_prediction_snapshot(prediction, db_path)
    save_shadow_decision_snapshot(build_shadow_snapshot(
        ticker=ticker, as_of_date=as_of_date, surface=surface,
        inputs=inputs, current_outputs=current_outputs,
    ), db_path)
    return str(prediction["prediction_id"])


def reconcile_shadow_prediction_lineage(db_path: object = None) -> dict[str, int]:
    """Add missing predictions from the earliest immutable shadow observation per daily key."""
    from src.data.database import (
        get_prediction_snapshots, get_shadow_decision_snapshots, save_prediction_snapshot,
    )

    predictions = get_prediction_snapshots(db_path=db_path)
    existing = {
        (str(row["ticker"]), str(row["as_of_date"]), str(row["model_version"]), str(row["config_hash"]))
        for row in predictions
    }
    candidates: dict[tuple[str, str, str, str], Mapping[str, object]] = {}
    shadows = sorted(
        get_shadow_decision_snapshots(db_path=db_path),
        key=lambda row: (str(row.get("created_at") or ""), str(row["shadow_snapshot_id"])),
    )
    for row in shadows:
        key = (
            str(row["ticker"]), str(row["as_of_date"]),
            str(row["current_model_version"]), str(row["current_config_hash"]),
        )
        candidates.setdefault(key, row)
    created = 0
    for key, shadow in candidates.items():
        if key in existing:
            continue
        prediction = build_prediction_snapshot(
            ticker=key[0], as_of_date=key[1],
            model={"model_version": key[2], "config_hash": key[3]},
            inputs=json.loads(str(shadow.get("input_json") or "{}")),
            outputs=json.loads(str(shadow.get("current_output_json") or "{}")),
            simulation_source="live" if shadow.get("surface") == "decision_dashboard" else "historical_replay",
            created_at=str(shadow.get("created_at") or "") or None,
        )
        save_prediction_snapshot(prediction, db_path)
        existing.add(key)
        created += 1
    return {"candidate_keys": len(candidates), "created": created}


def backfill_shadow_history(db_path: object = None) -> dict[str, int]:
    """Create idempotent shadow comparisons from existing immutable predictions."""
    import json

    from src.data.database import (
        get_prediction_snapshots, get_shadow_decision_snapshots, save_shadow_decision_snapshot,
    )

    if COVERAGE_AWARE_PROMOTED:
        return {"attempted": 0, "created": 0, "signal_changes": 0}
    before = len(get_shadow_decision_snapshots(db_path=db_path))
    attempted = changed = 0
    for prediction in get_prediction_snapshots(db_path=db_path):
        inputs = json.loads(str(prediction["input_json"]))
        current_outputs = json.loads(str(prediction["output_json"]))
        snapshot = build_shadow_snapshot(
            ticker=str(prediction["ticker"]), as_of_date=str(prediction["as_of_date"]),
            surface="historical_replay", inputs={**inputs, "industry_calibrated": False},
            current_outputs=current_outputs,
            current_model={"model_version": prediction["model_version"],
                           "config_hash": prediction["config_hash"]},
        )
        save_shadow_decision_snapshot(snapshot, db_path)
        attempted += 1
        changed += int(snapshot["signal_changed"])
    after = len(get_shadow_decision_snapshots(db_path=db_path))
    return {"attempted": attempted, "created": after - before, "signal_changes": changed}
