from src.data.congress_trading import CongressProviderBatch
from src.data.database import get_whale_backfill_states, get_whale_disclosures
from src.whaleseeker import (
    disclosure_feed,
    politician_profiles,
    run_historical_backfill_step,
    whaleseeker_runtime_enabled,
)


def row(identifier, politician, ticker, *, transaction="Purchase", amount="$1,001 - $15,000"):
    return {
        "id": identifier,
        "politician": politician,
        "ticker": ticker,
        "assetDescription": f"{ticker} common stock",
        "type": transaction,
        "amount": amount,
        "transactionDate": "2026-07-01",
        "disclosureDate": "2026-07-21",
        "link": f"https://disclosures.example/{identifier}.pdf",
    }


class SequencedProvider:
    provider_key = "sequence_congress"

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def fetch(self, chamber, *, page=0, page_size=25):
        self.calls.append((chamber, page, page_size))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return CongressProviderBatch(
            provider_key=self.provider_key,
            endpoint=f"{chamber}-latest",
            request={"page": page, "limit": page_size},
            rows=result,
            fetched_at=f"2026-08-{page + 1:02d}T12:00:00Z",
        )


def test_bounded_backfill_advances_independent_cursors_and_marks_empty_complete(tmp_path):
    database = tmp_path / "backfill.db"
    provider = SequencedProvider([
        [row("h1", "House Person", "AAA")],
        [row("s1", "Senate Person", "BBB")],
        [],
        RuntimeError("temporary provider failure"),
        [],
    ])

    first = run_historical_backfill_step(provider, db_path=database)
    second = run_historical_backfill_step(provider, db_path=database)
    states = {item["chamber"]: item for item in get_whale_backfill_states(provider.provider_key, database)}

    assert [item["status"] for item in first] == ["imported", "imported"]
    assert states["house"]["status"] == "complete"
    assert states["house"]["next_page"] == 1
    assert states["senate"]["status"] == "failed"
    assert states["senate"]["next_page"] == 1
    assert second[1]["status"] == "failed"

    third = run_historical_backfill_step(provider, db_path=database)
    states = {item["chamber"]: item for item in get_whale_backfill_states(provider.provider_key, database)}
    assert third[0]["status"] == "complete"
    assert third[1]["status"] == "complete"
    assert states["senate"]["status"] == "complete"
    assert len(get_whale_disclosures(db_path=database)) == 2
    assert provider.calls == [
        ("house", 0, 25), ("senate", 0, 25),
        ("house", 1, 25), ("senate", 1, 25),
        ("senate", 1, 25),
    ]


def test_runtime_switch_prevents_provider_calls(tmp_path, monkeypatch):
    provider = SequencedProvider([])
    monkeypatch.setenv("WHALESEEKER_ENABLED", "false")

    result = run_historical_backfill_step(provider, db_path=tmp_path / "disabled.db")

    assert result == [{"status": "runtime_disabled", "provider_key": provider.provider_key}]
    assert provider.calls == []
    assert whaleseeker_runtime_enabled({"WHALESEEKER_ENABLED": "off"}) is False


def test_feed_and_politician_profiles_expose_delay_without_inventing_returns():
    observations = [
        {
            "politician_name": "Ada Lovelace", "chamber": "house", "ticker": "AAA",
            "transaction_type": "purchase", "amount_text": "$1,001 - $15,000",
            "trade_date": "2026-07-01", "filed_date": "2026-07-21",
            "known_at": "2026-08-01T12:00:00Z", "owner": "Spouse",
            "source_document_url": "https://disclosures.example/a.pdf",
        },
        {
            "politician_name": "Ada Lovelace", "chamber": "house", "ticker": "BBB",
            "transaction_type": "sale", "amount_text": "$15,001 - $50,000",
            "trade_date": "2026-07-10", "filed_date": "2026-07-25",
            "known_at": "2026-08-01T12:00:00Z", "owner": "Self",
            "source_document_url": "https://disclosures.example/b.pdf",
        },
    ]

    feed = disclosure_feed(observations, relevant_tickers={"AAA"})
    profiles = politician_profiles(observations)

    assert len(feed) == 1
    assert feed[0]["Filing lag (days)"] == 20
    assert feed[0]["App lag (days)"] == 11
    assert profiles[0]["Disclosures"] == 2
    assert profiles[0]["Median filing lag"] == 17.5
    assert profiles[0]["Copyable return"] == "Pending prospective outcome policy"
