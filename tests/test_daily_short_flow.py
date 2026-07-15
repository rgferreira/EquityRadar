from datetime import date, timedelta

from src.scoring.daily_short_flow import daily_short_flow_evidence


def rows(*, rising: bool = True, known_offset: int = 0):
    start = date(2026, 6, 1)
    values = range(30, 60) if rising else range(60, 30, -1)
    return [
        {
            "trade_date": (start + timedelta(days=index)).isoformat(),
            "short_volume": value,
            "total_volume": 100,
            "known_at": (start + timedelta(days=index + known_offset)).isoformat(),
            "known_at_status": "verified_observed",
        }
        for index, value in enumerate(values)
    ]


def test_rising_rolling_flow_is_bounded_shadow_entry_caution():
    evidence = daily_short_flow_evidence(rows(), as_of="2026-06-30")

    assert evidence["slope_pp_per_session"] > 0
    assert -2 <= evidence["entry_modifier"] < 0
    assert 0 < evidence["exit_modifier"] <= 2
    assert evidence["confidence"] > 0
    assert evidence["coverage"] in {"ready", "limited"}


def test_falling_rolling_flow_is_easing_pressure():
    evidence = daily_short_flow_evidence(rows(rising=False), as_of="2026-06-30")

    assert evidence["slope_pp_per_session"] < 0
    assert evidence["entry_modifier"] > 0
    assert evidence["exit_modifier"] < 0


def test_after_cutoff_or_stale_evidence_is_neutral():
    after_cutoff = daily_short_flow_evidence(
        rows(known_offset=30), as_of="2026-06-30",
    )
    stale = daily_short_flow_evidence(rows(), as_of="2026-07-20")

    assert after_cutoff["entry_modifier"] == 0
    assert after_cutoff["observations"] < 20
    assert stale["entry_modifier"] == stale["exit_modifier"] == 0
    assert stale["coverage"] == "stale"
