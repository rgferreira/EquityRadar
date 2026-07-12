"""Portfolio-aware action layer built on top of company research scores."""

from __future__ import annotations


def initiation_diagnostic(entry_score: float, entry_signal: str, exit_signal: str) -> str:
    """Use initiation vocabulary for securities not currently owned."""
    if entry_score >= 70:
        return "Initiate · Buy candidate"
    if entry_score >= 55:
        return "Initiate · Watch"
    return f"Initiate · Wait ({exit_signal})" if exit_signal != "Hold / no review" else "Initiate · Wait"


def position_action(
    entry_score: float,
    exit_score: float,
    current_weight_pct: float,
    target_weight_pct: float | None = None,
    risk_contribution_pct: float | None = None,
) -> dict[str, object]:
    """Convert company evidence into Add/Hold/Monitor/Trim/Exit for an owned position."""
    weight = max(0.0, float(current_weight_pct))
    target = float(target_weight_pct) if target_weight_pct is not None else None
    gap = (target - weight) if target is not None else 0.0
    target_adjustment = max(-15.0, min(15.0, gap * 1.5)) if target is not None else 0.0
    concentration_penalty = max(0.0, min(15.0, (weight - 20.0) * 0.75))
    risk_penalty = 0.0
    if risk_contribution_pct is not None:
        risk_penalty = max(0.0, min(10.0, (float(risk_contribution_pct) - weight) * 0.5))
    add_score = max(0.0, min(100.0, float(entry_score) + target_adjustment - concentration_penalty - risk_penalty))
    overweight_pressure = max(0.0, min(20.0, -gap * 1.5)) if target is not None else concentration_penalty
    trim_score = max(0.0, min(100.0, float(exit_score) + overweight_pressure + risk_penalty))

    if float(exit_score) >= 70:
        action = "Exit review"
    elif trim_score >= 60:
        action = "Trim review"
    elif add_score >= 65 and float(exit_score) < 50:
        action = "Add candidate"
    elif float(exit_score) >= 50 or (add_score < 45 and float(exit_score) >= 40):
        action = "Monitor closely"
    else:
        action = "Hold"

    notes = [f"Company Entry evidence {float(entry_score):.1f}", f"Exit-review evidence {float(exit_score):.1f}",
             f"Current portfolio weight {weight:.1f}%"]
    if target is not None:
        notes.append(f"Target {target:.1f}% ({gap:+.1f} percentage-point gap)")
    else:
        notes.append("No target weight set; only concentration modifies sizing")
    if concentration_penalty:
        notes.append(f"Concentration penalty −{concentration_penalty:.1f}")
    if risk_penalty:
        notes.append(f"Excess risk-contribution penalty −{risk_penalty:.1f}")
    return {
        "action": action, "add_score": round(add_score, 1), "trim_score": round(trim_score, 1),
        "current_weight_pct": round(weight, 2), "target_weight_pct": target,
        "target_adjustment": round(target_adjustment, 1),
        "concentration_penalty": round(concentration_penalty, 1), "risk_penalty": round(risk_penalty, 1),
        "notes": notes,
    }
