import pytest

from src.data.congress_trading import (
    CongressProviderBatch,
    FMPCongressTradingProvider,
    ingest_congress_page,
    normalize_congress_record,
    prepare_ingestion,
)
from src.data.database import (
    get_provider_health_states,
    get_registered_models,
    get_shadow_decision_snapshots,
    get_whale_disclosures,
    get_whale_raw_payloads,
    init_db,
)


HOUSE_ROW = {
    "id": "house-1",
    "firstName": "Ada",
    "lastName": "Lovelace",
    "district": "CA-00",
    "owner": "Spouse",
    "assetDescription": "Example Corporation Common Stock",
    "assetType": "Stock",
    "symbol": "exm",
    "type": "Purchase",
    "amount": "$1,001 - $15,000",
    "transactionDate": "2026-07-01",
    "disclosureDate": "2026-07-28",
    "link": "https://disclosures.example/house-1.pdf",
}


class FakeProvider:
    provider_key = "fake_congress"

    def __init__(self, batches):
        self.batches = list(batches)

    def fetch(self, chamber, *, page=0, page_size=25):
        result = self.batches.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def batch(row, *, chamber="house", fetched_at="2026-08-01T12:00:00+00:00"):
    return CongressProviderBatch(
        provider_key="fake_congress",
        endpoint=f"{chamber}-latest",
        request={"page": 0, "limit": 25},
        rows=[row],
        fetched_at=fetched_at,
    )


def test_house_record_normalizes_deterministically_with_conservative_known_at():
    raw, observations = prepare_ingestion(batch(HOUSE_ROW))
    repeated_raw, repeated_observations = prepare_ingestion(batch(HOUSE_ROW))
    observation = observations[0]

    assert raw == repeated_raw
    assert observations == repeated_observations
    assert observation["politician_name"] == "Ada Lovelace"
    assert observation["chamber"] == "house"
    assert observation["ticker"] == "EXM"
    assert observation["transaction_type"] == "purchase"
    assert observation["amount_min"] == 1001
    assert observation["amount_max"] == 15000
    assert observation["trade_date"] == "2026-07-01"
    assert observation["filed_date"] == "2026-07-28"
    assert observation["published_at"] is None
    assert observation["known_at"] == "2026-08-01T12:00:00+00:00"
    assert observation["known_at"] not in {observation["trade_date"], observation["filed_date"]}
    assert observation["raw_payload_id"] == raw["raw_payload_id"]


def test_senate_aliases_and_exact_publication_timestamp_are_preserved():
    record = {
        "Representative": "Grace Hopper",
        "Ticker": "NVDA",
        "Company": "NVIDIA Corporation",
        "Transaction": "Sale (Partial)",
        "Range": "Over $50,000",
        "Traded": "2026-07-02",
        "Filed": "2026-07-20",
        "publishedAt": "2026-07-20T14:32:00Z",
    }
    observation = normalize_congress_record(
        record, provider_key="quiver_test", chamber="senate",
        raw_payload_id="raw", fetched_at="2026-07-20T15:00:00Z",
    )

    assert observation["politician_name"] == "Grace Hopper"
    assert observation["chamber"] == "senate"
    assert observation["transaction_type"] == "sale"
    assert observation["amount_min"] == observation["amount_max"] == 50000
    assert observation["published_at"] == "2026-07-20T14:32:00Z"
    assert observation["known_at"] == "2026-07-20T15:00:00Z"


def test_ingestion_is_idempotent_and_does_not_touch_model_or_shadow_state(tmp_path):
    database = tmp_path / "whales.db"
    fixed = batch(HOUSE_ROW)
    provider = FakeProvider([fixed, fixed])
    init_db(database)
    models_before = get_registered_models(database)
    shadows_before = get_shadow_decision_snapshots(db_path=database)

    first = ingest_congress_page(provider, "house", db_path=database)
    second = ingest_congress_page(provider, "house", db_path=database)

    assert first["observations_inserted"] == 1
    assert second["observations_inserted"] == 0
    assert len(get_whale_raw_payloads(database)) == 1
    observations = get_whale_disclosures(db_path=database)
    assert len(observations) == 1
    assert observations[0]["revision_number"] == 1
    assert get_registered_models(database) == models_before
    assert get_shadow_decision_snapshots(db_path=database) == shadows_before


