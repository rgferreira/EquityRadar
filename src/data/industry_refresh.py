"""Bounded background refresh orchestration for industry research snapshots."""

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Callable

from src.data.database import get_cached_industry_research, save_industry_research
from src.data.industry import YahooIndustryResearchProvider


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="industry-refresh")
_lock = RLock()
_futures: dict[str, Future[dict[str, object]]] = {}
_failures: dict[str, tuple[datetime, str]] = {}
RETRY_COOLDOWN = timedelta(minutes=15)


def snapshot_is_fresh(snapshot: dict[str, object] | None) -> bool:
    if not snapshot or not snapshot.get("fetched_at"):
        return False
    try:
        daily_fresh = datetime.fromisoformat(str(snapshot["fetched_at"])).date() == datetime.now().date()
        if snapshot.get("applicable") is not False and len(snapshot.get("peer_profiles", [])) < 3:
            retry_at = snapshot.get("next_peer_discovery_at")
            if not retry_at:
                return False  # Legacy limited snapshots get one immediate discovery attempt.
            if datetime.now() >= datetime.fromisoformat(str(retry_at)):
                return False
        return daily_fresh
    except ValueError:
        return False


def _refresh(
    ticker: str, provider_factory: Callable[[], YahooIndustryResearchProvider],
    db_path: str | Path | None,
) -> dict[str, object]:
    provider = provider_factory()
    cached = get_cached_industry_research(ticker, db_path)
    existing_peers: list[str] = []
    if cached and len(cached.get("peer_profiles", [])) >= 3:
        membership_at = cached.get("peer_membership_fetched_at")
        try:
            if membership_at and datetime.now() - datetime.fromisoformat(str(membership_at)) < timedelta(days=30):
                existing_peers = [str(value) for value in cached.get("peers", [])]
        except ValueError:
            pass
    if isinstance(provider, YahooIndustryResearchProvider):
        payload = provider.fetch(
            ticker, existing_peer_symbols=existing_peers or None, existing_snapshot=cached,
        )
    else:
        payload = provider.fetch(ticker)
    fetched_at = datetime.now().isoformat(timespec="seconds")
    payload["provider_name"] = provider.name
    payload["fetched_at"] = fetched_at
    save_industry_research(ticker, payload, provider.name, fetched_at, db_path)
    return payload


def _finished(ticker: str, future: Future[dict[str, object]]) -> None:
    with _lock:
        try:
            future.result()
            _failures.pop(ticker, None)
        except Exception as exc:
            _failures[ticker] = (datetime.now(), str(exc))
        _futures.pop(ticker, None)


def schedule_industry_refresh(
    tickers: list[str], *, max_new: int = 2,
    provider_factory: Callable[[], YahooIndustryResearchProvider] = YahooIndustryResearchProvider,
    db_path: str | Path | None = None,
) -> list[str]:
    """Schedule only missing/stale snapshots, respecting concurrency and cooldowns."""
    scheduled: list[str] = []
    now = datetime.now()
    with _lock:
        available_slots = max(0, 2 - len(_futures))
        budget = min(max_new, available_slots)
        for raw_ticker in tickers:
            if len(scheduled) >= budget:
                break
            ticker = raw_ticker.strip().upper()
            if not ticker or ticker in _futures:
                continue
            if snapshot_is_fresh(get_cached_industry_research(ticker, db_path)):
                continue
            failure = _failures.get(ticker)
            if failure and now - failure[0] < RETRY_COOLDOWN:
                continue
            future = _executor.submit(_refresh, ticker, provider_factory, db_path)
            _futures[ticker] = future
            future.add_done_callback(lambda completed, symbol=ticker: _finished(symbol, completed))
            scheduled.append(ticker)
    return scheduled


def industry_refresh_status(ticker: str, db_path: str | Path | None = None) -> str:
    normalized = ticker.strip().upper()
    with _lock:
        if normalized in _futures:
            snapshot = get_cached_industry_research(normalized, db_path)
            return "Discovering peers" if not snapshot or len(snapshot.get("peer_profiles", [])) < 3 else "Updating"
        failure = _failures.get(normalized)
    snapshot = get_cached_industry_research(normalized, db_path)
    if snapshot and snapshot.get("applicable") is not False and len(snapshot.get("peer_profiles", [])) < 3:
        try:
            if datetime.fromisoformat(str(snapshot.get("fetched_at"))).date() == datetime.now().date():
                return "Limited coverage"
        except (TypeError, ValueError):
            pass
    if snapshot_is_fresh(snapshot):
        if snapshot.get("applicable") is False:
            return "Not applicable"
        return "Limited coverage" if len(snapshot.get("peer_profiles", [])) < 3 else "Ready"
    if snapshot:
        return "Stale"
    if failure:
        return "Provider unavailable"
    return "Pending"


def refreshes_in_flight() -> bool:
    with _lock:
        return bool(_futures)
