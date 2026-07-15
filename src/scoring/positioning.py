"""Transparent positioning scores and capped decision-score modifiers."""

from collections.abc import Mapping
from datetime import date, datetime


SHORT_INTEREST_MAX_AGE_DAYS = 28


def _num(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, value))


def _as_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def short_interest_freshness(
    record: Mapping[str, object] | None, as_of: date | datetime | str | None = None,
) -> dict[str, object]:
    """Classify report-date freshness; fetch time never makes old evidence current."""
    report_date = _as_date(
        (record or {}).get("reporting_date") or (record or {}).get("period_end")
    )
    cutoff = _as_date(as_of) if as_of is not None else date.today()
    if report_date is None or cutoff is None:
        return {
            "status": "missing", "report_date": None, "age_days": None,
            "scoring_eligible": False, "reason": "Short-interest report date is unavailable",
        }
    age_days = (cutoff - report_date).days
    if age_days < 0:
        status, eligible, reason = "future", False, "Short-interest report is after the decision date"
    elif age_days > SHORT_INTEREST_MAX_AGE_DAYS:
        status, eligible = "stale", False
        reason = f"Short-interest report is {age_days} days old and excluded from scores"
    else:
        status, eligible = "current", True
        reason = f"Short-interest report is {age_days} days old and within the {SHORT_INTEREST_MAX_AGE_DAYS}-day gate"
    return {
        "status": status, "report_date": report_date.isoformat(), "age_days": age_days,
        "scoring_eligible": eligible, "reason": reason,
    }


def effective_positioning_snapshot(
    snapshot: Mapping[str, object] | None,
    history: list[Mapping[str, object]],
    as_of: date | datetime | str | None = None,
) -> dict[str, object]:
    """Use the freshest dated short report while retaining non-short current evidence."""
    cutoff = _as_date(as_of) if as_of is not None else date.today()
    candidates: list[tuple[date, int, Mapping[str, object], str]] = []

    def add_candidate(record: Mapping[str, object], priority: int, source: str) -> None:
        short = record.get("short")
        report_date = _as_date(record.get("reporting_date") or record.get("period_end"))
        if (
            isinstance(short, Mapping) and report_date is not None
            and (cutoff is None or report_date <= cutoff)
            and any(_num(short.get(field)) is not None for field in (
                "shares_short", "short_percent_float", "short_change_pct", "days_to_cover",
            ))
        ):
            candidates.append((report_date, priority, record, source))

    if snapshot:
        add_candidate(snapshot, 1, str(snapshot.get("provider_name") or "current positioning"))
    for row in history:
        if isinstance(row, Mapping) and row.get("snapshot_type") == "historical_short_interest":
            add_candidate(row, 2, str(row.get("provider_name") or "FINRA history"))

    effective = dict(snapshot or {})
    if not candidates:
        effective["short"] = {}
        freshness = short_interest_freshness(None, as_of)
        return {"snapshot": effective, "source": "—", **freshness}

    latest_date = max(item[0] for item in candidates)
    same_date = sorted((item for item in candidates if item[0] == latest_date), key=lambda item: item[1])
    merged_short: dict[str, object] = {}
    sources: list[str] = []
    representative: Mapping[str, object] = same_date[-1][2]
    for _, _, record, source in same_date:
        short = record.get("short")
        if isinstance(short, Mapping):
            merged_short.update({key: value for key, value in short.items() if value is not None})
        if source not in sources:
            sources.append(source)
    freshness = short_interest_freshness(representative, as_of)
    effective["short"] = merged_short if freshness["scoring_eligible"] else {}
    effective["reporting_date"] = latest_date.isoformat()
    return {"snapshot": effective, "source": " + ".join(sources), **freshness}


