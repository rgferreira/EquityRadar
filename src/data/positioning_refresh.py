"""Non-blocking daily positioning refresh with stale-data preservation."""

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Callable

from src.data.database import get_cached_positioning, get_positioning_history, save_positioning_snapshot
from src.data.finra_short_interest import FINRAShortInterestProvider, backfill_finra_short_history
from src.data.positioning import YahooPositioningProvider
from src.data.temporal import observed_at_fetch

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="positioning-refresh")
_lock = RLock()
_futures: dict[str, Future[dict[str, object]]] = {}
_failures: dict[str, tuple[datetime, str]] = {}
_finra_futures: dict[str, Future[int]] = {}
_finra_failures: dict[str, tuple[datetime, str]] = {}
_finra_attempted_empty: set[str] = set()
RETRY_COOLDOWN = timedelta(minutes=15)


def positioning_is_fresh(snapshot: dict[str, object] | None) -> bool:
    if not snapshot or not snapshot.get("fetched_at"):
        return False
    try:
        return datetime.fromisoformat(str(snapshot["fetched_at"])).date() == datetime.now().date()
    except ValueError:
        return False


def _refresh(ticker: str, provider_factory: Callable[[], YahooPositioningProvider], db_path: str | Path | None) -> dict[str, object]:
    provider = provider_factory()
    payload = dict(provider.fetch(ticker))
    fetched_at = datetime.now().isoformat(timespec="seconds")
    reporting_date = str(payload.get("reporting_date") or "") or None
    payload["provider_name"] = provider.name
    payload["fetched_at"] = fetched_at
    payload.update(observed_at_fetch(fetched_at, period_end=reporting_date).as_dict())
    save_positioning_snapshot(ticker, payload, provider.name, reporting_date, fetched_at, db_path)
    return payload


def _finished(ticker: str, future: Future[dict[str, object]]) -> None:
    with _lock:
        try:
            future.result(); _failures.pop(ticker, None)
        except Exception as exc:
            _failures[ticker] = (datetime.now(), str(exc))
        _futures.pop(ticker, None)


def schedule_positioning_refresh(
    tickers: list[str], *, max_new: int = 1,
    provider_factory: Callable[[], YahooPositioningProvider] = YahooPositioningProvider,
    db_path: str | Path | None = None,
) -> list[str]:
    scheduled, now = [], datetime.now()
    with _lock:
        budget = min(max_new, max(0, 2 - len(_futures)))
        for raw in tickers:
            if len(scheduled) >= budget: break
            ticker = raw.strip().upper()
            if not ticker or ticker in _futures or positioning_is_fresh(get_cached_positioning(ticker, db_path)):
                continue
            failure = _failures.get(ticker)
            if failure and now - failure[0] < RETRY_COOLDOWN: continue
            future = _executor.submit(_refresh, ticker, provider_factory, db_path)
            _futures[ticker] = future
            future.add_done_callback(lambda completed, symbol=ticker: _finished(symbol, completed))
            scheduled.append(ticker)
    return scheduled


def positioning_refresh_status(ticker: str, db_path: str | Path | None = None) -> str:
    normalized = ticker.strip().upper()
    with _lock:
        if normalized in _futures: return "Updating"
        failure = _failures.get(normalized)
    cached = get_cached_positioning(normalized, db_path)
    if positioning_is_fresh(cached): return "Ready"
    if cached: return "Stale"
    if failure: return "Provider unavailable"
    return "Pending"


def has_finra_history(ticker: str, db_path: str | Path | None = None) -> bool:
    """Return whether official historical short-interest rows are persisted."""
    return any(
        row.get("snapshot_type") == "historical_short_interest"
        for row in get_positioning_history(ticker, db_path)
    )


def _finra_backfill(
    ticker: str, provider_factory: Callable[[], FINRAShortInterestProvider],
    db_path: str | Path | None,
) -> int:
    return backfill_finra_short_history(ticker, provider_factory(), db_path)


def _finra_finished(ticker: str, future: Future[int]) -> None:
    with _lock:
        try:
            count = future.result()
            _finra_failures.pop(ticker, None)
            if count == 0:
                _finra_attempted_empty.add(ticker)
            else:
                # Avoid a module-level cycle; recalculate only after FINRA rows are committed.
                from src.data.backtest_refresh import schedule_ticker_recalculation
                schedule_ticker_recalculation(ticker)
        except Exception as exc:
            _finra_failures[ticker] = (datetime.now(), str(exc))
        _finra_futures.pop(ticker, None)


def schedule_finra_backfill(
    tickers: list[str], *, max_new: int = 2,
    provider_factory: Callable[[], FINRAShortInterestProvider] = FINRAShortInterestProvider,
    db_path: str | Path | None = None,
) -> list[str]:
    """Backfill missing official FINRA history without blocking page rendering."""
    scheduled: list[str] = []
    now = datetime.now()
    with _lock:
        budget = min(max_new, max(0, 2 - len(_finra_futures)))
        for raw in tickers:
            if len(scheduled) >= budget:
                break
            ticker = raw.strip().upper()
            if (
                not ticker or ticker in _finra_futures or ticker in _finra_attempted_empty
                or has_finra_history(ticker, db_path)
            ):
                continue
            failure = _finra_failures.get(ticker)
            if failure and now - failure[0] < RETRY_COOLDOWN:
                continue
            future = _executor.submit(_finra_backfill, ticker, provider_factory, db_path)
            _finra_futures[ticker] = future
            future.add_done_callback(lambda completed, symbol=ticker: _finra_finished(symbol, completed))
            scheduled.append(ticker)
    return scheduled


def finra_backfill_status(ticker: str, db_path: str | Path | None = None) -> str:
    normalized = ticker.strip().upper()
    with _lock:
        if normalized in _finra_futures:
            return "Backfilling"
        if normalized in _finra_attempted_empty:
            return "No FINRA coverage"
        failure = _finra_failures.get(normalized)
    if has_finra_history(normalized, db_path):
        return "Ready"
    if failure:
        return "Provider unavailable"
    return "Pending"
