"""Provider-neutral, point-in-time-safe congressional trading ingestion."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

from src.data.database import init_db, record_provider_health, save_whale_ingestion


MAX_FMP_PAGE_SIZE = 25
MAX_FMP_RESPONSE_BYTES = 2 * 1024 * 1024
SUPPORTED_CHAMBERS = {"house", "senate"}


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()


def _observed_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validated_https_url(value: object, *, allow_path_only: bool = False) -> str | None:
    """Return a credential-free HTTPS URL or None for untrusted provider text."""
    candidate = str(value or "").strip()
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or (not allow_path_only and (parsed.query or parsed.fragment))
    ):
        return None
    return candidate


@dataclass(frozen=True)
class CongressProviderBatch:
    provider_key: str
    endpoint: str
    request: Mapping[str, object]
    rows: Sequence[Mapping[str, object]]
    fetched_at: str


class CongressTradingProvider(Protocol):
    provider_key: str

    def fetch(self, chamber: str, *, page: int = 0, page_size: int = 25) -> CongressProviderBatch:
        """Fetch one provider page without persisting it."""


class FMPCongressTradingProvider:
    """Conservative adapter for FMP's stable House and Senate endpoints."""

    provider_key = "fmp_congress"

    def __init__(
        self, api_key: str, *, base_url: str = "https://financialmodelingprep.com/stable",
        requester: Callable[[str], object] | None = None,
    ):
        if not api_key:
            raise ValueError("FMP_API_KEY is not configured")
        validated_base_url = _validated_https_url(base_url)
        if validated_base_url is None:
            raise ValueError("FMP base URL must be credential-free HTTPS without query or fragment")
        self.api_key = api_key
        self.base_url = validated_base_url.rstrip("/")
        self.requester = requester

    def fetch(self, chamber: str, *, page: int = 0, page_size: int = 25) -> CongressProviderBatch:
        normalized_chamber = chamber.strip().lower()
        if normalized_chamber not in SUPPORTED_CHAMBERS:
            raise ValueError(f"Unsupported congressional chamber: {chamber}")
        if page < 0:
            raise ValueError("page must be zero or greater")
        if not 1 <= page_size <= MAX_FMP_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {MAX_FMP_PAGE_SIZE}")
        endpoint = f"{normalized_chamber}-latest"
        request = {"page": page, "limit": page_size}
        query = urlencode({**request, "apikey": self.api_key})
        url = f"{self.base_url}/{endpoint}?{query}"
        try:
            if self.requester is None:
                # The complete request URL is constructed from the HTTPS-validated base above.
                with urlopen(url, timeout=10) as response:  # nosec B310
                    if _validated_https_url(response.geturl(), allow_path_only=True) is None:
                        raise RuntimeError("FMP congressional redirect was not HTTPS")
                    body = response.read(MAX_FMP_RESPONSE_BYTES + 1)
                    if len(body) > MAX_FMP_RESPONSE_BYTES:
                        raise RuntimeError("FMP congressional response exceeded the safety limit")
                    payload = json.loads(body)
            else:
                payload = self.requester(url)
        except Exception:
            # urllib errors may include the complete URL, including the API key.
            raise RuntimeError("FMP congressional request failed") from None
        if isinstance(payload, Mapping) and payload.get("Error Message"):
            raise RuntimeError("FMP congressional endpoint returned an error")
        if not isinstance(payload, list):
            raise RuntimeError("FMP congressional endpoint returned an invalid payload")
        return CongressProviderBatch(
            provider_key=self.provider_key,
            endpoint=endpoint,
            request=request,
            rows=[dict(row) for row in payload if isinstance(row, Mapping)],
            fetched_at=_observed_now(),
        )


