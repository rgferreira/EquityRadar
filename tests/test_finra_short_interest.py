from src.data.database import get_cached_positioning, get_positioning_history
from src.data.finra_short_interest import backfill_finra_short_history
from src.data.positioning_refresh import _finra_backfill


def test_finra_backfill_adds_history_without_replacing_current_cache(tmp_path):
    class StubProvider:
        name = "FINRA stub"

        def fetch_history(self, ticker):
            return [{
                "ticker": ticker, "reporting_date": "2026-06-30",
                "short": {"shares_short": 100, "short_change_pct": 5, "days_to_cover": 2},
                "snapshot_type": "historical_short_interest",
            }]

    database = tmp_path / "radar.db"
    assert backfill_finra_short_history("NVDA", StubProvider(), database) == 1
    history = get_positioning_history("NVDA", database)
    assert history[0]["short"]["shares_short"] == 100
    assert history[0]["snapshot_type"] == "historical_short_interest"
    assert history[0]["period_end"] == "2026-06-30"
    assert history[0]["known_at_status"] == "verified_observed"
    assert history[0]["known_at"] == history[0]["fetched_at"]
    assert get_cached_positioning("NVDA", database) is None


def test_finra_backfill_does_not_rewrite_existing_historical_observation(tmp_path):
    class StubProvider:
        name = "FINRA stub"

        def __init__(self):
            self.shares = 100

        def fetch_history(self, ticker):
            return [{
                "ticker": ticker, "reporting_date": "2026-06-30",
                "short": {"shares_short": self.shares},
                "snapshot_type": "historical_short_interest",
            }]

    database = tmp_path / "radar.db"
    provider = StubProvider()
    backfill_finra_short_history("NVDA", provider, database)
    first = get_positioning_history("NVDA", database)[0]
    provider.shares = 999
    backfill_finra_short_history("NVDA", provider, database)

    assert get_positioning_history("NVDA", database)[0] == first


def test_daily_finra_refresh_distinguishes_new_reports_from_unchanged_history(tmp_path):
    class StubProvider:
        name = "FINRA stub"

        def fetch_history(self, ticker):
            return [{
                "ticker": ticker, "reporting_date": "2026-06-30",
                "short": {"shares_short": 100},
                "snapshot_type": "historical_short_interest",
            }]

    database = tmp_path / "radar.db"
    first = _finra_backfill("MU", StubProvider, database)
    second = _finra_backfill("MU", StubProvider, database)
    assert first == {"rows_fetched": 1, "new_reports": 1}
    assert second == {"rows_fetched": 1, "new_reports": 0}
