"""Read-only WhaleSeeker views and bounded historical-bootstrap orchestration."""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from statistics import median

from src.data.congress_trading import CongressTradingProvider, ingest_congress_page
from src.data.database import (
    get_whale_backfill_states,
    get_whale_disclosures,
    update_whale_backfill_state,
)


WHALESEEKER_ENVIRONMENT_VARIABLE = "WHALESEEKER_ENABLED"
FALSE_VALUES = {"0", "false", "no", "off", "disabled"}


def whaleseeker_runtime_enabled(environment: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environment is None else environment
    return str(source.get(WHALESEEKER_ENVIRONMENT_VARIABLE, "true")).strip().lower() not in FALSE_VALUES


def run_historical_backfill_step(
    provider: CongressTradingProvider, *, db_path: str | Path | None = None,
    page_size: int = 25,
) -> list[dict[str, object]]:
    """Import at most one page per chamber, advancing only after a committed batch."""
    if not whaleseeker_runtime_enabled():
        return [{"status": "runtime_disabled", "provider_key": provider.provider_key}]
    states = {
        str(row["chamber"]): row
        for row in get_whale_backfill_states(provider.provider_key, db_path)
    }
    results = []
    for chamber in ("house", "senate"):
        state = states[chamber]
        page = int(state["next_page"])
        if state["status"] == "complete":
            results.append({
                "provider_key": provider.provider_key,
                "chamber": chamber,
                "page": page,
                "status": "complete",
                "rows_received": 0,
            })
            continue
        update_whale_backfill_state(
            provider.provider_key, chamber, status="running", next_page=page,
            db_path=db_path,
        )
        try:
            ingestion = ingest_congress_page(
                provider, chamber, page=page, page_size=page_size, db_path=db_path,
            )
        except RuntimeError as exc:
            update_whale_backfill_state(
                provider.provider_key, chamber, status="failed", next_page=page,
                last_error=str(exc), db_path=db_path,
            )
            results.append({
                "provider_key": provider.provider_key,
                "chamber": chamber,
                "page": page,
                "status": "failed",
                "rows_received": 0,
                "error": str(exc),
            })
            continue
        rows_received = int(ingestion["rows_received"])
        complete = rows_received == 0
        next_page = page if complete else page + 1
        update_whale_backfill_state(
            provider.provider_key, chamber,
            status="complete" if complete else "ready",
            next_page=next_page,
            last_rows_received=rows_received,
            db_path=db_path,
        )
        results.append({
            **ingestion,
            "chamber": chamber,
            "page": page,
            "status": "complete" if complete else "imported",
            "next_page": next_page,
        })
    return results


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _filing_delay(record: Mapping[str, object]) -> int | None:
    traded = _as_date(record.get("trade_date"))
    filed = _as_date(record.get("filed_date"))
    return (filed - traded).days if traded and filed else None


def _observation_delay(record: Mapping[str, object]) -> int | None:
    filed = _as_date(record.get("filed_date"))
    observed = _as_date(record.get("known_at"))
    return (observed - filed).days if filed and observed else None


def disclosure_feed(
    observations: Sequence[Mapping[str, object]], *,
    relevant_tickers: set[str] | None = None, limit: int | None = None,
) -> list[dict[str, object]]:
    """Build a deterministic disclosure view with both legal and app-observation delay."""
    normalized_tickers = {ticker.strip().upper() for ticker in relevant_tickers or set()}
    records = []
    for record in observations:
        ticker = str(record.get("ticker") or "").upper()
        if normalized_tickers and ticker not in normalized_tickers:
            continue
        records.append({
            "Ticker": ticker or "—",
            "Politician": str(record.get("politician_name") or "Unknown"),
            "Chamber": str(record.get("chamber") or "unknown").title(),
            "Trade": str(record.get("transaction_type") or "other").title(),
            "Amount": str(record.get("amount_text") or "Not disclosed"),
            "Traded": record.get("trade_date"),
            "Filed": record.get("filed_date"),
            "Filing lag (days)": _filing_delay(record),
            "First seen by app": record.get("known_at"),
            "App lag (days)": _observation_delay(record),
            "Owner": str(record.get("owner") or "Not specified"),
            "Source": record.get("source_document_url"),
        })
    records.sort(
        key=lambda row: (
            str(row["Filed"] or ""), str(row["First seen by app"] or ""),
            str(row["Ticker"]), str(row["Politician"]),
        ),
        reverse=True,
    )
    return records[:limit] if limit is not None else records


def whale_dashboard_feed(
    tickers: Sequence[str], db_path: str | Path | None = None, *, limit: int = 6,
) -> list[dict[str, object]]:
    observations = get_whale_disclosures(latest_only=True, db_path=db_path)
    return disclosure_feed(observations, relevant_tickers=set(tickers), limit=limit)


def politician_profiles(
    observations: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Summarize observed activity without claiming unmeasured investment performance."""
    groups: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for record in observations:
        groups[(
            str(record.get("politician_name") or "Unknown"),
            str(record.get("chamber") or "unknown").title(),
        )].append(record)
    profiles = []
    for (politician, chamber), rows in groups.items():
        delays = [delay for delay in (_filing_delay(row) for row in rows) if delay is not None]
        tickers = sorted({str(row.get("ticker")) for row in rows if row.get("ticker")})
        filed_dates = sorted(str(row["filed_date"]) for row in rows if row.get("filed_date"))
        profiles.append({
            "Politician": politician,
            "Chamber": chamber,
            "Disclosures": len(rows),
            "Purchases": sum(str(row.get("transaction_type")) == "purchase" for row in rows),
            "Sales": sum(str(row.get("transaction_type")) == "sale" for row in rows),
            "Unique tickers": len(tickers),
            "Tickers": ", ".join(tickers[:8]) + ("…" if len(tickers) > 8 else ""),
            "Median filing lag": round(median(delays), 1) if delays else None,
            "First filing": filed_dates[0] if filed_dates else None,
            "Latest filing": filed_dates[-1] if filed_dates else None,
            "Copyable return": "Pending prospective outcome policy",
        })
    return sorted(
        profiles,
        key=lambda row: (int(row["Disclosures"]), str(row["Latest filing"] or "")),
        reverse=True,
    )