def _text(record: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _date_value(record: Mapping[str, object], *keys: str) -> str | None:
    value = _text(record, *keys)
    if not value:
        return None
    return value[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", value) else value


def _published_timestamp(record: Mapping[str, object]) -> str | None:
    value = _text(record, "publishedAt", "published_at", "publicationTimestamp")
    if value and ("T" in value or len(value) > 10):
        return value
    return None


def _politician_name(record: Mapping[str, object]) -> str:
    direct = _text(record, "politician", "representative", "name", "Representative")
    if direct:
        return direct
    parts = [
        _text(record, "firstName", "first_name"),
        _text(record, "lastName", "last_name"),
    ]
    return " ".join(part for part in parts if part) or "Unknown politician"


def _transaction_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if "purchase" in normalized or normalized in {"buy", "bought"}:
        return "purchase"
    if "sale" in normalized or normalized in {"sell", "sold"}:
        return "sale"
    if "exchange" in normalized:
        return "exchange"
    return "other"


def _amount_range(value: str | None) -> tuple[float | None, float | None]:
    if not value:
        return None, None
    numbers = [float(item.replace(",", "")) for item in re.findall(r"\d[\d,]*(?:\.\d+)?", value)]
    if not numbers:
        return None, None
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return min(numbers[0], numbers[1]), max(numbers[0], numbers[1])


def normalize_congress_record(
    record: Mapping[str, object], *, provider_key: str, chamber: str,
    raw_payload_id: str, fetched_at: str,
) -> dict[str, object]:
    """Normalize one disclosure while keeping filing and availability semantics separate."""
    normalized_chamber = chamber.strip().lower()
    if normalized_chamber not in SUPPORTED_CHAMBERS:
        normalized_chamber = "unknown"
    politician = _politician_name(record)
    ticker_value = _text(record, "symbol", "ticker", "Ticker")
    ticker = ticker_value.upper() if ticker_value and ticker_value not in {"-", "--", "N/A"} else None
    asset_description = _text(
        record, "assetDescription", "asset_description", "description", "Company",
    ) or ticker or "Unknown asset"
    transaction = _transaction_type(_text(record, "type", "transactionType", "Transaction"))
    amount_text = _text(record, "amount", "range", "Range")
    amount_min, amount_max = _amount_range(amount_text)
    trade_date = _date_value(record, "transactionDate", "transaction_date", "Traded")
    filed_date = _date_value(
        record, "disclosureDate", "reportDate", "filingDate", "ReportDate", "Filed",
    )
    source_document_url = _validated_https_url(
        _text(record, "link", "source", "sourceUrl", "officialLink"),
        allow_path_only=True,
    )
    provider_record_id = _text(record, "id", "transactionId", "providerRecordId")
    owner = _text(record, "owner", "Owner")
    source_json = _canonical_json(dict(record))
    source_hash = hashlib.sha256(source_json.encode()).hexdigest()
    canonical_trade_id = _hash(
        provider_key,
        provider_record_id or source_document_url or "no-provider-id",
        politician.lower(),
        normalized_chamber,
        ticker or "",
        asset_description.lower(),
        trade_date or "",
        transaction,
        (owner or "").lower(),
    )
    return {
        "observation_id": _hash(provider_key, canonical_trade_id, source_hash),
        "canonical_trade_id": canonical_trade_id,
        "provider_key": provider_key,
        "provider_record_id": provider_record_id,
        "raw_payload_id": raw_payload_id,
        "politician_name": politician,
        "chamber": normalized_chamber,
        "district": _text(record, "district", "District", "office"),
        "party": _text(record, "party", "Party"),
        "owner": owner,
        "ticker": ticker,
        "asset_description": asset_description,
        "asset_type": _text(record, "assetType", "asset_type", "TickerType"),
        "transaction_type": transaction,
        "amount_text": amount_text,
        "amount_min": amount_min,
        "amount_max": amount_max,
        "trade_date": trade_date,
        "filed_date": filed_date,
        "published_at": _published_timestamp(record),
        "known_at": fetched_at,
        "known_at_status": "observed_by_app",
        "source_document_url": source_document_url,
        "source_hash": source_hash,
        "fetched_at": fetched_at,
    }


def prepare_ingestion(batch: CongressProviderBatch) -> tuple[dict[str, object], list[dict[str, object]]]:
    payload_json = _canonical_json(list(batch.rows))
    payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()
    raw_payload_id = _hash(batch.provider_key, batch.endpoint, batch.fetched_at, payload_hash)
    raw_payload = {
        "raw_payload_id": raw_payload_id,
        "provider_key": batch.provider_key,
        "endpoint": batch.endpoint,
        "request_json": _canonical_json(dict(batch.request)),
        "payload_json": payload_json,
        "payload_hash": payload_hash,
        "fetched_at": batch.fetched_at,
    }
    chamber = batch.endpoint.split("-", 1)[0]
    observations = [
        normalize_congress_record(
            row,
            provider_key=batch.provider_key,
            chamber=chamber,
            raw_payload_id=raw_payload_id,
            fetched_at=batch.fetched_at,
        )
        for row in batch.rows
    ]
    return raw_payload, observations


def _safe_error(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    return f"{type(exc).__name__}: provider request failed" + (f" ({code})" if code else "")


def ingest_congress_page(
    provider: CongressTradingProvider, chamber: str, *, page: int = 0, page_size: int = 25,
    db_path: str | Path | None = None,
) -> dict[str, object]:
    """Fetch and atomically persist a page while recording secret-safe provider health."""
    normalized_chamber = chamber.strip().lower()
    health_ticker = normalized_chamber.upper() or "*"
    init_db(db_path)
    record_provider_health(provider.provider_key, health_ticker, "running", db_path=db_path)
    try:
        batch = provider.fetch(normalized_chamber, page=page, page_size=page_size)
        raw_payload, observations = prepare_ingestion(batch)
        result = save_whale_ingestion(raw_payload, observations, db_path)
    except Exception as exc:
        safe_error = _safe_error(exc)
        record_provider_health(
            provider.provider_key, health_ticker, "failed",
            error=safe_error, db_path=db_path,
        )
        raise RuntimeError(safe_error) from None
    record_provider_health(provider.provider_key, health_ticker, "healthy", db_path=db_path)
    return {
        **result,
        "provider_key": batch.provider_key,
        "endpoint": batch.endpoint,
        "rows_received": len(batch.rows),
        "fetched_at": batch.fetched_at,
    }
