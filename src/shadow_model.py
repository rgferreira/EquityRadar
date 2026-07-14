"""Inactive shadow-model computation and immutable comparison snapshots."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from src.model_registry import (
    canonical_json, content_hash, coverage_aware_shadow_registration,
    current_model_registration,
)
from src.scoring.decision import entry_label
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


def build_shadow_snapshot(
    *, ticker: str, as_of_date: str, surface: str,
    inputs: Mapping[str, object], current_outputs: Mapping[str, object],
    current_model: Mapping[str, object] | None = None,
) -> dict[str, object]:
    registered_current = dict(current_model or current_model_registration())
    challenger = coverage_aware_shadow_registration()
    challenger_outputs = coverage_aware_shadow_output(inputs, current_outputs)
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


def backfill_shadow_history(db_path: object = None) -> dict[str, int]:
    """Create idempotent shadow comparisons from existing immutable predictions."""
    import json

    from src.data.database import (
        get_prediction_snapshots, get_shadow_decision_snapshots, save_shadow_decision_snapshot,
    )

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
