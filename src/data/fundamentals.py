"""Provider-neutral fundamentals retrieval with a daily SQLite cache."""

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from src.data.database import get_cached_fundamentals, save_fundamentals
from src.data.temporal import observed_at_fetch


@dataclass
class Fundamentals:
    ticker: str
    trailing_pe: float | None = None
    forward_pe: float | None = None
    price_to_sales_ttm: float | None = None
    revenue_growth: float | None = None
    eps_growth: float | None = None
    reporting_date: str | None = None
    period_end: str | None = None
    published_at: str | None = None
    known_at: str | None = None
    known_at_status: str | None = None
    provider_name: str = "unknown"
    fetched_at: str | None = None


class FundamentalsProvider(Protocol):
    name: str

    def fetch(self, ticker: str, current_price: float | None = None) -> Fundamentals: ...


class FallbackFundamentalsProvider:
    """Try independent adapters in order and retain the provider that succeeds."""

    name = "Provider fallback chain"

    def __init__(self, providers: list[FundamentalsProvider]):
        self.providers = providers

    def fetch(self, ticker: str, current_price: float | None = None) -> Fundamentals:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return provider.fetch(ticker, current_price)
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
        raise RuntimeError("; ".join(errors) or "No fundamentals providers configured")


def get_fundamentals(
    ticker: str,
    provider: FundamentalsProvider | None,
    current_price: float | None = None,
    force_refresh: bool = False,
    db_path: str | Path | None = None,
) -> dict[str, object] | None:
    """Return today's cache unless explicitly refreshed; preserve stale cache on errors."""
    normalized = ticker.strip().upper()
    cached = get_cached_fundamentals(normalized, db_path)
    if cached and not force_refresh:
        fetched = datetime.fromisoformat(str(cached["fetched_at"]))
        if fetched.date() == datetime.now().date():
            return cached
    if provider is None:
        return cached
    try:
        result = provider.fetch(normalized, current_price)
        result.fetched_at = datetime.now().isoformat(timespec="seconds")
        result.period_end = result.period_end or result.reporting_date
        temporal = observed_at_fetch(
            result.fetched_at, period_end=result.period_end, published_at=result.published_at,
        )
        result.known_at = temporal.known_at
        result.known_at_status = temporal.known_at_status
        payload = asdict(result)
        save_fundamentals(payload, db_path)
        return payload
    except Exception:
        return cached
