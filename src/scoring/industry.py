"""Transparent, confidence-aware Industry Feature scoring."""

from statistics import median
from typing import Mapping


def _num(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _confidence_adjust(score: float, confidence: float) -> float:
    return round(50 + max(0.0, min(confidence, 1.0)) * (score - 50), 1)


def _average(values: list[float], default: float = 50) -> float:
    return sum(values) / len(values) if values else default


def business_quality_score(research: Mapping[str, object] | None) -> tuple[float, float, list[str]]:
    profile = research.get("profile", {}) if research else {}
    if not isinstance(profile, Mapping):
        return 50, 0, ["No quality inputs"]
    components: list[float] = []
    explanations: list[str] = []
    growth = _num(profile.get("revenue_growth"))
    if growth is not None:
        score = 100 if growth >= .25 else 80 if growth >= .15 else 60 if growth >= .05 else 35 if growth >= 0 else 10
        components.append(score); explanations.append(f"Revenue growth {growth:.1%}: {score:.0f}")
    for field, label in (("operating_margin", "Operating margin"), ("free_cash_flow_margin", "FCF margin")):
        value = _num(profile.get(field))
        if value is not None:
            score = 100 if value >= .25 else 80 if value >= .15 else 60 if value >= .05 else 40 if value >= 0 else 15
            components.append(score); explanations.append(f"{label} {value:.1%}: {score:.0f}")
    gross = _num(profile.get("gross_margin"))
    if gross is not None:
        score = 90 if gross >= .75 else 75 if gross >= .60 else 55 if gross >= .40 else 30
        components.append(score); explanations.append(f"Gross margin {gross:.1%}: {score:.0f}")
    raw = _average(components)
    confidence = min(1.0, len(components) / 4)
    return _confidence_adjust(raw, confidence), confidence, explanations


def relative_valuation_score(research: Mapping[str, object] | None) -> tuple[float, float, list[str]]:
    if not research:
        return 50, 0, ["No peer valuation inputs"]
    profile = research.get("profile", {})
    peers = research.get("peer_profiles", [])
    if not isinstance(profile, Mapping) or not isinstance(peers, list):
        return 50, 0, ["No peer valuation inputs"]
    components: list[float] = []
    explanations: list[str] = []
    for field, label in (("forward_pe", "Forward P/E"), ("price_to_sales", "Price/sales")):
        company = _num(profile.get(field))
        peer_values = [value for peer in peers if isinstance(peer, Mapping) and (value := _num(peer.get(field))) is not None and value > 0]
        if company and peer_values:
            peer_median = median(peer_values)
            ratio = company / peer_median
            score = 90 if ratio <= .70 else 75 if ratio <= .90 else 60 if ratio <= 1.10 else 40 if ratio <= 1.30 else 20
            components.append(score)
            explanations.append(f"{label} {company:.2f} vs peer median {peer_median:.2f}: {score}")
    raw = _average(components)
    confidence = min(1.0, len(peers) / 5) * min(1.0, len(components) / 2)
    return _confidence_adjust(raw, confidence), confidence, explanations


def analyst_sentiment_score(research: Mapping[str, object] | None) -> tuple[float, float, list[str]]:
    if not research:
        return 50, 0, ["No analyst inputs"]
    recs = research.get("recommendations", {})
    revisions = research.get("eps_revisions", {})
    targets = research.get("price_targets", {})
    components: list[tuple[float, float]] = []
    explanations: list[str] = []
    coverage = 0.0
    if isinstance(recs, Mapping):
        strong_buy = _num(recs.get("strongBuy")) or 0
        buy = _num(recs.get("buy")) or 0
        hold = _num(recs.get("hold")) or 0
        sell = _num(recs.get("sell")) or 0
        strong_sell = _num(recs.get("strongSell")) or 0
        total = strong_buy + buy + hold + sell + strong_sell
        if total:
            rating = (100 * strong_buy + 75 * buy + 50 * hold + 25 * sell) / total
            components.append((rating, .35)); coverage = total
            explanations.append(f"Consensus {int(strong_buy + buy)} positive / {int(total)} analysts: {rating:.0f}")
    if isinstance(revisions, Mapping):
        up = (_num(revisions.get("upLast30days")) or 0) + (_num(revisions.get("upLast7days")) or 0)
        down = (_num(revisions.get("downLast30days")) or 0) + (_num(revisions.get("downLast7days")) or 0)
        if up + down:
            revision_score = 50 + 50 * (up - down) / (up + down)
            components.append((revision_score, .45))
            explanations.append(f"EPS revisions {up:.0f} up / {down:.0f} down: {revision_score:.0f}")
    if isinstance(targets, Mapping):
        upside = _num(targets.get("median_upside_pct"))
        low, high, median_target = _num(targets.get("low")), _num(targets.get("high")), _num(targets.get("median"))
        if upside is not None:
            target_score = max(0, min(100, 50 + upside * 1.5))
            dispersion_discount = 1.0
            if low and high and median_target:
                dispersion_discount = max(.35, 1 - (high - low) / median_target)
            target_score = 50 + (target_score - 50) * dispersion_discount
            components.append((target_score, .20))
            explanations.append(f"Median target upside {upside:.1f}%: {target_score:.0f}")
    if not components:
        return 50, 0, ["No analyst inputs"]
    weight = sum(item[1] for item in components)
    raw = sum(score * component_weight for score, component_weight in components) / weight
    confidence = min(1.0, coverage / 12) * .6 + min(1.0, len(components) / 3) * .4
    return _confidence_adjust(raw, confidence), confidence, explanations


def industry_entry_score(
    technical: float, risk: float, research: Mapping[str, object] | None,
) -> dict[str, object]:
    quality, quality_confidence, quality_notes = business_quality_score(research)
    relative_value, value_confidence, value_notes = relative_valuation_score(research)
    analyst, analyst_confidence, analyst_notes = analyst_sentiment_score(research)
    score = round(quality * .25 + relative_value * .30 + technical * .20 + risk * .15 + analyst * .10, 1)
    return {
        "score": score,
        "business_quality": quality,
        "relative_valuation": relative_value,
        "technical_timing": technical,
        "risk_resilience": risk,
        "analyst_sentiment": analyst,
        "quality_confidence": quality_confidence,
        "valuation_confidence": value_confidence,
        "analyst_confidence": analyst_confidence,
        "quality_notes": quality_notes,
        "valuation_notes": value_notes,
        "analyst_notes": analyst_notes,
    }
