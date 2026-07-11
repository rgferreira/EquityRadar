"""Non-blocking daily positioning refresh with stale-data preservation."""

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Callable

from src.data.database import get_cached_positioning, save_positioning_snapshot
from src.data.positioning import YahooPositioningProvider

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="positioning-refresh")
_lock = RLock()
_futures: dict[str, Future[dict[str, object]]] = {}
_failures: dict[str, tuple[datetime, str]] = {}
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
