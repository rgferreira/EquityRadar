import pandas as pd
import pytest

from src.portfolio import (
    calculate_portfolio_history, calculate_return_risk_metrics, calculate_risk_contributions,
    calculate_time_weighted_return, enrich_holdings, normalize_performance,
    calculate_rebalance,
)


def test_portfolio_history_values_current_shares_across_prices():
    dates = pd.date_range("2026-01-01", periods=2)
    holdings = [{"ticker": "AAA", "shares": 2}, {"ticker": "BBB", "shares": 3}]
    histories = {
        "AAA": pd.DataFrame({"Close": [10.0, 12.0]}, index=dates),
        "BBB": pd.DataFrame({"Close": [20.0, 21.0]}, index=dates),
    }
    result = calculate_portfolio_history(holdings, histories)
    assert result.tolist() == [80.0, 87.0]


def test_enriched_holdings_adds_value_and_weight():
    rows = enrich_holdings(
        [{"ticker": "AAA", "shares": 2}, {"ticker": "BBB", "shares": 1}],
        {"AAA": 10.0, "BBB": 20.0},
    )
    assert [row["market_value"] for row in rows] == [20.0, 20.0]
    assert [row["weight_pct"] for row in rows] == [50.0, 50.0]


def test_enriched_holdings_calculates_cost_and_unrealized_pl_when_known():
    rows = enrich_holdings(
        [{"ticker": "AAA", "shares": 2}],
        {"AAA": 15.0},
        [{"ticker": "AAA", "shares": 2, "price_per_share": 10.0, "fees": 1.0}],
    )
    assert rows[0]["cost_basis"] == 21.0
    assert rows[0]["average_cost"] == 10.5
    assert rows[0]["unrealized_pl"] == 9.0
    assert rows[0]["return_pct"] == pytest.approx(42.857142857)


def test_enriched_holdings_does_not_invent_cost_for_legacy_lot():
    rows = enrich_holdings(
        [{"ticker": "AAA", "shares": 2}],
        {"AAA": 15.0},
        [{"ticker": "AAA", "shares": 2, "price_per_share": None, "fees": 0}],
    )
    assert rows[0]["cost_basis"] is None
    assert rows[0]["unrealized_pl"] is None


def test_portfolio_normalizes_market_value_and_cost_to_base_currency():
    rows = enrich_holdings(
        [{"ticker": "EURCO", "shares": 2}],
        {"EURCO": 15.0},
        [{"ticker": "EURCO", "shares": 2, "price_per_share": 10.0, "fees": 1.0}],
        {"EURCO": "EUR"}, {"EUR": 1.2}, "USD",
    )
    assert rows[0]["local_market_value"] == 30
    assert rows[0]["market_value"] == 36
    assert rows[0]["local_cost_basis"] == 21
    assert rows[0]["cost_basis"] == pytest.approx(25.2)
    assert rows[0]["unrealized_pl"] == pytest.approx(10.8)


def test_portfolio_history_applies_fx_conversion():
    dates = pd.date_range("2026-01-01", periods=2)
    result = calculate_portfolio_history(
        [{"ticker": "EURCO", "shares": 2}],
        {"EURCO": pd.DataFrame({"Close": [10.0, 12.0]}, index=dates)},
        {"EURCO": "EUR"}, {"EUR": 1.2}, "USD",
    )
    assert result.tolist() == pytest.approx([24.0, 28.8])


def test_normalize_performance_rebases_to_100():
    result = normalize_performance(pd.Series([50.0, 55.0, 45.0]))
    assert result.tolist() == pytest.approx([100.0, 110.0, 90.0])


def test_return_risk_metrics_include_return_drawdown_and_volatility():
    metrics = calculate_return_risk_metrics(pd.Series([100.0, 110.0, 88.0, 99.0]))
    assert metrics["total_return_pct"] == pytest.approx(-1.0)
    assert metrics["max_drawdown_pct"] == pytest.approx(-20.0)
    assert metrics["annualized_volatility_pct"] is not None


def test_risk_contributions_sum_to_100():
    dates = pd.date_range("2026-01-01", periods=5)
    contributions = calculate_risk_contributions(
        [{"ticker": "AAA", "shares": 2}, {"ticker": "BBB", "shares": 1}],
        {
            "AAA": pd.DataFrame({"Close": [10, 11, 10, 12, 11]}, index=dates),
            "BBB": pd.DataFrame({"Close": [20, 19, 21, 20, 22]}, index=dates),
        },
    )
    assert sum(contributions.values()) == pytest.approx(100.0)


def test_time_weighted_return_removes_external_deposit():
    dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
    values = pd.Series([100.0, 160.0, 176.0], index=dates)
    flows = pd.Series([0.0, 50.0, 0.0], index=dates)
    assert calculate_time_weighted_return(values, flows) == pytest.approx(21.0)


def test_rebalance_calculates_theoretical_trade_values():
    rows = calculate_rebalance(
        [{"ticker": "AAA", "market_value": 60}, {"ticker": "BBB", "market_value": 40}],
        {"AAA": 50, "BBB": 50}, 100,
    )
    assert rows[0]["trade_value"] == -10
    assert rows[1]["trade_value"] == 10
