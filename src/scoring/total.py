"""Weighted composite score."""

def calculate_total_score(technical: int | float, valuation: int | float, risk: int | float) -> float:
    return round(technical * 0.50 + valuation * 0.30 + risk * 0.20, 1)
