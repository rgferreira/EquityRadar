"""Market-data retrieval and daily-price metrics."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from functools import lru_cache

import pandas as pd
import yfinance as yf

DEFAULT_REQUEST_TIMEOUT_SECONDS = 8
SUPPORTED_PERIODS = {"1y", "3y", "max"}
_price_history_fetched_at: dict[tuple[str, str], str] = {}


@lru_cache(maxsize=100)
def _fetch_price_history_cached(ticker: str, period: str, timeout: int) -> pd.DataFrame:
    """Fetch and cache a provider response for the lifetime of the app process."""

    def download() -> pd.DataFrame:
        return yf.Ticker(ticker).history(
            period=period,
            interval="1d",
            auto_adjust=True,
            timeout=timeout,
            raise_errors=True,
        )

    # yfinance's HTTP timeout does not protect against every provider-side stall.
    # Do not let one ticker prevent Streamlit from rendering an error message.
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(download)
    try:
        history = future.result(timeout=timeout)
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError(f"Market-data request timed out after {timeout} seconds") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    if history.empty or "Close" not in history:
        raise ValueError("No daily price data returned")
    _price_history_fetched_at[(ticker, period)] = datetime.now().isoformat(timespec="seconds")
    return history.dropna(subset=["Close"])


def fetch_price_history(
    ticker: str, timeout: int = DEFAULT_REQUEST_TIMEOUT_SECONDS, period: str = "1y"
) -> pd.DataFrame:
    """Fetch daily prices for a supported range, reusing cached responses."""
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        raise ValueError("Ticker cannot be empty")
    if period not in SUPPORTED_PERIODS:
        raise ValueError(f"Unsupported price-history period: {period}")
    return _fetch_price_history_cached(normalized_ticker, period, timeout).copy()


def get_price_history_fetched_at(ticker: str, period: str = "1y") -> str | None:
    """Return when this process last fetched a ticker/range from yfinance."""
    return _price_history_fetched_at.get((ticker.strip().upper(), period))


@lru_cache(maxsize=100)
def fetch_quote_currency(ticker: str) -> str | None:
    """Return the provider-reported trading currency, if available."""
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("Ticker cannot be empty")
    try:
        currency = yf.Ticker(normalized).fast_info.get("currency")
        return str(currency).upper() if currency else None
    except Exception:
        return None


@lru_cache(maxsize=100)
def fetch_fx_rate(from_currency: str, to_currency: str) -> float | None:
    """Fetch the latest yfinance FX conversion rate between two ISO currencies."""
    source, target = from_currency.strip().upper(), to_currency.strip().upper()
    if source == target:
        return 1.0
    direct = fetch_price_history(f"{source}{target}=X", period="1y")
    close = direct["Close"].dropna()
    return float(close.iloc[-1]) if not close.empty else None


@lru_cache(maxsize=100)
def fetch_asset_profile(ticker: str) -> dict[str, str | None]:
    """Return lightweight allocation metadata when yfinance exposes it."""
    try:
        info = yf.Ticker(ticker.strip().upper()).info
        return {"sector": info.get("sector"), "country": info.get("country")}
    except Exception:
        return {"sector": None, "country": None}


def clear_market_data_cache() -> None:
    """Force the next market-data call to request a new provider response."""
    _fetch_price_history_cached.cache_clear()
    _price_history_fetched_at.clear()
    fetch_quote_currency.cache_clear()
    fetch_fx_rate.cache_clear()
    fetch_asset_profile.cache_clear()


def _return_over_days(close: pd.Series, trading_days: int) -> float | None:
    if len(close) <= trading_days:
        return None
    return (float(close.iloc[-1]) / float(close.iloc[-(trading_days + 1)]) - 1) * 100


def calculate_metrics(history: pd.DataFrame) -> dict[str, float | None]:
    """Calculate dashboard metrics from a daily history DataFrame."""
    if history.empty or "Close" not in history:
        raise ValueError("History must contain at least one Close price")
    close = history["Close"].dropna()
    if close.empty:
        raise ValueError("History contains no valid Close prices")
    latest = float(close.iloc[-1])
    high_52w, low_52w = float(close.max()), float(close.min())
    return {
        "latest_price": latest,
        "return_1m": _return_over_days(close, 21),
        "return_3m": _return_over_days(close, 63),
        "return_6m": _return_over_days(close, 126),
        "return_12m": _return_over_days(close, 252),
        "high_52w": high_52w,
        "low_52w": low_52w,
        "drawdown_from_52w_high": (latest / high_52w - 1) * 100,
        "ma_50": float(close.tail(50).mean()) if len(close) >= 50 else None,
        "ma_100": float(close.tail(100).mean()) if len(close) >= 100 else None,
        "ma_200": float(close.tail(200).mean()) if len(close) >= 200 else None,
    }
