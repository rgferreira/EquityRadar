from datetime import date, timedelta

import pandas as pd
import pytest

from src.data.congress_trading import CongressProviderBatch
from src.data.database import get_whale_backfill_states, get_whale_disclosures
from src.whaleseeker import (
    add_since_trade_returns,
    asset_display_name,
    clean_asset_description,
    disclosure_feed,
    empty_disclosure_message,
    normalize_trade_filter,
    politician_profiles,
    reported_ticker_quality,
    run_historical_backfill_step,
    run_latest_refresh,
    whale_dashboard_feed,
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


def test_latest_refresh_reads_page_zero_without_moving_backfill_cursors(tmp_path):
    database = tmp_path / "latest.db"
    provider = SequencedProvider([
        [row("h1", "House Person", "AAA")],
        [row("s1", "Senate Person", "BBB")],
    ])

    before = get_whale_backfill_states(provider.provider_key, database)
    result = run_latest_refresh(provider, db_path=database)
    after = get_whale_backfill_states(provider.provider_key, database)

    assert [item["status"] for item in result] == ["refreshed", "refreshed"]
    assert provider.calls == [("house", 0, 25), ("senate", 0, 25)]
    assert before == after
    assert len(get_whale_disclosures(db_path=database)) == 2


def test_feed_and_politician_profiles_expose_delay_without_inventing_returns():
    observations = [
        {
            "politician_name": "Ada Lovelace", "chamber": "house", "ticker": "AAA",
            "asset_description": "Example Corp (3)",
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
    assert feed[0]["Asset"] == "Example Corp"
    assert feed[0]["Ticker quality"] == "Reported"
    assert profiles[0]["Disclosures"] == 2
    assert profiles[0]["Median filing lag"] == 17.5
    assert profiles[0]["Copyable return"] == "Pending prospective outcome policy"


def test_instrument_display_cleans_provider_suffixes_without_merging_share_classes():
    assert clean_asset_description("  Alphabet   Inc (3) ") == "Alphabet Inc"
    assert clean_asset_description("Company 3M") == "Company 3M"
    assert asset_display_name("GOOGL", "Alphabet Inc (2)") == (
        "Alphabet Inc · Class A (voting)"
    )
    assert asset_display_name("GOOG", "Alphabet Inc") == (
        "Alphabet Inc · Class C (non-voting)"
    )
    assert asset_display_name("O", "Realty Income Corp") == "Realty Income Corp"
    assert reported_ticker_quality("O") == "Reported"
    assert reported_ticker_quality("BRK.B") == "Reported"
    assert reported_ticker_quality("BAD TICKER") == "Review format"


def test_dashboard_feed_filters_trade_type_before_limit_and_orders_by_trade_date():
    observations = [
        {
            "politician_name": "Recent Seller", "chamber": "house", "ticker": "AAA",
            "transaction_type": "sale", "trade_date": "2026-08-10",
            "filed_date": "2026-08-11", "known_at": "2026-08-12T12:00:00Z",
        },
        {
            "politician_name": "Older Buyer", "chamber": "senate", "ticker": "AAA",
            "transaction_type": "purchase", "trade_date": "2026-08-01",
            "filed_date": "2026-08-12", "known_at": "2026-08-12T12:00:00Z",
        },
        {
            "politician_name": "Recent Buyer", "chamber": "house", "ticker": "AAA",
            "transaction_type": "purchase", "trade_date": "2026-08-09",
            "filed_date": "2026-08-10", "known_at": "2026-08-12T12:00:00Z",
        },
    ]

    feed = disclosure_feed(
        observations, relevant_tickers={"AAA"}, transaction_types={"purchase"},
        order_by="trade", limit=2,
    )

    assert [row["Politician"] for row in feed] == ["Recent Buyer", "Older Buyer"]
    assert all(row["Trade"] == "Purchase" for row in feed)


def test_dashboard_feed_defaults_to_full_sample_and_can_restrict_to_dashboard_universe(monkeypatch):
    observations = [
        {
            "politician_name": "Buyer", "chamber": "house", "ticker": "OUTSIDE",
            "transaction_type": "purchase", "trade_date": "2026-08-10",
            "filed_date": "2026-08-11", "known_at": "2026-08-12T12:00:00Z",
        },
        {
            "politician_name": "Seller", "chamber": "senate", "ticker": "OWNED",
            "transaction_type": "sale", "trade_date": "2026-08-09",
            "filed_date": "2026-08-10", "known_at": "2026-08-12T12:00:00Z",
        },
    ]
    monkeypatch.setattr("src.whaleseeker.get_whale_disclosures", lambda **_: observations)

    global_purchases = whale_dashboard_feed(
        transaction_types=normalize_trade_filter("Purchase"),
    )
    universe_purchases = whale_dashboard_feed(
        ["OWNED"], transaction_types=normalize_trade_filter("Purchase"),
    )

    assert [row["Ticker"] for row in global_purchases] == ["OUTSIDE"]
    assert universe_purchases == []


def test_trade_filter_none_means_all_and_empty_messages_never_expose_none():
    assert normalize_trade_filter(None) is None
    assert normalize_trade_filter("All") is None
    assert normalize_trade_filter("Purchase") == {"purchase"}
    assert normalize_trade_filter("Sale") == {"sale"}
    assert empty_disclosure_message(None, restricted_to_universe=False) == (
        "No congressional disclosures are available in the local WhaleSeeker data."
    )
    assert empty_disclosure_message("Purchase", restricted_to_universe=True) == (
        "No purchase disclosures involve a security in the current Portfolio or Watchlist. "
        "Try All disclosures to see the full local sample."
    )


def test_since_trade_returns_fetch_each_ticker_once_and_preserve_feed_order():
    start = date.today() - timedelta(days=5)
    calls = []

    def fake_history(ticker, *, period):
        calls.append((ticker, period))
        return pd.DataFrame(
            {"Close": [100.0, 110.0]},
            index=pd.to_datetime([start.isoformat(), date.today().isoformat()]),
        )

    feed = [
        {"Ticker": "AAA", "Traded": start.isoformat(), "Politician": "First"},
        {"Ticker": "AAA", "Traded": start.isoformat(), "Politician": "Second"},
    ]

    enriched = add_since_trade_returns(feed, history_fetcher=fake_history)

    assert calls == [("AAA", "1y")]
    assert [row["Politician"] for row in enriched] == ["First", "Second"]
    assert [row["Since trade %"] for row in enriched] == pytest.approx([10.0, 10.0])
