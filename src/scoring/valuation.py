"""Transparent fundamentals-based valuation scoring."""

from collections.abc import Mapping


def _lower_is_better(value: float, bands: tuple[float, float, float, float]) -> int:
    if value <= bands[0]: return 100
    if value <= bands[1]: return 75
    if value <= bands[2]: return 50
    if value <= bands[3]: return 25
    return 0


def _growth_score(value: float) -> int:
    # FMP growth fields are decimal rates: 0.10 means 10%.
    if value >= 0.20: return 100
    if value >= 0.10: return 75
    if value >= 0: return 50
    if value >= -0.10: return 25
    return 0


def valuation_score_breakdown(
    fundamentals: Mapping[str, object] | None,
) -> dict[str, int]:
    if not fundamentals:
        return {}
    scores: dict[str, int] = {}
    multiple_rules = {
        "trailing_pe": (10, 18, 25, 35),
        "forward_pe": (10, 18, 25, 35),
        "price_to_sales_ttm": (1, 3, 6, 10),
    }
    for field, bands in multiple_rules.items():
        value = fundamentals.get(field)
        if isinstance(value, (int, float)) and value > 0:
            scores[field] = _lower_is_better(float(value), bands)
    for field in ("revenue_growth", "eps_growth"):
        value = fundamentals.get(field)
        if isinstance(value, (int, float)):
            scores[field] = _growth_score(float(value))
    return scores


def calculate_valuation_score(fundamentals: Mapping[str, object] | None = None) -> int:
    breakdown = valuation_score_breakdown(fundamentals)
    return round(sum(breakdown.values()) / len(breakdown)) if breakdown else 50


def explain_valuation_score(fundamentals: Mapping[str, object] | None) -> str:
    breakdown = valuation_score_breakdown(fundamentals)
    if not breakdown:
        return "No meaningful fundamentals are available; using a neutral score of 50."
    labels = {
        "trailing_pe": "Trailing P/E", "forward_pe": "Forward P/E",
        "price_to_sales_ttm": "Price/sales TTM", "revenue_growth": "Revenue growth",
        "eps_growth": "EPS growth",
    }
    return "; ".join(f"{labels[key]}: {score}/100" for key, score in breakdown.items())
