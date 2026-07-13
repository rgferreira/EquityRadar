from src.data.database import get_cached_extended_hours_quote, init_db
from src.data.extended_hours import get_extended_hours_quote


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