def test_changed_provider_content_appends_a_linked_revision(tmp_path):
    database = tmp_path / "whale-revisions.db"
    amended = {**HOUSE_ROW, "amount": "$15,001 - $50,000", "comment": "Amended"}
    provider = FakeProvider([
        batch(HOUSE_ROW, fetched_at="2026-08-01T12:00:00Z"),
        batch(amended, fetched_at="2026-08-02T12:00:00Z"),
    ])

    ingest_congress_page(provider, "house", db_path=database)
    result = ingest_congress_page(provider, "house", db_path=database)

    observations = sorted(
        get_whale_disclosures(db_path=database), key=lambda row: row["revision_number"],
    )
    assert result["revisions_inserted"] == 1
    assert [row["revision_number"] for row in observations] == [1, 2]
    assert observations[1]["supersedes_observation_id"] == observations[0]["observation_id"]
    assert observations[0]["amount_max"] == 15000
    assert observations[1]["amount_max"] == 50000
    latest = get_whale_disclosures(latest_only=True, db_path=database)
    assert len(latest) == 1 and latest[0]["revision_number"] == 2


def test_provider_failure_records_secret_safe_health_and_no_partial_payload(tmp_path):
    database = tmp_path / "whale-failure.db"
    provider = FakeProvider([RuntimeError("request contained apikey=super-secret")])

    with pytest.raises(RuntimeError, match="provider request failed") as error:
        ingest_congress_page(provider, "senate", db_path=database)

    assert "super-secret" not in str(error.value)
    assert get_whale_raw_payloads(database) == []
    assert get_whale_disclosures(db_path=database) == []
    health = next(
        row for row in get_provider_health_states(database)
        if row["provider_key"] == "fake_congress" and row["ticker"] == "SENATE"
    )
    assert health["status"] == "failed"
    assert "super-secret" not in health["last_error"]


def test_fmp_adapter_enforces_small_pages_and_keeps_credentials_out_of_batch_metadata():
    seen_urls = []
    provider = FMPCongressTradingProvider(
        "synthetic-key", requester=lambda url: seen_urls.append(url) or [HOUSE_ROW],
    )

    result = provider.fetch("house", page=2, page_size=25)

    assert result.endpoint == "house-latest"
    assert result.request == {"page": 2, "limit": 25}
    assert "apikey=synthetic-key" in seen_urls[0]
    assert "synthetic-key" not in str(result)
    with pytest.raises(ValueError, match="between 1 and 25"):
        provider.fetch("senate", page_size=50)


@pytest.mark.parametrize(
    "base_url",
    (
        "http://financialmodelingprep.com/stable",
        "file:///tmp/fmp",
        "https://user:password@financialmodelingprep.com/stable",
        "https://financialmodelingprep.com/stable?redirect=elsewhere",
    ),
)
def test_fmp_adapter_rejects_non_https_or_credential_bearing_base_urls(base_url):
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        FMPCongressTradingProvider("synthetic-key", base_url=base_url)


def test_fmp_adapter_sanitizes_requester_exceptions_before_they_escape():
    def fail_with_url(_url):
        raise RuntimeError("https://provider.invalid?apikey=synthetic-secret")

    provider = FMPCongressTradingProvider("synthetic-secret", requester=fail_with_url)

    with pytest.raises(RuntimeError, match="FMP congressional request failed") as error:
        provider.fetch("house")

    assert "synthetic-secret" not in str(error.value)


@pytest.mark.parametrize(
    "unsafe_url",
    (
        "javascript:alert(1)",
        "http://disclosures.example/insecure.pdf",
        "file:///tmp/disclosure.pdf",
        "https://user:password@disclosures.example/private.pdf",
    ),
)
def test_normalization_drops_untrusted_source_document_urls(unsafe_url):
    observation = normalize_congress_record(
        {**HOUSE_ROW, "link": unsafe_url}, provider_key="synthetic", chamber="house",
        raw_payload_id="raw", fetched_at="2026-08-11T12:00:00Z",
    )

    assert observation["source_document_url"] is None


def test_normalization_keeps_credential_free_https_source_document_urls():
    observation = normalize_congress_record(
        {**HOUSE_ROW, "link": "https://disclosures.example/report.pdf?id=123#page=2"},
        provider_key="synthetic", chamber="house", raw_payload_id="raw",
        fetched_at="2026-08-11T12:00:00Z",
    )

    assert observation["source_document_url"] == (
        "https://disclosures.example/report.pdf?id=123#page=2"
    )
