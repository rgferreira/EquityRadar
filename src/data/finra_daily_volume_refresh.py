"""Non-blocking refresh for FINRA consolidated daily short-sale-volume flow."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Callable

from src.data.database import (
    get_finra_daily_short_volume, get_provider_health_states, record_provider_health,
)
from src.data.finra_daily_volume import (
    FINRADailyShortVolumeProvider, backfill_finra_daily_short_volume,
)
from src.data.finra_short_interest import finra_supports_ticker


_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="finra-daily-flow")
_lock = RLock()
_future: Future[dict[str, int]] | None = None
_failure: tuple[datetime, str] | None = None
RETRY_COOLDOWN = timedelta(minutes=15)
HEALTH_TICKER = "__WATCHLIST__"


def _refresh(
    tickers: list[str], provider_factory: Callable[[], FINRADailyShortVolumeProvider],
    db_path: str | Path | None, lookback_days: int,
) -> dict[str, int]:
    return backfill_finra_daily_short_volume(
        tickers, provider_factory(), db_path, lookback_days=lookback_days,
    )


def _finished(future: Future[dict[str, int]], db_path: str | Path | None) -> None:
    global _future, _failure
    with _lock:
        try:
            future.result()
            _failure = None
            record_provider_health("finra_daily_volume", HEALTH_TICKER, "healthy", db_path=db_path)
        except Exception as exc:
            _failure = (datetime.now(), str(exc))
            record_provider_health(
                "finra_daily_volume", HEALTH_TICKER, "failed", error=str(exc),
                cooldown_until=(datetime.now() + RETRY_COOLDOWN).isoformat(timespec="seconds"),
                db_path=db_path,
            )
        _future = None


def finra_daily_volume_refresh_due(
    db_path: str | Path | None = None, *, now: datetime | None = None,
) -> bool:
    current = now or datetime.now()
    state = next((
        row for row in get_provider_health_states(db_path)
        if row["provider_key"] == "finra_daily_volume" and row["ticker"] == HEALTH_TICKER
    ), None)
    if not state or not state.get("last_attempt_at"):
        return True
    try:
        return datetime.fromisoformat(str(state["last_attempt_at"])).date() < current.date()
    except ValueError:
        return True


def schedule_finra_daily_volume_refresh(
    tickers: list[str], *, lookback_days: int = 120,
    provider_factory: Callable[[], FINRADailyShortVolumeProvider] = FINRADailyShortVolumeProvider,
    db_path: str | Path | None = None,
) -> bool:
    """Schedule one watchlist-wide download so files are never fetched per ticker."""
    global _future
    eligible = [ticker.strip().upper() for ticker in tickers if finra_supports_ticker(ticker)]
    if not eligible:
        return False
    with _lock:
        if _future is not None or not finra_daily_volume_refresh_due(db_path):
            return False
        if _failure and datetime.now() - _failure[0] < RETRY_COOLDOWN:
            return False
        record_provider_health("finra_daily_volume", HEALTH_TICKER, "running", db_path=db_path)
        _future = _executor.submit(_refresh, eligible, provider_factory, db_path, lookback_days)
        _future.add_done_callback(lambda completed, path=db_path: _finished(completed, path))
        return True


def finra_daily_volume_status(ticker: str, db_path: str | Path | None = None) -> str:
    if not finra_supports_ticker(ticker):
        return "Not applicable"
    with _lock:
        if _future is not None:
            return "Backfilling"
        failure = _failure
    if get_finra_daily_short_volume(ticker, db_path):
        return "Ready"
    return "Provider unavailable" if failure else "Pending"
