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
ONBOARDING_PROVIDER_KEY = "finra_daily_volume_onboarding"
MIN_ONBOARDING_OBSERVATIONS = 20


def _refresh(
    tickers: list[str], provider_factory: Callable[[], FINRADailyShortVolumeProvider],
    db_path: str | Path | None, lookback_days: int, force_full_lookback: bool,
) -> dict[str, int]:
    return backfill_finra_daily_short_volume(
        tickers, provider_factory(), db_path, lookback_days=lookback_days,
        force_full_lookback=force_full_lookback,
    )


def _finished(
    future: Future[dict[str, int]], db_path: str | Path | None, tickers: list[str],
    track_onboarding: bool,
) -> None:
    global _future, _failure
    with _lock:
        try:
            future.result()
            _failure = None
            record_provider_health("finra_daily_volume", HEALTH_TICKER, "healthy", db_path=db_path)
            if track_onboarding:
                for ticker in tickers:
                    record_provider_health(
                        ONBOARDING_PROVIDER_KEY, ticker, "healthy", db_path=db_path,
                    )
        except Exception as exc:
            _failure = (datetime.now(), str(exc))
            record_provider_health(
                "finra_daily_volume", HEALTH_TICKER, "failed", error=str(exc),
                cooldown_until=(datetime.now() + RETRY_COOLDOWN).isoformat(timespec="seconds"),
                db_path=db_path,
            )
            if track_onboarding:
                for ticker in tickers:
                    record_provider_health(
                        ONBOARDING_PROVIDER_KEY, ticker, "failed", error=str(exc),
                        cooldown_until=(datetime.now() + RETRY_COOLDOWN).isoformat(timespec="seconds"),
                        db_path=db_path,
                    )
        _future = None


def finra_daily_volume_onboarding_due(
    tickers: list[str], db_path: str | Path | None = None, *, now: datetime | None = None,
) -> list[str]:
    """Return supported tickers needing a one-time replay of already cached files."""
    current = now or datetime.now()
    states = {
        str(row["ticker"]): row for row in get_provider_health_states(db_path)
        if row["provider_key"] == ONBOARDING_PROVIDER_KEY
    }
    due: list[str] = []
    for ticker in dict.fromkeys(symbol.strip().upper() for symbol in tickers):
        if not finra_supports_ticker(ticker):
            continue
        if len(get_finra_daily_short_volume(ticker, db_path)) >= MIN_ONBOARDING_OBSERVATIONS:
            continue
        state = states.get(ticker)
        attempted = str(state.get("last_attempt_at") or "") if state else ""
        try:
            attempted_today = datetime.fromisoformat(attempted).date() >= current.date()
        except ValueError:
            attempted_today = False
        if not attempted_today:
            due.append(ticker)
    return due


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
    eligible = list(dict.fromkeys(
        ticker.strip().upper() for ticker in tickers if finra_supports_ticker(ticker)
    ))
    if not eligible:
        return False
    onboarding = finra_daily_volume_onboarding_due(eligible, db_path)
    refresh_tickers = onboarding or eligible
    force_full_lookback = bool(onboarding)
    with _lock:
        if _future is not None or (
            not force_full_lookback and not finra_daily_volume_refresh_due(db_path)
        ):
            return False
        if _failure and datetime.now() - _failure[0] < RETRY_COOLDOWN:
            return False
        record_provider_health("finra_daily_volume", HEALTH_TICKER, "running", db_path=db_path)
        if force_full_lookback:
            for ticker in refresh_tickers:
                record_provider_health(
                    ONBOARDING_PROVIDER_KEY, ticker, "running", db_path=db_path,
                )
        _future = _executor.submit(
            _refresh, refresh_tickers, provider_factory, db_path, lookback_days,
            force_full_lookback,
        )
        _future.add_done_callback(
            lambda completed, path=db_path, symbols=refresh_tickers,
            onboarding_run=force_full_lookback:
            _finished(completed, path, symbols, onboarding_run)
        )
        return True


def finra_daily_volume_status(ticker: str, db_path: str | Path | None = None) -> str:
    if not finra_supports_ticker(ticker):
        return "Not applicable"
    with _lock:
        if _future is not None:
            return "Backfilling"
        failure = _failure
    if len(get_finra_daily_short_volume(ticker, db_path)) >= MIN_ONBOARDING_OBSERVATIONS:
        return "Ready"
    return "Provider unavailable" if failure else "Pending"
