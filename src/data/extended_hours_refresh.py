"""Non-blocking extended-hours quote refresh orchestration."""

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from src.data.database import get_cached_extended_hours_quote
from src.data.extended_hours import extended_quote_is_fresh, get_extended_hours_quote


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="extended-hours")
_futures: dict[str, Future] = {}
_lock = Lock()


def _finished(ticker: str, _: Future) -> None:
    with _lock:
        _futures.pop(ticker, None)


def schedule_extended_hours_refresh(
    tickers: list[str], max_new: int = 2, db_path: str | Path | None = None,
) -> list[str]:
    """Refresh stale quotes in the background without blocking page rendering."""
    scheduled: list[str] = []
    with _lock:
        for ticker in tickers:
            normalized = ticker.strip().upper()
            if len(scheduled) >= max_new:
                break
            if normalized in _futures or extended_quote_is_fresh(get_cached_extended_hours_quote(normalized, db_path)):
                continue
            future = _executor.submit(get_extended_hours_quote, normalized, None, True, db_path)
            _futures[normalized] = future
            future.add_done_callback(lambda completed, symbol=normalized: _finished(symbol, completed))
            scheduled.append(normalized)
    return scheduled


def extended_hours_refresh_status(ticker: str, db_path: str | Path | None = None) -> str:
    normalized = ticker.strip().upper()
    with _lock:
        if normalized in _futures:
            return "Updating"
    snapshot = get_cached_extended_hours_quote(normalized, db_path)
    if extended_quote_is_fresh(snapshot):
        return "Ready"
    return "Stale" if snapshot else "Pending"
