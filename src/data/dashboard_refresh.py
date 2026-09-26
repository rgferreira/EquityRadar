"""Process-local cooldown for automatic dashboard-wide provider refreshes."""

from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock


DASHBOARD_AUTO_REFRESH_COOLDOWN = timedelta(minutes=1)
DASHBOARD_SNAPSHOT_MAX_AGE = timedelta(minutes=15)
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


def dashboard_snapshot_is_fresh(
    fetched_at: object, now: datetime | None = None,
) -> bool:
    """Return whether a persisted snapshot is recent enough to imply current data."""
    if not fetched_at:
        return False
    try:
        fetched = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    current = now or datetime.now(tz=fetched.tzinfo)
    if fetched.tzinfo is not None and current.tzinfo is None:
        current = current.replace(tzinfo=fetched.tzinfo)
    elif fetched.tzinfo is None and current.tzinfo is not None:
        fetched = fetched.replace(tzinfo=current.tzinfo)
    age = current - fetched
    return timedelta(0) <= age <= DASHBOARD_SNAPSHOT_MAX_AGE


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


# No Streamlit calls in workers: a page continues showing its last complete generation.
from concurrent.futures import ThreadPoolExecutor, as_completed

_refresh_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dashboard-warm")
_refresh_future = None
_refresh_tickers: tuple[str, ...] = ()
_refresh_generation = 0
_refresh_next_attempt = datetime.min


def _warm_dashboard(tickers: tuple[str, ...]) -> dict[str, object]:
    from src.data.price_cache import fetch_cached_price_history
    successes = 0
    with ThreadPoolExecutor(max_workers=min(6, len(tickers))) as pool:
        futures = [pool.submit(fetch_cached_price_history, symbol, force_refresh=True) for symbol in tickers]
        for future in as_completed(futures):
            try:
                future.result()
                successes += 1
            except Exception:
                pass
    return {"successes": successes, "total": len(tickers)}


def schedule_dashboard_price_refresh(tickers: list[str]) -> bool:
    global _refresh_future, _refresh_tickers, _refresh_generation, _refresh_next_attempt
    normalized = tuple(sorted(set(tickers)))
    with _lock:
        if not normalized or (_refresh_future and not _refresh_future.done()) or datetime.now() < _refresh_next_attempt:
            return False
        _refresh_tickers = normalized
        _refresh_generation += 1
        _refresh_next_attempt = datetime.now() + timedelta(minutes=1)
        _refresh_future = _refresh_pool.submit(_warm_dashboard, normalized)
    return True


def dashboard_price_refresh_state(tickers: list[str]) -> dict[str, object]:
    with _lock:
        if not _refresh_future or _refresh_tickers != tuple(sorted(set(tickers))):
            return {"status": "idle", "generation": 0}
        if not _refresh_future.done():
            return {"status": "running", "generation": _refresh_generation}
        try:
            result = _refresh_future.result()
            return {"status": "ready" if result["successes"] == result["total"] else "partial",
                    "generation": _refresh_generation, **result}
        except Exception:
            return {"status": "failed", "generation": _refresh_generation}