def positioning_scores(snapshot: Mapping[str, object] | None) -> dict[str, object]:
    if not snapshot:
        return {"long_positioning": 50.0, "short_pressure": 50.0, "squeeze_potential": 50.0, "confidence": 0.0, "notes": ["No positioning snapshot"], "decision_implication": "Insufficient evidence"}
    short = snapshot.get("short", {}); options = snapshot.get("options", {})
    ownership = snapshot.get("ownership", {}); insiders = snapshot.get("insiders", {})
    short = short if isinstance(short, Mapping) else {}; options = options if isinstance(options, Mapping) else {}
    ownership = ownership if isinstance(ownership, Mapping) else {}; insiders = insiders if isinstance(insiders, Mapping) else {}
    evidence, available = [], 0

    short_float = _num(short.get("short_percent_float"))
    short_change = _num(short.get("short_change_pct"))
    days = _num(short.get("days_to_cover"))
    pc_oi = _num(options.get("put_call_oi_ratio")); pc_volume = _num(options.get("put_call_volume_ratio"))
    institutional = _num(ownership.get("institutional_percent"))
    buys, sells = _num(insiders.get("purchase_rows")), _num(insiders.get("sale_rows"))

    long_parts = []
    if pc_oi is not None:
        long_parts.append(_bounded(75 - 25 * pc_oi)); available += 1; evidence.append(f"Put/call open interest {pc_oi:.2f}")
    if institutional is not None:
        long_parts.append(_bounded(35 + institutional * 50)); available += 1; evidence.append(f"Institutional ownership {institutional:.1%}")
    if buys is not None and sells is not None and buys + sells:
        long_parts.append(50 + 50 * (buys - sells) / (buys + sells)); available += 1; evidence.append(f"Insider rows {buys:.0f} buy / {sells:.0f} sell")

    pressure_parts = []
    if short_float is not None:
        pressure_parts.append(_bounded(short_float * 500)); available += 1; evidence.append(f"Short float {short_float:.1%}")
    if short_change is not None:
        pressure_parts.append(_bounded(50 + short_change * 2)); available += 1; evidence.append(f"Short-interest change {short_change:+.1f}%")
    if days is not None:
        pressure_parts.append(_bounded(days * 12.5)); available += 1; evidence.append(f"Days to cover {days:.2f}")
    if pc_volume is not None:
        pressure_parts.append(_bounded(25 + pc_volume * 35)); available += 1; evidence.append(f"Put/call volume {pc_volume:.2f}")

    long_raw = sum(long_parts) / len(long_parts) if long_parts else 50
    pressure_raw = sum(pressure_parts) / len(pressure_parts) if pressure_parts else 50
    confidence = min(100.0, available / 7 * 100)
    long_score = 50 + (long_raw - 50) * confidence / 100
    pressure = 50 + (pressure_raw - 50) * confidence / 100
    squeeze_parts = [pressure]
    if short_float is not None: squeeze_parts.append(_bounded(short_float * 600))
    if days is not None: squeeze_parts.append(_bounded(days * 15))
    if pc_oi is not None: squeeze_parts.append(_bounded(80 - pc_oi * 20))
    squeeze = 50 + ((sum(squeeze_parts) / len(squeeze_parts)) - 50) * confidence / 100
    implication = (
        "Supportive positioning" if long_score >= 60 and pressure < 60
        else "Crowded short · squeeze watch" if pressure >= 60 and squeeze >= 60
        else "Positioning caution" if pressure >= 60 or long_score < 35
        else "Mixed / neutral positioning"
    )
    return {
        "long_positioning": round(long_score, 1), "short_pressure": round(pressure, 1),
        "squeeze_potential": round(squeeze, 1), "confidence": round(confidence, 1),
        "notes": evidence,
        "decision_implication": implication,
    }


