import pytest

from src.portfolio import simulate_allocation_scenario


def test_scenario_preserves_internal_trade_value_and_changes_concentration():
    result = simulate_allocation_scenario(
        {"AAA": 800, "BBB": 200}, {"AAA": -200, "BBB": 200}, current_cash=0,
    )
    assert result["after_total"] == 1000
    assert result["after_cash"] == 0
    assert result["after_max_weight_pct"] == 60
    assert result["after_hhi"] < result["before_hhi"]


def test_external_cash_can_fund_hypothetical_purchase():
    result = simulate_allocation_scenario(
        {"AAA": 1000}, {"BBB": 500}, external_cash_change=500,
    )
    assert result["after_total"] == 1500
    assert result["after_cash"] == 0


def test_scenario_rejects_impossible_sale_or_unfunded_buy():
    with pytest.raises(ValueError):
        simulate_allocation_scenario({"AAA": 100}, {"AAA": -101})
    with pytest.raises(ValueError):
        simulate_allocation_scenario({"AAA": 100}, {"AAA": 1})
