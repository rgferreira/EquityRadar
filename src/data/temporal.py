"""Point-in-time metadata and conservative evidence-availability rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Mapping


class KnownAtStatus(str, Enum):
    """Verification state for the timestamp used by historical reconstruction."""

    VERIFIED_PUBLISHED = "verified_published"
    VERIFIED_OBSERVED = "verified_observed"
    UNVERIFIED_LEGACY = "unverified_legacy"


VERIFIED_KNOWN_AT_STATUSES = {
    KnownAtStatus.VERIFIED_PUBLISHED.value,
    KnownAtStatus.VERIFIED_OBSERVED.value,
}


@dataclass(frozen=True)
class TemporalMetadata:
    period_end: str | None = None
    published_at: str | None = None
    known_at: str | None = None
    fetched_at: str | None = None
    known_at_status: str = KnownAtStatus.UNVERIFIED_LEGACY.value

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


def observed_at_fetch(
    fetched_at: str, *, period_end: str | None = None, published_at: str | None = None,
) -> TemporalMetadata:
    """Build safe metadata for a newly captured provider response.

    A verified publication timestamp is preferred. Otherwise the fetch time is
    a conservative upper bound: the system proves only that it observed the
    evidence then, never that it was public at the underlying period end.
    """
    return TemporalMetadata(
        period_end=period_end,
        published_at=published_at,
        known_at=published_at or fetched_at,
        fetched_at=fetched_at,
        known_at_status=(
            KnownAtStatus.VERIFIED_PUBLISHED.value
            if published_at else KnownAtStatus.VERIFIED_OBSERVED.value
        ),
    )


def _parse_timestamp(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _cutoff_timestamp(value: date | str | datetime) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.max)
    else:
        text = str(value)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if len(text) == 10:
            parsed = datetime.combine(parsed.date(), time.max)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def evidence_known_by(record: Mapping[str, object] | None, as_of: date | str | datetime) -> bool:
    """Return true only for evidence with a verified `known_at` by cutoff."""
    if not record or str(record.get("known_at_status") or "") not in VERIFIED_KNOWN_AT_STATUSES:
        return False
    known_at = _parse_timestamp(record.get("known_at"))
    cutoff = _cutoff_timestamp(as_of)
    return bool(known_at and cutoff and known_at <= cutoff)
