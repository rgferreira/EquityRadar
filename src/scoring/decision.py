"""Decision-oriented scores derived from the MVP component scores."""

from src.scoring.total import calculate_total_score


def calculate_entry_score(technical: int | float, valuation: int | float, risk: int | float) -> float:
    """Higher means a more attractive potential entry or add."""
    return calculate_total_score(technical, valuation, risk)


def calculate_coverage_aware_entry_score(
    technical: int | float, valuation: int | float, risk: int | float, *,
    valuation_available: bool,
) -> float:
    """Promoted policy: renormalize verified factors when valuation is unavailable."""
    if valuation_available:
        score = float(technical) * .50 + float(valuation) * .30 + float(risk) * .20
    else:
        score = float(technical) * (5 / 7) + float(risk) * (2 / 7)
    return round(max(0.0, min(100.0, score)), 1)


def calculate_exit_review_score(technical: int | float, risk: int | float) -> float:
    """Higher means the holding deserves more urgent sell/reassess review."""
    return round((100 - technical) * 0.60 + (100 - risk) * 0.40, 1)


def entry_label(score: int | float) -> str:
    if score >= 70:
        return "Buy candidate"
    if score >= 55:
        return "Watch"
    return "Wait"


def exit_review_label(score: int | float) -> str:
    if score >= 70:
        return "Sell review"
    if score >= 50:
        return "Reassess"
    return "Hold / no review"
