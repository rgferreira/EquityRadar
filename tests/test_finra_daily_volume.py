from datetime import date, datetime

from src.data.database import (
    get_finra_daily_short_volume, get_finra_daily_short_volume_fetches,
    save_finra_daily_short_volume_file,
)
from src.data.finra_daily_volume import (
    DailyShortVolumeFileUnavailable, FINRADailyShortVolumeProvider,
    backfill_finra_daily_short_volume,
)


class FakeResponse:
    def __init__(self, content: str):
        self.content = content.encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.content


def test_finra_daily_adapter_filters_and_parses_consolidated_file():
    content = (
        "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
        "20260714|MU|120.5|2|300|B,Q,N\n"
        "20260714|NVDA|90|0|200|Q\n"
    )
    provider = FINRADailyShortVolumeProvider(lambda *_args, **_kwargs: FakeResponse(content))

    rows, source_url = provider.fetch_date(date(2026, 7, 14), ["MU"])

    assert source_url.endswith("CNMSshvol20260714.txt")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "MU"
    assert rows[0]["short_volume"] == 120.5
    assert rows[0]["total_volume"] == 300
    assert len(str(rows[0]["payload_hash"])) == 64


def test_finra_daily_persistence_is_immutable_and_returns_latest_version(tmp_path):
    database = tmp_path / "daily-volume.db"
    original = [{
        "ticker": "MU", "short_volume": 100, "short_exempt_volume": 0,
        "total_volume": 250, "market": "Q", "payload_hash": "original",
    }]
    revised = [{**original[0], "short_volume": 120, "payload_hash": "revised"}]

    assert save_finra_daily_short_volume_file(
        "2026-07-14", original, "stub", "https://example/one", "2026-07-14T22:00:00",
        db_path=database,
    ) == 1
    assert save_finra_daily_short_volume_file(
        "2026-07-14", original, "stub", "https://example/one", "2026-07-14T23:00:00",
        db_path=database,
    ) == 0
    assert save_finra_daily_short_volume_file(
        "2026-07-14", revised, "stub", "https://example/two", "2026-07-15T09:00:00",
        db_path=database,
    ) == 1

    latest = get_finra_daily_short_volume("MU", database)
    assert len(latest) == 1
    assert latest[0]["short_volume"] == 120
    assert latest[0]["known_at"] == "2026-07-15T09:00:00"
    assert latest[0]["known_at_status"] == "verified_observed"


def test_finra_daily_backfill_records_unavailable_days_without_fabricating_rows(tmp_path):
    database = tmp_path / "daily-backfill.db"

    class StubProvider:
        name = "daily stub"

        def fetch_date(self, trade_date, tickers):
            source_url = f"https://example/{trade_date}.txt"
            if trade_date == date(2026, 7, 3):
                raise DailyShortVolumeFileUnavailable(source_url)
            return ([{
                "ticker": tickers[0], "short_volume": 40, "short_exempt_volume": 0,
                "total_volume": 100, "market": "Q", "payload_hash": trade_date.isoformat(),
            }], source_url)

    result = backfill_finra_daily_short_volume(
        ["MU"], StubProvider(), database, lookback_days=4,
        now=datetime(2026, 7, 6, 12, 0),
    )

    assert result["files_fetched"] == 2
    assert result["unavailable"] == 1
    assert len(get_finra_daily_short_volume("MU", database)) == 2
    fetches = get_finra_daily_short_volume_fetches(database)
    assert {row["status"] for row in fetches} == {"fetched", "unavailable"}
