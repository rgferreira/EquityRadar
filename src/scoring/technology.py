"""Transparent, industry-relative Technology Potential shadow evidence."""

from __future__ import annotations

from collections.abc import Mapping
from statistics import median


COMPONENT_WEIGHTS = {
    "r_and_d_intensity": 0.35,
    "revenue_growth": 0.25,
    "gross_margin": 0.15,
    "free_cash_flow_margin": 0.15,
    "balance_sheet_capacity": 0.10,
}


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _percentile(value: float, peers: list[float]) -> float:
    """Return a transparent higher-is-better percentile including the company."""
    sample = [*peers, value]
    below = sum(item < value for item in sample)
    equal = sum(item == value for item in sample)
    return round(100 * (below + 0.5 * equal) / len(sample), 1)


def technology_potential_evidence(
    research: Mapping[str, object] | None,
) -> dict[str, object]:
    """Build a confidence-gated proxy; missing evidence is neutral, never directional."""
    profile = research.get("profile", {}) if research else {}
    peers = research.get("peer_profiles", []) if research else []
    if not isinstance(profile, Mapping) or not isinstance(peers, list):
        profile, peers = {}, []

    company_market_cap = _number(profile.get("market_cap"))
    company_net_debt = _number(profile.get("net_debt"))
    company_values = {
        "r_and_d_intensity": _number(profile.get("r_and_d_intensity")),
        "revenue_growth": _number(profile.get("revenue_growth")),
        "gross_margin": _number(profile.get("gross_margin")),
        "free_cash_flow_margin": _number(profile.get("free_cash_flow_margin")),
        "balance_sheet_capacity": (
            -company_net_debt / company_market_cap
            if company_net_debt is not None and company_market_cap and company_market_cap > 0 else None
        ),
    }
    component_scores: dict[str, float] = {}
    component_inputs: dict[str, object] = {}
    available_weight = 0.0
    for field, weight in COMPONENT_WEIGHTS.items():
        value = company_values[field]
        peer_values: list[float] = []
        for peer in peers:
            if not isinstance(peer, Mapping):
                continue
            if field == "balance_sheet_capacity":
                market_cap, net_debt = _number(peer.get("market_cap")), _number(peer.get("net_debt"))
                peer_value = -net_debt / market_cap if net_debt is not None and market_cap and market_cap > 0 else None
            else:
                peer_value = _number(peer.get(field))
            if peer_value is not None:
                peer_values.append(peer_value)
        if value is None or len(peer_values) < 2:
            continue
        component_scores[field] = _percentile(value, peer_values)
        component_inputs[field] = {
            "company": round(value, 6), "peer_count": len(peer_values),
            "peer_median": round(median(peer_values), 6),
        }
        available_weight += weight

    if not component_scores:
        return {
            "score": 50.0, "confidence": 0.0, "entry_modifier": 0.0,
            "coverage": "unavailable", "components": {}, "inputs": {},
            "rationale": "No comparable Technology Potential evidence; neutral shadow adjustment.",
        }
    weighted = sum(component_scores[field] * COMPONENT_WEIGHTS[field] for field in component_scores)
    score = weighted / available_weight
    peer_confidence = min(1.0, len(peers) / 5)
    confidence = available_weight * peer_confidence
    if "r_and_d_intensity" not in component_scores:
        confidence = min(confidence, 0.50)
    modifier = max(-5.0, min(5.0, (score - 50.0) / 10.0 * confidence))
    return {
        "score": round(score, 1), "confidence": round(confidence, 3),
        "entry_modifier": round(modifier, 1),
        "coverage": "ready" if confidence >= 0.70 else "limited",
        "components": {field: round(value, 1) for field, value in component_scores.items()},
        "inputs": component_inputs,
        "rationale": (
            f"Industry-relative proxy across {len(component_scores)} available component(s); "
            "modifier is confidence-gated and capped at +/-5 shadow Entry points."
        ),
    }
