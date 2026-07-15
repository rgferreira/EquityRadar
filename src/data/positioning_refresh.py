"""Non-blocking daily positioning refresh with stale-data preservation."""

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Callable

from src.data.database import (
    get_cached_positioning, get_positioning_history, get_provider_health_states, record_provider_health,
    save_positioning_snapshot,
)
from src.data.finra_short_interest import FINRAShortInterestProvider, backfill_finra_short_history
from src.data.positioning import YahooPositioningProvider
from src.data.temporal import observed_at_fetch
from src.scoring.positioning import effective_positioning_snapshot

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="positioning-refresh")
_lock = RLock()
_futures: dict[str, Future[dict[str, object]]] = {}
_failures: dict[str, tuple[datetime, str]] = {}
_finra_futures: dict[str, Future[dict[str, int]]] = {}
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


def _finished(ticker: str, future: Future[dict[str, object]], db_path: str | Path | None = None) -> None:
    with _lock:
        try:
            future.result(); _failures.pop(ticker, None)
            record_provider_health("positioning", ticker, "healthy", db_path=db_path)
        except Exception as exc:
            _failures[ticker] = (datetime.now(), str(exc))
            record_provider_health(
                "positioning", ticker, "failed", error=str(exc),
                cooldown_until=(datetime.now() + RETRY_COOLDOWN).isoformat(timespec="seconds"),
                db_path=db_path,
            )
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
            record_provider_health("positioning", ticker, "running", db_path=db_path)
            future.add_done_callback(lambda completed, symbol=ticker, path=db_path: _finished(symbol, completed, path))
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


def finra_refresh_due(
    ticker: str, db_path: str | Path | None = None, *, now: datetime | None = None,
) -> bool:
    """Refresh official history at most daily, even when earlier rows already exist."""
    normalized = ticker.strip().upper()
    current = now or datetime.now()
    state = next((
        row for row in get_provider_health_states(db_path)
        if row["provider_key"] == "finra" and row["ticker"] == normalized
    ), None)
    if not state or not state.get("last_attempt_at"):
        return True
    try:
        return datetime.fromisoformat(str(state["last_attempt_at"])).date() < current.date()
    except ValueError:
        return True


def _finra_backfill(
    ticker: str, provider_factory: Callable[[], FINRAShortInterestProvider],
    db_path: str | Path | None,
) -> dict[str, int]:
    before = {
        str(row.get("reporting_date")) for row in get_positioning_history(ticker, db_path)
        if row.get("snapshot_type") == "historical_short_interest" and row.get("reporting_date")
    }
    rows_fetched = backfill_finra_short_history(ticker, provider_factory(), db_path)
    after = {
        str(row.get("reporting_date")) for row in get_positioning_history(ticker, db_path)
        if row.get("snapshot_type") == "historical_short_interest" and row.get("reporting_date")
    }
    return {"rows_fetched": rows_fetched, "new_reports": len(after - before)}


def _finra_finished(
    ticker: str, future: Future[dict[str, int]], db_path: str | Path | None = None,
) -> None:
    with _lock:
        try:
            result = future.result()
            _finra_failures.pop(ticker, None)
            if result["rows_fetched"] == 0:
                _finra_attempted_empty.add(ticker)
                record_provider_health("finra", ticker, "failed", error="No FINRA coverage", db_path=db_path)
            else:
                record_provider_health("finra", ticker, "healthy", db_path=db_path)
                if result["new_reports"]:
                    # Avoid a module-level cycle; recalculate only after a new report is committed.
                    from src.data.backtest_refresh import schedule_ticker_recalculation
                    schedule_ticker_recalculation(ticker)
        except Exception as exc:
            _finra_failures[ticker] = (datetime.now(), str(exc))
            record_provider_health(
                "finra", ticker, "failed", error=str(exc),
                cooldown_until=(datetime.now() + RETRY_COOLDOWN).isoformat(timespec="seconds"),
                db_path=db_path,
            )
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
                not ticker or ticker in _finra_futures
                or not finra_refresh_due(ticker, db_path, now=now)
            ):
                continue
            failure = _finra_failures.get(ticker)
            if failure and now - failure[0] < RETRY_COOLDOWN:
                continue
            future = _executor.submit(_finra_backfill, ticker, provider_factory, db_path)
            _finra_attempted_empty.discard(ticker)
            _finra_futures[ticker] = future
            record_provider_health("finra", ticker, "running", db_path=db_path)
            future.add_done_callback(lambda completed, symbol=ticker, path=db_path: _finra_finished(symbol, completed, path))
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
    history = get_positioning_history(normalized, db_path)
    if has_finra_history(normalized, db_path):
        evidence = effective_positioning_snapshot(None, history)
        return "Ready" if evidence["scoring_eligible"] else "Stale"
    if failure:
        return "Provider unavailable"
    return "Pending"
