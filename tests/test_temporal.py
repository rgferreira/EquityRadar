from datetime import datetime, timezone

from src.data.temporal import KnownAtStatus, evidence_known_by, observed_at_fetch


def test_period_end_and_fetch_time_do_not_implicitly_establish_known_at():
    assert evidence_known_by({
        "period_end": "2026-03-31", "fetched_at": "2026-05-01T10:00:00+00:00",
    }, "2026-12-31") is False


def test_verified_known_at_has_exact_boundary_semantics():
    record = {
        "known_at": "2026-05-01T10:00:00+00:00",
        "known_at_status": KnownAtStatus.VERIFIED_OBSERVED.value,
    }

    assert evidence_known_by(record, "2026-05-01T09:59:59+00:00") is False
    assert evidence_known_by(record, "2026-05-01T10:00:00+00:00") is True
    assert evidence_known_by(record, "2026-05-01T10:00:01+00:00") is True
    assert evidence_known_by(record, "2026-05-01") is True


def test_observed_snapshot_is_not_backdated_to_period_end():
    metadata = observed_at_fetch(
        "2026-07-14T08:00:00+00:00", period_end="2026-06-30",
    )

    assert metadata.period_end == "2026-06-30"
    assert metadata.known_at == "2026-07-14T08:00:00+00:00"
    assert metadata.known_at_status == KnownAtStatus.VERIFIED_OBSERVED.value
    assert evidence_known_by(metadata.as_dict(), "2026-07-13") is False
    assert evidence_known_by(metadata.as_dict(), datetime(2026, 7, 14, 8, tzinfo=timezone.utc)) is True


def test_verified_publication_time_takes_precedence_over_fetch_time():
    metadata = observed_at_fetch(
        "2026-05-03T08:00:00+00:00",
        period_end="2026-03-31",
        published_at="2026-05-01T20:00:00+00:00",
    )

    assert metadata.known_at == metadata.published_at
    assert metadata.known_at_status == KnownAtStatus.VERIFIED_PUBLISHED.value
