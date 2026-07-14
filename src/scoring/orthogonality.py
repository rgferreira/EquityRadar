"""Auditable checks for duplicated evidence across decision-score components."""

from __future__ import annotations

import json
from collections.abc import Mapping

import numpy as np
import pandas as pd

from src.backtesting import decision_outcome, latest_model_runs

CORE_COMPONENTS = ["Technical", "Valuation", "Risk resilience", "Positioning modifier"]

# These are architectural overlaps, independent of the empirical sample. They
# document raw evidence or gating logic reused by more than one component.
SEMANTIC_OVERLAPS = [
    {
        "Components": "Technical ↔ Risk resilience",
        "Shared evidence": "Drawdown from the 52-week high",
        "Assessment": "Resolved in v4",
        "Action": "Drawdown now belongs only to Risk resilience; Technical trend weights were rescaled to retain a 0–100 range.",
    },
    {
        "Components": "Industry & analysts ↔ Market positioning",
        "Shared evidence": "Analyst upgrades/downgrades",
        "Assessment": "Resolved in v4",
        "Action": "Analyst actions now belong only to Industry & analysts; positioning uses ownership, options and short-interest evidence.",
    },
    {
        "Components": "Technical ↔ Market positioning",
        "Shared evidence": "Technical score gates squeeze and short-reversal bonuses",
        "Assessment": "Interaction, not pure duplication",
        "Action": "Retain as an explicit interaction but do not increase both weights for the same confirmation event.",
    },
    {
        "Components": "Core score ↔ Backtested learning",
        "Shared evidence": "Lessons are trained on outcomes of decisions produced by the core score",
        "Assessment": "Feedback-loop risk",
        "Action": "Keep the learning modifier tightly capped and require novel, decision-aware evidence, as Phase 3.7 now does.",
    },
]


def _latest_runs(runs: list[Mapping[str, object]]) -> list[Mapping[str, object]]:
    return list(latest_model_runs(runs))


def audit_frame(runs: list[Mapping[str, object]]) -> pd.DataFrame:
    rows = []
    for run in _latest_runs(runs):
        try:
            inputs = json.loads(str(run.get("inputs_json") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            inputs = {}
        positioning = inputs.get("positioning_modifier") or {}
        outcome = decision_outcome(run)
        rows.append({
            "Ticker": run.get("ticker"), "Cutoff": run.get("as_of_date"),
            "Technical": run.get("technical_score"), "Valuation": run.get("valuation_score"),
            "Risk resilience": run.get("risk_score"),
            "Positioning modifier": positioning.get("entry_adjustment", 0.0),
            "Forward outcome": outcome.get("composite"),
        })
    return pd.DataFrame(rows)


def _incremental_r2(frame: pd.DataFrame, target: str, component: str, features: list[str]) -> float | None:
    data = frame[[*features, target]].dropna()
    if len(data) < max(12, len(features) * 3):
        return None
    y = data[target].astype(float).to_numpy()
    if float(np.std(y)) == 0:
        return None

    def r2(columns: list[str]) -> float:
        x = data[columns].astype(float).to_numpy() if columns else np.empty((len(data), 0))
        x = np.column_stack([np.ones(len(data)), x])
        prediction = x @ np.linalg.lstsq(x, y, rcond=None)[0]
        return 1 - float(np.sum((y - prediction) ** 2)) / float(np.sum((y - y.mean()) ** 2))

    return max(0.0, r2(features) - r2([feature for feature in features if feature != component]))


def score_orthogonality_audit(runs: list[Mapping[str, object]]) -> dict[str, object]:
    """Measure component overlap and incremental outcome information."""
    frame = audit_frame(runs)
    available = [component for component in CORE_COMPONENTS if component in frame and frame[component].notna().sum() >= 3]
    pair_rows: list[dict[str, object]] = []
    if len(available) >= 2:
        correlations = frame[available].astype(float).rank().corr()
        for index, left in enumerate(available):
            for right in available[index + 1:]:
                value = correlations.loc[left, right]
                if pd.isna(value):
                    continue
                magnitude = abs(float(value))
                pair_rows.append({
                    "Components": f"{left} ↔ {right}", "Spearman correlation": round(float(value), 2),
                    "Overlap level": "High" if magnitude >= .75 else "Review" if magnitude >= .55 else "Distinct",
                    "Interpretation": (
                        "Likely duplicate behavior; merge or reduce a weight."
                        if magnitude >= .75 else "Material shared behavior; inspect raw inputs."
                        if magnitude >= .55 else "No material empirical overlap detected."
                    ),
                })
    component_rows = []
    for component in available:
        usable = frame[[component, "Forward outcome"]].dropna()
        predictive = usable[component].rank().corr(usable["Forward outcome"].rank()) if len(usable) >= 5 else None
        incremental = _incremental_r2(frame, "Forward outcome", component, available)
        component_rows.append({
            "Component": component,
            "Outcome correlation": None if predictive is None or pd.isna(predictive) else round(float(predictive), 2),
            "Incremental R²": None if incremental is None else round(incremental, 3),
            "Observation": (
                "Insufficient matured outcomes" if incremental is None else
                "Low unique information in this sample" if incremental < .01 else
                "Some unique information" if incremental < .05 else "Material unique information"
            ),
        })
    flagged = [row for row in pair_rows if row["Overlap level"] != "Distinct"]
    recommendations = [row["Action"] for row in SEMANTIC_OVERLAPS]
    if flagged:
        recommendations.insert(0, "Empirical overlap exists: test one-at-a-time component removal before changing production weights.")
    else:
        recommendations.insert(0, "No strong empirical pair overlap is proven yet; fix direct semantic duplication first and preserve weights pending more outcomes.")
    return {
        "sample_size": len(frame), "matured_outcomes": int(frame["Forward outcome"].notna().sum()) if not frame.empty else 0,
        "pairwise": pair_rows, "components": component_rows,
        "semantic": SEMANTIC_OVERLAPS, "recommendations": recommendations,
    }
