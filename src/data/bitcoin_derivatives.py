"""Venue-specific, display-only Bitcoin perpetual-futures observations."""

from __future__ import annotations

import hashlib
import json
import math
import csv
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from io import BytesIO, TextIOWrapper
from pathlib import Path
from threading import RLock
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from src.data.database import (
    get_bitcoin_derivatives_daily_observations,
    record_provider_health,
    save_bitcoin_derivatives_daily_observations,
)


VENUE = "Binance USD-M Futures"
INSTRUMENT = "BTCUSDT perpetual"
PROVIDER_KEY = "bitcoin_derivatives_binance"
HEALTH_TICKER = "BTC-USD"
SOURCE_ENDPOINTS = (
    "/futures/data/takerlongshortRatio",
    "/futures/data/globalLongShortAccountRatio",
    "/futures/data/openInterestHist",
)
MAX_RESPONSE_BYTES = 2_000_000
MAX_ARCHIVE_BYTES = 4_000_000
MAX_ARCHIVE_CSV_BYTES = 12_000_000
TARGET_HISTORY_DAYS = 365
MIN_READY_OBSERVATIONS = 350
MIN_READY_SPAN_DAYS = 364
RETRY_COOLDOWN = timedelta(minutes=15)


class BitcoinDerivativesProvider(Protocol):
    name: str

    def fetch_daily(
        self, *, limit: int = 30, fetched_at: datetime | None = None,
    ) -> list[dict[str, object]]: ...


def _utc_period_date(timestamp_ms: object, *, end_timestamp: bool) -> str:
    timestamp = int(timestamp_ms)
    if end_timestamp:
        timestamp -= 1
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date().isoformat()


def _nonnegative_float(value: object, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field}") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"Invalid {field}")
    return parsed


