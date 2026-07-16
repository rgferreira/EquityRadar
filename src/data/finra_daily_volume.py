"""FINRA consolidated daily short-sale-volume flow adapter and bounded backfill."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.data.database import (
    get_finra_daily_short_volume_fetches, save_finra_daily_short_volume_file,
)


class DailyShortVolumeProvider(Protocol):
    name: str

    def fetch_date(
        self, trade_date: date, tickers: Iterable[str],
    ) -> tuple[list[dict[str, object]], str]: ...


class DailyShortVolumeFileUnavailable(RuntimeError):
    """A dated FINRA file does not exist, normally for a weekend or holiday."""

    def __init__(self, source_url: str) -> None:
        super().__init__(f"FINRA daily file unavailable: {source_url}")
        self.source_url = source_url


class FINRADailyShortVolumeProvider:
    name = "FINRA Consolidated NMS Daily Short Sale Volume"
    base_url = "https://cdn.finra.org/equity/regsho/daily"

    def __init__(self, opener: Callable[..., object] = urlopen) -> None:
        self._opener = opener

    def source_url(self, trade_date: date) -> str:
        return f"{self.base_url}/CNMSshvol{trade_date:%Y%m%d}.txt"

    def fetch_date(
        self, trade_date: date, tickers: Iterable[str],
    ) -> tuple[list[dict[str, object]], str]:
        symbols = {str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()}
        source_url = self.source_url(trade_date)
        request = Request(source_url, headers={"User-Agent": "PersonalEquityRadar/1.0"})
        try:
            with self._opener(request, timeout=30) as response:
                content = response.read().decode("utf-8-sig")
        except HTTPError as exc:
            # The FINRA CDN returns 403, rather than 404, for dated files that
            # do not exist (normally US market holidays).
            if exc.code in {403, 404}:
                raise DailyShortVolumeFileUnavailable(source_url) from exc
            raise
        rows: list[dict[str, object]] = []
        for item in csv.DictReader(StringIO(content), delimiter="|"):
            ticker = str(item.get("Symbol") or "").strip().upper()
            if ticker not in symbols:
                continue
            raw = {
                "ticker": ticker,
                "trade_date": str(item.get("Date") or ""),
                "short_volume": str(item.get("ShortVolume") or "0"),
                "short_exempt_volume": str(item.get("ShortExemptVolume") or "0"),
                "total_volume": str(item.get("TotalVolume") or "0"),
                "market": str(item.get("Market") or ""),
            }
            payload_hash = hashlib.sha256(
                json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            rows.append({
                "ticker": ticker,
                "short_volume": float(raw["short_volume"]),
                "short_exempt_volume": float(raw["short_exempt_volume"]),
                "total_volume": float(raw["total_volume"]),
                "market": raw["market"],
                "payload_hash": payload_hash,
            })
        return rows, source_url


def backfill_finra_daily_short_volume(
    tickers: list[str], provider: DailyShortVolumeProvider | None = None,
    db_path: str | Path | None = None, *, lookback_days: int = 120,
    now: datetime | None = None, force_full_lookback: bool = False,
) -> dict[str, int]:
    """Fetch missing files, optionally replaying the bounded window for new tickers."""
    provider = provider or FINRADailyShortVolumeProvider()
    current = now or datetime.now()
    end_date = current.date() - timedelta(days=1)
    start_date = end_date - timedelta(days=max(1, lookback_days))
    fetched = {str(row["trade_date"]): str(row["status"]) for row in get_finra_daily_short_volume_fetches(db_path)}
    revision_window = end_date - timedelta(days=4)
    candidates = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5 and (
            force_full_lookback or cursor.isoformat() not in fetched or cursor >= revision_window
        ):
            candidates.append(cursor)
        cursor += timedelta(days=1)

    files_fetched = unavailable = rows_inserted = errors = 0
    fetched_at = current.isoformat(timespec="seconds")
    for trade_date in candidates:
        try:
            rows, source_url = provider.fetch_date(trade_date, tickers)
        except DailyShortVolumeFileUnavailable as exc:
            save_finra_daily_short_volume_file(
                trade_date.isoformat(), [], provider.name, exc.source_url, fetched_at,
                status="unavailable", db_path=db_path,
            )
            unavailable += 1
            continue
        except Exception:
            errors += 1
            continue
        rows_inserted += save_finra_daily_short_volume_file(
            trade_date.isoformat(), rows, provider.name, source_url, fetched_at, db_path=db_path,
        )
        files_fetched += 1
    if errors and not files_fetched and not unavailable:
        raise RuntimeError("FINRA daily short-volume files could not be retrieved")
    return {
        "files_checked": len(candidates), "files_fetched": files_fetched,
        "unavailable": unavailable, "rows_inserted": rows_inserted, "errors": errors,
    }
