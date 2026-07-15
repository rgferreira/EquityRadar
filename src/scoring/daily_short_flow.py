"""Transparent, prospective-only FINRA daily short-flow shadow evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from statistics import mean


ROLLING_SESSIONS = 10
SLOPE_SESSIONS = 10
MINIMUM_OBSERVATIONS = 20
FRESH_DAYS = 4
STALE_DAYS = 7
SLOPE_DEADBAND = 0.05
FULL_STRENGTH_SLOPE = 0.25
MODIFIER_CAP = 2.0


def _date(value: object) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _neutral(reason: str, *, observations: int = 0, latest_trade_date: str | None = None) -> dict[str, object]:
    return {
        "slope_pp_per_session": 0.0,
        "rolling_share_pct": None,
        "confidence": 0.0,
        "entry_modifier": 0.0,
        "exit_modifier": 0.0,
        "coverage": "unavailable" if observations < MINIMUM_OBSERVATIONS else "stale",
        "observations": observations,
        "latest_trade_date": latest_trade_date,
        "persistence": 0.0,
        "rationale": reason,
    }


def daily_short_flow_evidence(
    rows: Sequence[Mapping[str, object]] | None, *, as_of: date | str | None = None,
) -> dict[str, object]:
    """Convert the slope of the 10-session short-volume-share mean into shadow evidence.

    Rising daily short-sale flow is tested as entry caution; falling flow is tested as
    easing pressure. This is a transaction-flow proxy, never outstanding short interest.
    Rows not verifiably known by the cutoff remain unavailable rather than directional.
    """
    cutoff = _date(as_of) if as_of is not None else date.today()
    if cutoff is None:
        raise ValueError("Invalid daily short-flow cutoff")
    by_trade_date: dict[date, float] = {}
    for row in rows or []:
        trade_date = _date(row.get("trade_date"))
        known_at = _date(row.get("known_at"))
        total = row.get("total_volume")
        short = row.get("short_volume")
        if (
            trade_date is None or trade_date > cutoff or known_at is None or known_at > cutoff
            or row.get("known_at_status") != "verified_observed"
            or not isinstance(total, (int, float)) or float(total) <= 0
            or not isinstance(short, (int, float)) or float(short) < 0
        ):
            continue
        by_trade_date[trade_date] = 100.0 * float(short) / float(total)
    ordered = sorted(by_trade_date.items())
    observations = len(ordered)
    latest = ordered[-1][0] if ordered else None
    latest_text = latest.isoformat() if latest else None
    if observations < MINIMUM_OBSERVATIONS:
        return _neutral(
            f"Need {MINIMUM_OBSERVATIONS} point-in-time daily observations; {observations} available.",
            observations=observations, latest_trade_date=latest_text,
        )
    age_days = (cutoff - latest).days if latest else STALE_DAYS + 1
    if age_days > STALE_DAYS:
        return _neutral(
            f"Latest daily-flow observation is {age_days} days old; stale evidence is neutral.",
            observations=observations, latest_trade_date=latest_text,
        )

    shares = [value for _, value in ordered]
    rolling = [mean(shares[index - ROLLING_SESSIONS + 1:index + 1])
               for index in range(ROLLING_SESSIONS - 1, len(shares))]
    recent = rolling[-SLOPE_SESSIONS:]
    x_mean = (len(recent) - 1) / 2
    denominator = sum((index - x_mean) ** 2 for index in range(len(recent)))
    slope = sum((index - x_mean) * (value - mean(recent))
                for index, value in enumerate(recent)) / denominator
    differences = [current - previous for previous, current in zip(recent, recent[1:])]
    expected_positive = slope >= 0
    persistence = (
        sum((change >= 0) == expected_positive for change in differences) / len(differences)
        if differences else 0.0
    )
    coverage_confidence = min(1.0, observations / 30)
    freshness_confidence = 1.0 if age_days <= FRESH_DAYS else 0.5
    confidence = coverage_confidence * freshness_confidence * (0.5 + 0.5 * persistence)
    magnitude = max(0.0, abs(slope) - SLOPE_DEADBAND)
    strength = min(1.0, magnitude / (FULL_STRENGTH_SLOPE - SLOPE_DEADBAND))
    direction = 1.0 if slope > 0 else -1.0 if slope < 0 else 0.0
    pressure = direction * MODIFIER_CAP * strength * confidence
    entry_modifier = -pressure
    exit_modifier = pressure
    coverage = "ready" if confidence >= 0.70 else "limited"
    direction_text = "rising" if slope > SLOPE_DEADBAND else "falling" if slope < -SLOPE_DEADBAND else "flat"
    return {
        "slope_pp_per_session": round(slope, 4),
        "rolling_share_pct": round(recent[-1], 3),
        "confidence": round(confidence, 3),
        "entry_modifier": round(entry_modifier, 1),
        "exit_modifier": round(exit_modifier, 1),
        "coverage": coverage,
        "observations": observations,
        "latest_trade_date": latest_text,
        "persistence": round(persistence, 3),
        "rationale": (
            f"10-session FINRA daily short-flow average is {direction_text} at "
            f"{slope:+.3f} percentage points per session; confidence-gated shadow "
            f"modifier is capped at +/-{MODIFIER_CAP:.0f}. Flow is not open short interest."
        ),
    }
