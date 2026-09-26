"""Prospective BTC perpetual-positioning evidence for the unified shorts Shadow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from statistics import median


MINIMUM_OBSERVATIONS = 30
LOOKBACK_DAYS = 90
CHANGE_DAYS = 10
MAXIMUM_AGE_DAYS = 2
MODIFIER_CAP = 2.0
SHORT_CHANGE_FULL_STRENGTH_PP = 1.0
SELL_FLOW_FULL_STRENGTH_PP = 2.0
OPEN_INTEREST_FULL_STRENGTH_PCT = 10.0


def _date(value: object) -> date | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _neutral(reason: str, *, observations: int = 0, latest_period_date: str | None = None) -> dict[str, object]:
    return {
        "confidence": 0.0, "entry_modifier": 0.0, "exit_modifier": 0.0,
        "coverage": "unavailable", "observations": observations,
        "latest_period_date": latest_period_date, "short_account_pct": None,
        "short_delta_10d_pp": 0.0, "taker_sell_vs_average_pp": 0.0,
        "open_interest_change_10d_pct": 0.0, "squeeze_score": 0.0,
        "downside_pressure_score": 0.0, "state": "Unavailable",
        "source": "Binance BTC perpetual", "included_in_shadow": False,
        "rationale": reason,
    }


def btc_short_pressure_evidence(
    rows: Sequence[Mapping[str, object]] | None, *, as_of: date | str | None = None,
) -> dict[str, object]:
    """Map completed, known BTC perpetual periods to a bounded Shadow modifier.

    High/rising short-account participation becomes an Entry-positive squeeze signal only
    when taker selling is below its 10-day baseline. The same crowding with above-baseline
    selling is Entry-negative downside pressure. Open-interest expansion confirms magnitude.
    """
    cutoff = _date(as_of or date.today())
    if cutoff is None:
        raise ValueError("Invalid BTC short-pressure cutoff")
    eligible: dict[date, Mapping[str, object]] = {}
    for row in rows or []:
        period = _date(row.get("period_date"))
        known_at = _date(row.get("known_at"))
        if (
            period is None or period >= cutoff or known_at is None or known_at > cutoff
            or row.get("known_at_status") != "verified_observed"
        ):
            continue
        eligible[period] = row
    ordered = sorted(eligible.items())
    latest = ordered[-1][0] if ordered else None
    latest_text = latest.isoformat() if latest else None
    if len(ordered) < MINIMUM_OBSERVATIONS:
        return _neutral(
            f"Need {MINIMUM_OBSERVATIONS} verified completed periods; {len(ordered)} available.",
            observations=len(ordered), latest_period_date=latest_text,
        )
    age_days = (cutoff - latest).days if latest else MAXIMUM_AGE_DAYS + 1
    if age_days > MAXIMUM_AGE_DAYS:
        result = _neutral(
            f"Latest BTC perpetual period is {age_days} days old; stale evidence is neutral.",
            observations=len(ordered), latest_period_date=latest_text,
        )
        result["coverage"] = "stale"
        return result

    window = [row for _, row in ordered[-LOOKBACK_DAYS:]]
    current = window[-1]
    baseline = window[-(CHANGE_DAYS + 1)]
    short_values = [float(row["short_account_pct"]) for row in window]
    current_short = short_values[-1]
    center = median(short_values)
    upper = sorted(short_values)[max(0, int(0.90 * (len(short_values) - 1)))]
    crowding_level = _clamp((current_short - center) / max(0.25, upper - center))
    short_delta = current_short - float(baseline["short_account_pct"])
    crowding_trend = _clamp(short_delta / SHORT_CHANGE_FULL_STRENGTH_PP)
    crowding = 0.6 * crowding_level + 0.4 * crowding_trend

    def sell_share(row: Mapping[str, object]) -> float:
        buy, sell = float(row["taker_buy_volume"]), float(row["taker_sell_volume"])
        return 100 * sell / (buy + sell) if buy + sell > 0 else 50.0

    current_sell = sell_share(current)
    average_sell = sum(sell_share(row) for row in window[-10:]) / 10
    sell_delta = current_sell - average_sell
    exhaustion = _clamp(-sell_delta / SELL_FLOW_FULL_STRENGTH_PP)
    active_selling = _clamp(sell_delta / SELL_FLOW_FULL_STRENGTH_PP)
    baseline_oi = float(baseline["open_interest_value_quote"])
    oi_change = (
        (float(current["open_interest_value_quote"]) / baseline_oi - 1) * 100
        if baseline_oi > 0 else 0.0
    )
    oi_confirmation = 0.5 + 0.5 * _clamp(oi_change / OPEN_INTEREST_FULL_STRENGTH_PCT)
    squeeze = crowding * exhaustion * oi_confirmation
    downside = crowding * active_selling * oi_confirmation
    confidence = min(1.0, len(ordered) / LOOKBACK_DAYS)
    net = (squeeze - downside) * confidence
    entry_modifier = round(MODIFIER_CAP * net, 1)
    exit_modifier = round(-entry_modifier, 1)
    state = (
        "Squeeze potential" if entry_modifier > 0
        else "Downside short pressure" if entry_modifier < 0
        else "Mixed / neutral short pressure"
    )
    return {
        "confidence": round(confidence, 3), "entry_modifier": entry_modifier,
        "exit_modifier": exit_modifier, "coverage": "ready", "observations": len(ordered),
        "latest_period_date": latest_text, "short_account_pct": round(current_short, 4),
        "short_delta_10d_pp": round(short_delta, 4),
        "taker_sell_vs_average_pp": round(sell_delta, 4),
        "open_interest_change_10d_pct": round(oi_change, 4),
        "squeeze_score": round(squeeze, 4), "downside_pressure_score": round(downside, 4),
        "state": state, "source": "Binance BTC perpetual", "included_in_shadow": True,
        "rationale": (
            "BTC Shadow v1: elevated/rising short-account participation is squeeze-positive only "
            "with below-baseline taker selling; above-baseline selling is downside pressure. "
            f"Open-interest expansion confirms magnitude; modifier is capped at +/-{MODIFIER_CAP:.0f}."
        ),
    }