def positioning_score_adjustments(
    snapshot: Mapping[str, object] | None, history: list[Mapping[str, object]],
    technical_score: float, as_of: date | datetime | str | None = None,
) -> dict[str, object]:
    """Return small reliability-gated modifiers for the established decision scores."""
    short_evidence = effective_positioning_snapshot(snapshot, history, as_of)
    effective_snapshot = short_evidence["snapshot"]
    current = positioning_scores(effective_snapshot if isinstance(effective_snapshot, Mapping) else None)
    if not effective_snapshot:
        return {"entry_adjustment": 0.0, "exit_adjustment": 0.0, "reliability": 0.0,
                "short_trend_pct": None, "history_points": 0, "notes": ["No current positioning snapshot"],
                "short_evidence_status": "missing", "short_report_date": None,
                "short_age_days": None, "short_scoring_eligible": False,
                "short_reversal_lever": "Unavailable · no dated short-interest evidence",
                "short_reversal_confirmed": False}
    cutoff = _as_date(as_of) if as_of is not None else date.today()
    short_rows = [
        row for row in history
        if isinstance(row, Mapping) and row.get("snapshot_type") == "historical_short_interest"
        and isinstance(row.get("short"), Mapping) and _num(row["short"].get("shares_short")) is not None
        and (_as_date(row.get("reporting_date") or row.get("period_end")) is not None)
        and (cutoff is None or _as_date(row.get("reporting_date") or row.get("period_end")) <= cutoff)
    ]
    unique = {str(row.get("reporting_date") or row.get("snapshot_date")): row for row in short_rows}
    ordered_all = [unique[key] for key in sorted(unique)]
    ordered = ordered_all if bool(short_evidence["scoring_eligible"]) else []
    trend = None
    if len(ordered) >= 2:
        latest = _num(ordered[-1]["short"].get("shares_short"))
        baseline_row = ordered[max(0, len(ordered) - 7)]
        baseline = _num(baseline_row["short"].get("shares_short"))
        if latest is not None and baseline:
            trend = (latest / baseline - 1) * 100
    effective_short = effective_snapshot.get("short", {}) if isinstance(effective_snapshot, Mapping) else {}
    latest_change = _num(effective_short.get("short_change_pct")) if isinstance(effective_short, Mapping) else None
    previous_change = (
        _num(ordered[-2]["short"].get("short_change_pct")) if len(ordered) >= 2 else None
    )
    reversal_confirmed = bool(
        latest_change is not None and previous_change is not None
        and latest_change < 0 <= previous_change and technical_score >= 60
    )
    if not short_evidence["scoring_eligible"]:
        age = short_evidence.get("age_days")
        suffix = "report date unavailable" if age is None else f"report is {age} days old"
        reversal_lever = f"Unavailable · {suffix}"
    elif reversal_confirmed:
        reversal_lever = "Confirmed · shorts falling with technical strength"
    elif latest_change is not None and latest_change > 0:
        reversal_lever = "Armed · short interest is still rising"
    elif latest_change is not None and latest_change < 0 and technical_score < 60:
        reversal_lever = "Watch · shorts easing without technical confirmation"
    else:
        reversal_lever = "Neutral · no new short-position reversal"

    current_confidence = float(current["confidence"]) / 100
    history_confidence = min(1.0, len(ordered) / 6) if short_evidence["scoring_eligible"] else 0.0
    reliability = current_confidence * (.60 + .40 * history_confidence)
    long_signal = (float(current["long_positioning"]) - 50) / 50
    pressure_signal = (float(current["short_pressure"]) - 50) / 50
    trend_signal = max(-1.0, min(1.0, (trend or 0) / 25))
    squeeze_confirmation = (
        max(-1.0, min(1.0, (float(current["squeeze_potential"]) - 50) / 50))
        if technical_score >= 60 else 0.0
    )
    entry_raw = .45 * long_signal - .30 * pressure_signal - .25 * trend_signal + .10 * squeeze_confirmation
    exit_raw = .40 * pressure_signal - .25 * long_signal + .35 * trend_signal
    if reversal_confirmed:
        entry_raw += .25
        exit_raw -= .20
    entry_adjustment = max(-5.0, min(5.0, 5 * entry_raw * reliability))
    exit_adjustment = max(-7.0, min(7.0, 7 * exit_raw * reliability))
    notes = [
        f"{len(ordered_all)} official FINRA observations",
        str(short_evidence["reason"]),
        "Six-report short trend unavailable" if trend is None else f"Six-report short-interest trend {trend:+.1f}%",
        f"Current positioning coverage {float(current['confidence']):.0f}/100",
        f"Modifier reliability {reliability:.0%}",
        f"Short reversal lever: {reversal_lever}",
    ]
    return {
        "entry_adjustment": round(entry_adjustment, 1), "exit_adjustment": round(exit_adjustment, 1),
        "reliability": round(reliability * 100, 1), "short_trend_pct": trend,
        "history_points": len(ordered_all), "notes": notes,
        "short_latest_change_pct": latest_change, "short_reversal_lever": reversal_lever,
        "short_reversal_confirmed": reversal_confirmed,
        "short_evidence_status": short_evidence["status"],
        "short_report_date": short_evidence["report_date"],
        "short_age_days": short_evidence["age_days"],
        "short_scoring_eligible": short_evidence["scoring_eligible"],
        "short_evidence_source": short_evidence["source"],
    }


def apply_positioning_adjustment(base_score: float, adjustment: float) -> float:
    return round(max(0.0, min(100.0, base_score + adjustment)), 1)
