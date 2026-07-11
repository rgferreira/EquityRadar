"""Transparent technical-momentum scoring."""

def technical_score_components(metrics: dict[str, float | None]) -> list[tuple[str, int]]:
    """Return transparent technical-score contributors as (label, points)."""
    components: list[tuple[str, int]] = []
    price = metrics["latest_price"]
    for average in ("ma_50", "ma_100", "ma_200"):
        if metrics.get(average) is not None and price > metrics[average]:
            components.append((f"Price above {average.replace('_', '-').upper()}", 15))
    for period in ("return_1m", "return_3m", "return_6m", "return_12m"):
        if metrics.get(period) is not None and metrics[period] > 0:
            components.append((f"Positive {period.replace('return_', '').upper()} return", 10))
    if metrics.get("drawdown_from_52w_high") is not None and metrics["drawdown_from_52w_high"] >= -10:
        components.append(("Within 10% of 52-week high", 15))
    return components


def calculate_technical_score(metrics: dict[str, float | None]) -> int:
    """Score trend and momentum from 0 to 100 using available metrics."""
    return min(sum(points for _, points in technical_score_components(metrics)), 100)


def explain_technical_score(metrics: dict[str, float | None]) -> str:
    components = technical_score_components(metrics)
    return "; ".join(f"{label} (+{points})" for label, points in components) or "No positive momentum signals"
