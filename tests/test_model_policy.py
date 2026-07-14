from src.model_policy import (
    ACTIVE_LEARNING_SCORE_POLICY,
    LearningScorePolicy,
    governed_learning_adjustments,
)
from src.scoring.positioning import apply_positioning_adjustment


def test_learning_is_quarantined_by_default_but_diagnostic_is_preserved():
    result = governed_learning_adjustments({"entry_adjustment": 3.2, "exit_adjustment": -3.2})

    assert ACTIVE_LEARNING_SCORE_POLICY is LearningScorePolicy.DIAGNOSTIC_ONLY
    assert result["diagnostic_entry_adjustment"] == 3.2
    assert result["diagnostic_exit_adjustment"] == -3.2
    assert result["applied_entry_adjustment"] == 0
    assert result["applied_exit_adjustment"] == 0
    assert result["is_applied"] is False
    assert apply_positioning_adjustment(61.4, result["applied_entry_adjustment"]) == 61.4
    assert apply_positioning_adjustment(28.7, result["applied_exit_adjustment"]) == 28.7


def test_future_operational_policy_is_explicit_and_testable():
    result = governed_learning_adjustments(
        {"entry_adjustment": 2.5, "exit_adjustment": -2.5},
        policy=LearningScorePolicy.OPERATIONAL,
    )

    assert result["applied_entry_adjustment"] == 2.5
    assert result["applied_exit_adjustment"] == -2.5
    assert result["is_applied"] is True


def test_missing_learning_evidence_stays_neutral():
    result = governed_learning_adjustments({})

    assert result["diagnostic_entry_adjustment"] == 0
    assert result["diagnostic_exit_adjustment"] == 0
    assert result["applied_entry_adjustment"] == 0
    assert result["applied_exit_adjustment"] == 0
