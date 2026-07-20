from src.data.database import get_cached_extended_hours_quote, init_db
from src.data.extended_hours import (
    effective_extended_quote, get_extended_hours_quote, overlay_extended_hours_prices,
)


class FakeProvider:
    provider_name = "mock extended"

    def __init__(self):
        self.calls = 0

    def fetch(self, ticker):
        self.calls += 1
        return {
            "ticker": ticker, "market_state": "after-hours", "active_session": "after-hours",
            "active_price": 102.0, "active_change_pct": 2.0,
            "active_timestamp": "2026-07-13T16:05:00-04:00", "regular_close": 100.0,
            "premarket_price": 99.0, "premarket_change_pct": -1.0,
            "premarket_timestamp": "2026-07-13T09:25:00-04:00",
            "afterhours_price": 102.0, "afterhours_change_pct": 2.0,
            "afterhours_timestamp": "2026-07-13T16:05:00-04:00",
        }


def test_extended_hours_quote_is_cached_in_sqlite(tmp_path):
    db = tmp_path / "quotes.db"
    init_db(db)
    provider = FakeProvider()
    first = get_extended_hours_quote("TEST", provider, db_path=db)
    second = get_extended_hours_quote("TEST", provider, db_path=db)
    assert provider.calls == 1
    assert first["active_price"] == second["active_price"] == 102.0
    assert second["provider_name"] == "mock extended"
    assert get_cached_extended_hours_quote("TEST", db)["quote_date"] == "2026-07-13"


def test_closed_gap_uses_last_after_hours_quote():
    effective = effective_extended_quote({
        "market_state": "closed", "active_session": "closed", "active_price": None,
        "afterhours_price": 920.8, "afterhours_change_pct": -1.73,
        "afterhours_timestamp": "2026-07-13T19:55:00-04:00",
    })

    assert effective == {
        "price": 920.8, "change_pct": -1.73,
        "timestamp": "2026-07-13T19:55:00-04:00",
        "label": "POST", "session": "after-hours close",
    }


def test_regular_session_does_not_override_regular_price():
    assert effective_extended_quote({
        "market_state": "regular", "active_session": "regular", "active_price": 101.0,
        "afterhours_price": 99.0,
    }) is None


def test_portfolio_prices_use_valid_extended_quotes_and_keep_regular_fallbacks():
    prices, applied = overlay_extended_hours_prices(
        {"PRE": 100.0, "POST": 200.0, "REG": 300.0, "BAD": 400.0},
        {
            "PRE": {
                "active_session": "pre-market", "active_price": 105.0,
                "active_timestamp": "2026-07-20T04:05:00-04:00",
            },
            "POST": {
                "active_session": "closed", "afterhours_price": 198.0,
                "afterhours_timestamp": "2026-07-17T19:55:00-04:00",
            },
            "REG": {"active_session": "regular", "active_price": 301.0},
            "BAD": {"active_session": "pre-market", "active_price": -1.0},
        },
    )

    assert prices == {"PRE": 105.0, "POST": 198.0, "REG": 300.0, "BAD": 400.0}
    assert applied["PRE"]["label"] == "PRE"
    assert applied["POST"]["label"] == "POST"
    assert set(applied) == {"PRE", "POST"}


def test_provider_failure_preserves_cached_extended_quote(tmp_path):
    db = tmp_path / "quotes.db"
    provider = FakeProvider()
    cached = get_extended_hours_quote("TEST", provider, db_path=db)

    class BrokenProvider:
        provider_name = "broken"

        def fetch(self, ticker):
            raise RuntimeError("provider unavailable")

    preserved = get_extended_hours_quote("TEST", BrokenProvider(), force_refresh=True, db_path=db)
    assert preserved["active_price"] == cached["active_price"]
    assert preserved["provider_name"] == "mock extended"
