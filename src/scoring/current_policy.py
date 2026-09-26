"""Shared final combination of the existing Dashboard policy; unchanged weights."""
from src.scoring.decision import (calculate_coverage_aware_entry_score, calculate_exit_review_score,
                                  entry_label, exit_review_label)
from src.scoring.positioning import apply_positioning_adjustment


def combine_current_decisions(*, technical, valuation, risk, industry_score,
                              valuation_available, entry_modifier, exit_modifier,
                              learning_entry, learning_exit):
    entry = (float(industry_score) if industry_score is not None else calculate_coverage_aware_entry_score(
        technical, valuation, risk, valuation_available=valuation_available))
    exit_score = calculate_exit_review_score(technical, risk)
    entry = apply_positioning_adjustment(entry, float(entry_modifier))
    exit_score = apply_positioning_adjustment(exit_score, float(exit_modifier))
    entry = apply_positioning_adjustment(entry, float(learning_entry))
    exit_score = apply_positioning_adjustment(exit_score, float(learning_exit))
    return {"entry_score": entry, "entry_signal": entry_label(entry),
            "exit_score": exit_score, "exit_signal": exit_review_label(exit_score)}
