"""Process-local cooldown for automatic dashboard-wide provider refreshes."""

from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock


DASHBOARD_AUTO_REFRESH_COOLDOWN = timedelta(minutes=1)
_lock = Lock()
_last_provider_refresh_at: datetime | None = None


def automatic_dashboard_refresh_due(now: datetime | None = None) -> bool:
    """Return whether navigation may trigger another provider-wide refresh."""
    current = now or datetime.now()
    with _lock:
        return (
            _last_provider_refresh_at is None
            or current - _last_provider_refresh_at >= DASHBOARD_AUTO_REFRESH_COOLDOWN
        )


def record_dashboard_provider_refresh(now: datetime | None = None) -> None:
    """Record a completed automatic or explicit provider-wide refresh."""
    global _last_provider_refresh_at
    with _lock:
        _last_provider_refresh_at = now or datetime.now()


def last_dashboard_provider_refresh_at() -> datetime | None:
    """Return the process-local timestamp of the latest provider-wide refresh."""
    with _lock:
        return _last_provider_refresh_at


def reset_dashboard_refresh_cooldown() -> None:
    """Reset process state for deterministic tests."""
    global _last_provider_refresh_at
    with _lock:
        _last_provider_refresh_at = None
