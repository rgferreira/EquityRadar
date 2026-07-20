"""Provider-neutral extended-hours quotes with a short SQLite cache."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol

import pandas as pd
import yfinance as yf

from src.data.database import get_cached_extended_hours_quote, save_extended_hours_quote


CACHE_TTL = timedelta(minutes=5)


class ExtendedHoursProvider(Protocol):
    provider_name: str

    def fetch(self, ticker: str) -> dict[str, object]: ...


def _change(price: float | None, base: float | None) -> float | None:
    return (price / base - 1) * 100 if price is not None and base not in (None, 0) else None


def _last_quote(frame: pd.DataFrame) -> tuple[float | None, str | None]:
    close = frame["Close"].dropna() if not frame.empty and "Close" in frame else pd.Series(dtype=float)
    return (float(close.iloc[-1]), str(close.index[-1])) if not close.empty else (None, None)


class YFinanceExtendedHoursProvider:
    provider_name = "yfinance extended hours"

    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))

    def fetch(self, ticker: str) -> dict[str, object]:
        normalized = ticker.strip().upper()
        instrument = yf.Ticker("BTC-USD" if normalized == "BTCUSD" else normalized)
        history = instrument.history(period="5d", interval="5m", prepost=True, timeout=8)
        if history.empty or "Close" not in history:
            raise ValueError("No intraday extended-hours data returned")
        if normalized.endswith("-USD") or normalized == "BTCUSD":
            price, timestamp = _last_quote(history)
            return {
                "ticker": normalized, "market_state": "24/7", "active_session": "24/7",
                "active_price": price, "active_change_pct": None, "active_timestamp": timestamp,
                "regular_close": None, "premarket_price": None, "premarket_change_pct": None,
                "premarket_timestamp": None, "afterhours_price": None,
                "afterhours_change_pct": None, "afterhours_timestamp": None,
            }

        periods = instrument.history_metadata.get("tradingPeriods")
        if not isinstance(periods, pd.DataFrame) or periods.empty:
            raise ValueError("Provider returned no exchange trading periods")
        period = periods.iloc[-1]
        pre_start = pd.Timestamp(period["pre_start"])
        regular_start = pd.Timestamp(period["start"])
        regular_end = pd.Timestamp(period["end"])
        post_end = pd.Timestamp(period["post_end"])
        index = pd.DatetimeIndex(history.index)
        pre = history[(index >= pre_start) & (index < regular_start)]
        regular = history[(index >= regular_start) & (index < regular_end)]
        post = history[(index >= regular_end) & (index <= post_end)]
        pre_price, pre_timestamp = _last_quote(pre)
        regular_close, regular_timestamp = _last_quote(regular)
        post_price, post_timestamp = _last_quote(post)

        previous_close = None
        if len(periods) > 1:
            previous = periods.iloc[-2]
            previous_start, previous_end = pd.Timestamp(previous["start"]), pd.Timestamp(previous["end"])
            previous_regular = history[(index >= previous_start) & (index < previous_end)]
            previous_close, _ = _last_quote(previous_regular)

        now = pd.Timestamp(self._now()).tz_convert(pre_start.tz)
        if pre_start <= now < regular_start:
            state, price, change, timestamp = "pre-market", pre_price, _change(pre_price, previous_close), pre_timestamp
        elif regular_start <= now < regular_end:
            state, price, change, timestamp = "regular", regular_close, _change(regular_close, previous_close), regular_timestamp
        elif regular_end <= now <= post_end:
            state, price, change, timestamp = "after-hours", post_price, _change(post_price, regular_close), post_timestamp
        else:
            state, price, change, timestamp = "closed", None, None, None
        return {
            "ticker": normalized, "market_state": state, "active_session": state,
            "active_price": price, "active_change_pct": change, "active_timestamp": timestamp,
            "regular_close": regular_close, "regular_timestamp": regular_timestamp,
            "previous_close": previous_close,
            "premarket_price": pre_price, "premarket_change_pct": _change(pre_price, previous_close),
            "premarket_timestamp": pre_timestamp,
            "afterhours_price": post_price, "afterhours_change_pct": _change(post_price, regular_close),
            "afterhours_timestamp": post_timestamp,
        }


def extended_quote_is_fresh(snapshot: dict[str, object] | None) -> bool:
    if not snapshot or not snapshot.get("fetched_at"):
        return False
    try:
        fetched = datetime.fromisoformat(str(snapshot["fetched_at"]))
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - fetched.astimezone(timezone.utc) < CACHE_TTL
    except (TypeError, ValueError):
        return False


def effective_extended_quote(snapshot: dict[str, object] | None) -> dict[str, object] | None:
    """Return the quote that should lead the UI outside the regular session.

    After the post-market session closes and before the next pre-market opens,
    the last post-market print remains the most recent traded value.
    """
    if not snapshot:
        return None
    session = str(snapshot.get("active_session") or snapshot.get("market_state") or "")
    if session in {"pre-market", "after-hours", "24/7"} and snapshot.get("active_price") is not None:
        label = "PRE" if session == "pre-market" else "POST" if session == "after-hours" else "24/7"
        return {
            "price": snapshot["active_price"],
            "change_pct": snapshot.get("active_change_pct"),
            "timestamp": snapshot.get("active_timestamp") or snapshot.get("fetched_at"),
            "label": label,
            "session": session,
        }
    if session == "closed" and snapshot.get("afterhours_price") is not None:
        return {
            "price": snapshot["afterhours_price"],
            "change_pct": snapshot.get("afterhours_change_pct"),
            "timestamp": snapshot.get("afterhours_timestamp") or snapshot.get("fetched_at"),
            "label": "POST",
            "session": "after-hours close",
        }
    return None


def overlay_extended_hours_prices(
    regular_prices: Mapping[str, float],
    snapshots: Mapping[str, dict[str, object] | None],
) -> tuple[dict[str, float], dict[str, dict[str, object]]]:
    """Overlay usable extended-hours prints on current regular-market prices.

    Invalid, missing, or regular-session snapshots never remove a known regular
    price. Returned metadata lets callers disclose which prices were replaced.
    """
    prices = {str(ticker): float(price) for ticker, price in regular_prices.items()}
    applied: dict[str, dict[str, object]] = {}
    for ticker in prices:
        effective = effective_extended_quote(snapshots.get(ticker))
        if not effective:
            continue
        try:
            extended_price = float(effective["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(extended_price) or extended_price <= 0:
            continue
        prices[ticker] = extended_price
        applied[ticker] = effective
    return prices, applied


def get_extended_hours_quote(
    ticker: str, provider: ExtendedHoursProvider | None = None, force_refresh: bool = False,
    db_path: str | Path | None = None,
) -> dict[str, object] | None:
    """Return a cached quote or retrieve one without affecting regular price data."""
    cached = get_cached_extended_hours_quote(ticker, db_path)
    if cached and not force_refresh and extended_quote_is_fresh(cached):
        return cached
    source = provider or YFinanceExtendedHoursProvider()
    try:
        payload = source.fetch(ticker)
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        quote_date = None
        for field in ("active_timestamp", "afterhours_timestamp", "premarket_timestamp", "regular_timestamp"):
            if payload.get(field):
                quote_date = str(pd.Timestamp(str(payload[field])).date())
                break
        save_extended_hours_quote(ticker, payload, source.provider_name, quote_date, fetched_at, db_path)
        return {**payload, "provider_name": source.provider_name, "quote_date": quote_date, "fetched_at": fetched_at}
    except Exception:
        return cached
