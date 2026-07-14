"""Coverage gates for research evidence that is not eligible for live scoring."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date


OPTIONS_MIN_DATES = 20
OPTIONS_MIN_COVERAGE = 0.75
OPTIONS_MAX_GAP_DAYS = 7


def _payload(row: Mapping[str, object]) -> dict[str, object]:
    value = row.get("payload_json") or row.get("payload") or {}
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return dict(value) if isinstance(value, Mapping) else {}


def options_evidence_report(
    histories: Mapping[str, Sequence[Mapping[str, object]]],
) -> list[dict[str, object]]:
    """Report continuity and short-interest overlap without scoring options."""
    reports = []
    for ticker, rows in sorted(histories.items()):
        daily = [row for row in rows if row.get("snapshot_type") != "historical_short_interest"]
        option_dates: list[date] = []
        overlap = 0
        for row in daily:
            payload = _payload(row)
            options = payload.get("options") if isinstance(payload.get("options"), Mapping) else {}
            has_options = any(options.get(key) is not None for key in (
                "put_call_oi_ratio", "put_call_volume_ratio", "median_contract_iv",
            ))
            if not has_options:
                continue
            try:
                option_dates.append(date.fromisoformat(str(row["snapshot_date"])[:10]))
            except (ValueError, KeyError):
                continue
            short = payload.get("short") if isinstance(payload.get("short"), Mapping) else {}
            overlap += int(any(short.get(key) is not None for key in ("shares_short", "short_percent_float")))
        option_dates = sorted(set(option_dates))
        gaps = [(right - left).days for left, right in zip(option_dates, option_dates[1:])]
        coverage = len(option_dates) / len(daily) if daily else 0.0
        max_gap = max(gaps) if gaps else None
        eligible = (
            len(option_dates) >= OPTIONS_MIN_DATES
            and coverage >= OPTIONS_MIN_COVERAGE
            and max_gap is not None and max_gap <= OPTIONS_MAX_GAP_DAYS
            and overlap >= OPTIONS_MIN_DATES
        )
        reports.append({
            "ticker": ticker,
            "daily_snapshots": len(daily),
            "options_dates": len(option_dates),
            "coverage_pct": round(coverage * 100, 1),
            "max_gap_days": max_gap,
            "short_overlap_dates": overlap,
            "research_ready": eligible,
        })
    return reports
