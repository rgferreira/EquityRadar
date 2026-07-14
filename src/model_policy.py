"""Explicit governance policies for research outputs used by live scores."""

from __future__ import annotations

from enum import Enum
from typing import Mapping


class LearningScorePolicy(str, Enum):
    """Whether backtested-learning evidence may alter operational scores."""

    DIAGNOSTIC_ONLY = "diagnostic_only"
    OPERATIONAL = "operational"


# Phase 3.8 PR-001 quarantine. Promotion requires a separately approved,
# scientifically evaluated policy change; it is intentionally not a UI toggle.
ACTIVE_LEARNING_SCORE_POLICY = LearningScorePolicy.DIAGNOSTIC_ONLY


def governed_learning_adjustments(
    diagnostic: Mapping[str, object],
    policy: LearningScorePolicy = ACTIVE_LEARNING_SCORE_POLICY,
) -> dict[str, object]:
    """Separate calculated research evidence from adjustments applied to scores."""
    diagnostic_entry = float(diagnostic.get("entry_adjustment") or 0)
    diagnostic_exit = float(diagnostic.get("exit_adjustment") or 0)
    applied = policy is LearningScorePolicy.OPERATIONAL
    return {
        "policy": policy.value,
        "is_applied": applied,
        "diagnostic_entry_adjustment": diagnostic_entry,
        "diagnostic_exit_adjustment": diagnostic_exit,
        "applied_entry_adjustment": diagnostic_entry if applied else 0.0,
        "applied_exit_adjustment": diagnostic_exit if applied else 0.0,
        "label": "Applied to operational scores" if applied else "Diagnostic only · quarantined",
    }