class BinanceBitcoinDerivativesProvider:
    """Public Binance BTCUSDT perpetual daily flow and positioning adapter."""

    name = "Binance USD-M Futures public market data"
    base_url = "https://fapi.binance.com"

    def __init__(self, requester: Callable[[str], object] | None = None) -> None:
        self._requester = requester or self._request_json

    @staticmethod
    def _request_json(url: str) -> object:
        request = Request(url, headers={"User-Agent": "PersonalEquityRadar/1.0"})
        try:
            with urlopen(request, timeout=20) as response:
                final_url = urlparse(response.geturl())
                if final_url.scheme != "https" or final_url.hostname != "fapi.binance.com":
                    raise RuntimeError("Binance BTC derivatives redirect was rejected")
                content = response.read(MAX_RESPONSE_BYTES + 1)
        except Exception as exc:
            raise RuntimeError("Binance BTC derivatives request failed") from exc
        if len(content) > MAX_RESPONSE_BYTES:
            raise RuntimeError("Binance BTC derivatives response exceeded the safety limit")
        try:
            return json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Binance BTC derivatives response was invalid") from exc

    def _fetch(self, endpoint: str, limit: int) -> list[Mapping[str, object]]:
        query = urlencode({"symbol": "BTCUSDT", "period": "1d", "limit": limit})
        try:
            payload = self._requester(f"{self.base_url}{endpoint}?{query}")
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("Binance BTC derivatives request failed") from exc
        if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
            raise RuntimeError("Binance BTC derivatives response was invalid")
        return payload

    def fetch_daily(
        self, *, limit: int = 30, fetched_at: datetime | None = None,
    ) -> list[dict[str, object]]:
        if not 1 <= limit <= 30:
            raise ValueError("Binance daily derivatives limit must be between 1 and 30")
        observed_at = fetched_at or datetime.now(timezone.utc)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        observed_iso = observed_at.astimezone(timezone.utc).isoformat(timespec="seconds")

        taker = {
            _utc_period_date(item.get("timestamp"), end_timestamp=False): item
            for item in self._fetch(SOURCE_ENDPOINTS[0], limit)
        }
        accounts = {
            _utc_period_date(item.get("timestamp"), end_timestamp=True): item
            for item in self._fetch(SOURCE_ENDPOINTS[1], limit)
        }
        open_interest = {
            _utc_period_date(item.get("timestamp"), end_timestamp=True): item
            for item in self._fetch(SOURCE_ENDPOINTS[2], limit)
        }
        common_dates = sorted(set(taker) & set(accounts) & set(open_interest))
        rows: list[dict[str, object]] = []
        for period_date in common_dates:
            raw = {
                "taker_buy_sell_volume": dict(taker[period_date]),
                "global_long_short_accounts": dict(accounts[period_date]),
                "open_interest": dict(open_interest[period_date]),
            }
            long_pct = _nonnegative_float(accounts[period_date].get("longAccount"), "long account share") * 100
            short_pct = _nonnegative_float(accounts[period_date].get("shortAccount"), "short account share") * 100
            if long_pct > 100 or short_pct > 100 or abs((long_pct + short_pct) - 100) > 0.2:
                raise RuntimeError("Binance BTC derivatives account shares were invalid")
            payload_hash = hashlib.sha256(
                json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            rows.append({
                "venue": VENUE,
                "instrument": INSTRUMENT,
                "period_date": period_date,
                "taker_buy_volume": _nonnegative_float(taker[period_date].get("buyVol"), "taker buy volume"),
                "taker_sell_volume": _nonnegative_float(taker[period_date].get("sellVol"), "taker sell volume"),
                "long_account_pct": long_pct,
                "short_account_pct": short_pct,
                "open_interest_value_quote": _nonnegative_float(
                    open_interest[period_date].get("sumOpenInterestValue"), "open interest value",
                ),
                "quote_currency": "USDT",
                "provider_name": self.name,
                "source_endpoints": list(SOURCE_ENDPOINTS),
                "payload": raw,
                "payload_hash": payload_hash,
                "fetched_at": observed_iso,
            })
        if not rows:
            raise RuntimeError("Binance BTC derivatives responses had no aligned daily observations")
        return rows


class BinanceBitcoinDerivativesArchiveProvider:
    """One-year BTCUSDT history from Binance's public USD-M archive."""

    name = "Binance USD-M Futures public data archive"
    archive_base_url = "https://data.binance.vision"
    api_base_url = "https://fapi.binance.com"

    def __init__(
        self, *, archive_requester: Callable[[str], bytes | None] | None = None,
        json_requester: Callable[[str], object] | None = None, max_workers: int = 8,
    ) -> None:
        self._archive_requester = archive_requester or self._download_archive
        self._json_requester = json_requester or BinanceBitcoinDerivativesProvider._request_json
        self._max_workers = max(1, min(12, int(max_workers)))

    @staticmethod
    def _download_archive(url: str) -> bytes | None:
        request = Request(url, headers={"User-Agent": "PersonalEquityRadar/1.0"})
        try:
            with urlopen(request, timeout=20) as response:
                final_url = urlparse(response.geturl())
                if final_url.scheme != "https" or final_url.hostname != "data.binance.vision":
                    raise RuntimeError("Binance public-data redirect was rejected")
                content = response.read(MAX_ARCHIVE_BYTES + 1)
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise RuntimeError("Binance public-data archive request failed") from None
        except Exception:
            raise RuntimeError("Binance public-data archive request failed") from None
        if len(content) > MAX_ARCHIVE_BYTES:
            raise RuntimeError("Binance public-data archive exceeded the safety limit")
        return content

    def _metrics_for_date(self, period_date: date) -> Mapping[str, object] | None:
        filename = f"BTCUSDT-metrics-{period_date.isoformat()}.zip"
        url = (
            f"{self.archive_base_url}/data/futures/um/daily/metrics/BTCUSDT/{filename}"
        )
        content = self._archive_requester(url)
        if content is None:
            return None
        try:
            with ZipFile(BytesIO(content)) as archive:
                members = archive.infolist()
                if (
                    len(members) != 1 or not members[0].filename.endswith(".csv")
                    or members[0].file_size > MAX_ARCHIVE_CSV_BYTES
                    or archive.testzip() is not None
                ):
                    raise RuntimeError("Binance metrics archive failed integrity validation")
                with archive.open(members[0]) as raw:
                    rows = list(csv.DictReader(TextIOWrapper(raw, encoding="utf-8-sig", newline="")))
        except (BadZipFile, OSError, RuntimeError) as exc:
            raise RuntimeError("Binance metrics archive was invalid") from exc
        valid = [
            row for row in rows
            if row.get("symbol") == "BTCUSDT"
            and str(row.get("create_time") or "")[:10] == period_date.isoformat()
        ]
        if not valid:
            return None
        return max(valid, key=lambda row: str(row.get("create_time") or ""))

    def _daily_klines(self, start_date: date, end_date: date) -> dict[str, list[object]]:
        start_ms = int(datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
        end_ms = int(
            datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp()
            * 1000 - 1
        )
        query = urlencode({
            "symbol": "BTCUSDT", "interval": "1d", "startTime": start_ms,
            "endTime": end_ms, "limit": min(1000, (end_date - start_date).days + 2),
        })
        try:
            payload = self._json_requester(f"{self.api_base_url}/fapi/v1/klines?{query}")
        except Exception:
            raise RuntimeError("Binance historical daily-volume request failed") from None
        if not isinstance(payload, list):
            raise RuntimeError("Binance historical daily-volume response was invalid")
        rows: dict[str, list[object]] = {}
        for item in payload:
            if not isinstance(item, list) or len(item) < 10:
                continue
            period = _utc_period_date(item[0], end_timestamp=False)
            if start_date.isoformat() <= period <= end_date.isoformat():
                rows[period] = item
        return rows

    def fetch_range(
        self, start_date: date, end_date: date, *, fetched_at: datetime | None = None,
    ) -> list[dict[str, object]]:
        if end_date < start_date or (end_date - start_date).days >= TARGET_HISTORY_DAYS:
            raise ValueError("Binance historical range must contain between 1 and 365 days")
        observed_at = fetched_at or datetime.now(timezone.utc)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        observed_iso = observed_at.astimezone(timezone.utc).isoformat(timespec="seconds")
        requested_dates = [
            start_date + timedelta(days=offset)
            for offset in range((end_date - start_date).days + 1)
        ]
        metrics: dict[str, Mapping[str, object]] = {}
        with ThreadPoolExecutor(
            max_workers=self._max_workers, thread_name_prefix="binance-btc-archive",
        ) as executor:
            futures = {executor.submit(self._metrics_for_date, day): day for day in requested_dates}
            for future in as_completed(futures):
                row = future.result()
                if row is not None:
                    metrics[futures[future].isoformat()] = row
        klines = self._daily_klines(start_date, end_date)
        available_dates = sorted(set(metrics) & set(klines))
        minimum_coverage = max(1, math.floor(len(requested_dates) * 0.95))
        if len(available_dates) < minimum_coverage:
            raise RuntimeError("Binance one-year archive coverage was below 95%")

        rows: list[dict[str, object]] = []
        for period_date in available_dates:
            metric = metrics[period_date]
            kline = klines[period_date]
            account_ratio = _nonnegative_float(
                metric.get("count_long_short_ratio"), "historical account ratio",
            )
            ratio_total = 1 + account_ratio
            total_volume = _nonnegative_float(kline[5], "historical total volume")
            taker_buy = _nonnegative_float(kline[9], "historical taker buy volume")
            taker_sell = total_volume - taker_buy
            if taker_sell < -1e-8:
                raise RuntimeError("Binance historical taker volume was inconsistent")
            raw = {"metrics_close": dict(metric), "daily_kline": list(kline)}
            payload_hash = hashlib.sha256(
                json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            rows.append({
                "venue": VENUE,
                "instrument": INSTRUMENT,
                "period_date": period_date,
                "taker_buy_volume": taker_buy,
                "taker_sell_volume": max(0.0, taker_sell),
                "long_account_pct": account_ratio / ratio_total * 100,
                "short_account_pct": 1 / ratio_total * 100,
                "open_interest_value_quote": _nonnegative_float(
                    metric.get("sum_open_interest_value"), "historical open interest value",
                ),
                "quote_currency": "USDT",
                "provider_name": self.name,
                "source_endpoints": [
                    "/data/futures/um/daily/metrics/BTCUSDT/",
                    "/fapi/v1/klines",
                ],
                "payload": raw,
                "payload_hash": payload_hash,
                "fetched_at": observed_iso,
            })
        return rows


_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bitcoin-derivatives")
_lock = RLock()
_future: Future[dict[str, int]] | None = None
_failure: tuple[datetime, str] | None = None


def _history_ready(rows: list[Mapping[str, object]]) -> bool:
    dates = sorted({str(row.get("period_date") or "") for row in rows if row.get("period_date")})
    if len(dates) < MIN_READY_OBSERVATIONS:
        return False
    try:
        return (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days >= MIN_READY_SPAN_DAYS
    except ValueError:
        return False


def bitcoin_derivatives_refresh_due(
    db_path: str | Path | None = None, *, now: datetime | None = None,
) -> bool:
    current = now or datetime.now(timezone.utc)
    rows = get_bitcoin_derivatives_daily_observations(db_path=db_path)
    if not rows:
        return True
    if not _history_ready(rows):
        return True
    try:
        latest_fetch = datetime.fromisoformat(str(rows[-1]["fetched_at"]))
    except (KeyError, TypeError, ValueError):
        return True
    if latest_fetch.tzinfo is None:
        latest_fetch = latest_fetch.replace(tzinfo=timezone.utc)
    return latest_fetch.astimezone(timezone.utc).date() < current.astimezone(timezone.utc).date()


def refresh_bitcoin_derivatives(
    provider: BitcoinDerivativesProvider | None = None,
    archive_provider: BinanceBitcoinDerivativesArchiveProvider | None = None,
    db_path: str | Path | None = None,
    *, now: datetime | None = None,
) -> dict[str, int]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    live_rows = (provider or BinanceBitcoinDerivativesProvider()).fetch_daily(
        limit=30, fetched_at=current,
    )
    existing = get_bitcoin_derivatives_daily_observations(db_path=db_path)
    combined_dates = sorted({
        str(row["period_date"]) for row in [*existing, *live_rows] if row.get("period_date")
    })
    historical_rows: list[dict[str, object]] = []
    if not _history_ready([*existing, *live_rows]) and combined_dates:
        target_start = current.astimezone(timezone.utc).date() - timedelta(days=TARGET_HISTORY_DAYS)
        archive_end = min(
            date.fromisoformat(combined_dates[0]) - timedelta(days=1),
            current.astimezone(timezone.utc).date() - timedelta(days=1),
        )
        if target_start <= archive_end:
            historical_rows = (
                archive_provider or BinanceBitcoinDerivativesArchiveProvider()
            ).fetch_range(target_start, archive_end, fetched_at=current)
    rows = [*historical_rows, *live_rows]
    return {
        "rows_received": len(rows),
        "rows_inserted": save_bitcoin_derivatives_daily_observations(rows, db_path=db_path),
        "historical_rows_received": len(historical_rows),
    }


def _finished(future: Future[dict[str, int]], db_path: str | Path | None) -> None:
    global _future, _failure
    with _lock:
        try:
            future.result()
            _failure = None
            record_provider_health(PROVIDER_KEY, HEALTH_TICKER, "healthy", db_path=db_path)
        except Exception as exc:
            safe_error = f"{type(exc).__name__}: BTC derivatives provider unavailable"
            _failure = (datetime.now(timezone.utc), safe_error)
            record_provider_health(
                PROVIDER_KEY, HEALTH_TICKER, "failed", error=safe_error,
                cooldown_until=(datetime.now(timezone.utc) + RETRY_COOLDOWN).isoformat(timespec="seconds"),
                db_path=db_path,
            )
        _future = None


def schedule_bitcoin_derivatives_refresh(
    *, provider_factory: Callable[[], BitcoinDerivativesProvider] = BinanceBitcoinDerivativesProvider,
    archive_provider_factory: Callable[[], BinanceBitcoinDerivativesArchiveProvider] = BinanceBitcoinDerivativesArchiveProvider,
    db_path: str | Path | None = None,
) -> bool:
    global _future
    with _lock:
        if _future is not None or not bitcoin_derivatives_refresh_due(db_path):
            return False
        if _failure and datetime.now(timezone.utc) - _failure[0] < RETRY_COOLDOWN:
            return False
        record_provider_health(PROVIDER_KEY, HEALTH_TICKER, "running", db_path=db_path)
        _future = _executor.submit(
            refresh_bitcoin_derivatives, provider_factory(), archive_provider_factory(), db_path,
        )
        _future.add_done_callback(lambda completed, path=db_path: _finished(completed, path))
        return True


def bitcoin_derivatives_status(db_path: str | Path | None = None) -> str:
    with _lock:
        if _future is not None:
            return "Updating"
        failure = _failure
    rows = get_bitcoin_derivatives_daily_observations(db_path=db_path)
    if failure:
        return "Provider unavailable"
    if _history_ready(rows):
        return "Stale" if bitcoin_derivatives_refresh_due(db_path) else "Ready"
    return "Provider unavailable" if failure else "Pending"
