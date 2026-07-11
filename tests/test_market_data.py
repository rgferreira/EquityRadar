import pandas as pd
import pytest
import time

from src.data.market_data import (
    calculate_metrics,
    clear_market_data_cache,
    fetch_price_history,
    get_price_history_fetched_at,
    fetch_quote_currency,
)


def test_calculate_metrics_uses_daily_close_prices():
    history = pd.DataFrame({"Close": range(1, 261)}, index=pd.date_range("2024-01-01", periods=260, freq="B"))
    metrics = calculate_metrics(history)
    assert metrics["latest_price"] == 260.0
    assert metrics["high_52w"] == 260.0
    assert metrics["low_52w"] == 1.0
    assert metrics["return_1m"] == pytest.approx((260 / 239 - 1) * 100)
    assert metrics["ma_200"] == pytest.approx(sum(range(61, 261)) / 200)
    assert metrics["drawdown_from_52w_high"] == 0.0


def test_fetch_price_history_uses_bounded_request(monkeypatch):
    calls = {}

    class FakeTicker:
        def history(self, **kwargs):
            calls.update(kwargs)
            return pd.DataFrame({"Close": [100.0]})

    monkeypatch.setattr("src.data.market_data.yf.Ticker", lambda ticker: FakeTicker())
    history = fetch_price_history("aapl", timeout=4)
    assert history["Close"].iloc[0] == 100.0
    assert calls == {
        "period": "1y", "interval": "1d", "auto_adjust": True,
        "timeout": 4, "raise_errors": True,
    }


def test_fetch_price_history_enforces_hard_timeout(monkeypatch):
    class SlowTicker:
        def history(self, **kwargs):
            time.sleep(0.1)
            return pd.DataFrame({"Close": [100.0]})

    monkeypatch.setattr("src.data.market_data.yf.Ticker", lambda ticker: SlowTicker())
    with pytest.raises(TimeoutError, match="timed out"):
        fetch_price_history("AAPL", timeout=0.01)


def test_three_year_history_and_freshness_are_tracked(monkeypatch):
    calls = {}

    class FakeTicker:
        def history(self, **kwargs):
            calls.update(kwargs)
            return pd.DataFrame({"Close": [100.0]})

    clear_market_data_cache()
    monkeypatch.setattr("src.data.market_data.yf.Ticker", lambda ticker: FakeTicker())
    fetch_price_history("msft", period="3y")
    assert calls["period"] == "3y"
    assert get_price_history_fetched_at("MSFT", "3y") is not None
    assert get_price_history_fetched_at("MSFT", "1y") is None


def test_unsupported_history_period_is_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        fetch_price_history("AAPL", period="5y")


def test_quote_currency_uses_yfinance_fast_info(monkeypatch):
    class FakeTicker:
        fast_info = {"currency": "eur"}

    fetch_quote_currency.cache_clear()
    monkeypatch.setattr("src.data.market_data.yf.Ticker", lambda ticker: FakeTicker())
    assert fetch_quote_currency("sap.de") == "EUR"
