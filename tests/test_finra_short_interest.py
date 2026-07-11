from src.data.database import get_cached_positioning, get_positioning_history
from src.data.finra_short_interest import backfill_finra_short_history


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
    assert get_cached_positioning("NVDA", database) is None
