from src.scoring.position_action import initiation_diagnostic, position_action


def test_unowned_uses_initiation_vocabulary():
    assert initiation_diagnostic(75, "Buy candidate", "Hold / no review") == "Initiate · Buy candidate"
    assert initiation_diagnostic(40, "Wait", "Sell review") == "Initiate · Wait (Sell review)"


def test_attractive_underweight_holding_is_add_candidate():
    result = position_action(72, 25, current_weight_pct=5, target_weight_pct=10)
    assert result["action"] == "Add candidate"
    assert result["add_score"] > 72


def test_overweight_position_can_be_trim_without_company_exit_signal():
    result = position_action(60, 45, current_weight_pct=25, target_weight_pct=10)
    assert result["action"] == "Trim review"
    assert result["trim_score"] >= 60


def test_company_deterioration_forces_exit_review():
    assert position_action(80, 72, 5, 10)["action"] == "Exit review"


def test_no_target_uses_concentration_but_remains_bounded():
    result = position_action(90, 20, current_weight_pct=50)
    assert 0 <= result["add_score"] <= 100
    assert result["concentration_penalty"] > 0
