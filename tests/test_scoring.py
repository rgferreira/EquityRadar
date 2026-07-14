import pandas as pd

from src.scoring.risk import calculate_risk_score, explain_risk_score
from src.scoring.technical import calculate_technical_score, explain_technical_score
from src.scoring.total import calculate_total_score
from src.scoring.valuation import calculate_valuation_score, valuation_score_breakdown
from src.scoring.decision import (
    calculate_coverage_aware_entry_score, calculate_entry_score,
    calculate_exit_review_score, entry_label, exit_review_label,
)


def test_technical_score_for_strong_momentum():
    metrics = {"latest_price": 110, "ma_50": 100, "ma_100": 95, "ma_200": 90,
               "return_1m": 2, "return_3m": 3, "return_6m": 4, "return_12m": 5,
               "drawdown_from_52w_high": -5}
    assert calculate_technical_score(metrics) == 100


def test_technical_score_no_longer_reuses_risk_drawdown():
    base = {"latest_price": 110, "ma_50": 100, "ma_100": 120, "ma_200": 120,
            "return_1m": 2, "return_3m": -3, "return_6m": -4, "return_12m": -5}
    near_high = calculate_technical_score({**base, "drawdown_from_52w_high": -2})
    deep_drawdown = calculate_technical_score({**base, "drawdown_from_52w_high": -35})
    assert near_high == deep_drawdown == 30


def test_placeholder_and_total_scores():
    assert calculate_valuation_score() == 50
    assert calculate_total_score(80, 50, 70) == 69.0


def test_valuation_ignores_negative_multiples_and_averages_available_inputs():
    fundamentals = {
        "trailing_pe": -4,
        "forward_pe": 15,
        "price_to_sales_ttm": 2,
        "revenue_growth": 0.12,
        "eps_growth": None,
    }
    breakdown = valuation_score_breakdown(fundamentals)
    assert "trailing_pe" not in breakdown
    assert breakdown == {"forward_pe": 75, "price_to_sales_ttm": 75, "revenue_growth": 75}
    assert calculate_valuation_score(fundamentals) == 75


def test_risk_score_is_bounded():
    history = pd.DataFrame({"Close": [100, 50, 100, 50, 100]})
    assert 0 <= calculate_risk_score({"drawdown_from_52w_high": -50}, history) <= 100


def test_score_explanations_include_underlying_signals():
    metrics = {"latest_price": 110, "ma_50": 100, "ma_100": 95, "ma_200": 90,
               "return_1m": 2, "return_3m": 3, "return_6m": 4, "return_12m": 5,
               "drawdown_from_52w_high": -5}
    history = pd.DataFrame({"Close": [100, 101, 102, 103, 104]})
    assert "Price above MA-50" in explain_technical_score(metrics)
    assert "Drawdown penalty" in explain_risk_score(metrics, history)


def test_decision_scores_have_clear_opposing_meaning():
    assert calculate_entry_score(80, 50, 70) == 69.0
    assert calculate_exit_review_score(80, 70) == 24.0
    assert entry_label(75) == "Buy candidate"
    assert exit_review_label(75) == "Sell review"


def test_promoted_entry_policy_renormalizes_only_when_valuation_is_unavailable():
    assert calculate_coverage_aware_entry_score(
        80, 50, 60, valuation_available=False,
    ) == 74.3
    assert calculate_coverage_aware_entry_score(
        80, 50, 60, valuation_available=True,
    ) == 67.0
