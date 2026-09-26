"""Read-only WhaleSeeker views and bounded historical-bootstrap orchestration."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median

import pandas as pd

from src.data.congress_trading import CongressTradingProvider, ingest_congress_page
from src.data.database import (
    get_connection, init_db,
    get_whale_backfill_states,
    get_whale_disclosures,
    update_whale_backfill_state,
)
from src.data.market_data import calculate_return_since_date, fetch_price_history


WHALESEEKER_ENVIRONMENT_VARIABLE = "WHALESEEKER_ENABLED"
FALSE_VALUES = {"0", "false", "no", "off", "disabled"}
TRADE_FILTERS = {"purchase", "sale"}
REPORTED_TICKER_PATTERN = re.compile(r"^[A-Z0-9]{1,6}(?:[.-][A-Z0-9]{1,2})?$")
SHARE_CLASS_CONTEXT = {
    "GOOG": "Class C (non-voting)",
    "GOOGL": "Class A (voting)",
}


def whaleseeker_runtime_enabled(environment: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environment is None else environment
    return str(source.get(WHALESEEKER_ENVIRONMENT_VARIABLE, "true")).strip().lower() not in FALSE_VALUES


def normalize_trade_filter(selected_trade: object) -> set[str] | None:
    """Translate UI state into the supported transaction filter.

    Streamlit single-selection controls may temporarily yield ``None``. Treat
    that state as All instead of inventing a non-existent ``none`` trade type.
    """
    normalized = str(selected_trade or "all").strip().lower()
    return {normalized} if normalized in TRADE_FILTERS else None


def empty_disclosure_message(
    selected_trade: object, *, restricted_to_universe: bool,
) -> str:
    """Return an understandable empty-state message for either UI scope."""
    normalized = normalize_trade_filter(selected_trade)
    subject = next(iter(normalized)).title() if normalized else "Congressional"
    if restricted_to_universe:
        return (
            f"No {subject.lower()} disclosures involve a security in the current "
            "Portfolio or Watchlist. Try All disclosures to see the full local sample."
        )
    return f"No {subject.lower()} disclosures are available in the local WhaleSeeker data."


def clean_asset_description(value: object) -> str:
    """Remove provider counters from display without changing stored lineage."""
    description = " ".join(str(value or "Unknown asset").split())
    cleaned = re.sub(r"(?:\s+\(\d+\))+$", "", description).strip()
    return cleaned or "Unknown asset"


def asset_display_name(ticker: str, description: object) -> str:
    """Add security-class context while retaining the provider-reported ticker."""
    asset = clean_asset_description(description)
    share_class = SHARE_CLASS_CONTEXT.get(ticker)
    return f"{asset} · {share_class}" if share_class else asset


def reported_ticker_quality(ticker: str) -> str:
    """Flag suspicious formatting; never guess a replacement security."""
    if not ticker or ticker == "—":
        return "Missing"
    return "Reported" if REPORTED_TICKER_PATTERN.fullmatch(ticker) else "Review format"


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


def whale_ingestion_summary(db_path=None):
    """Small aggregate read: never load every raw provider payload to render a page."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        return dict(connection.execute(
            "SELECT COUNT(*) batches, MAX(fetched_at) last_provider_check FROM whale_raw_payloads"
        ).fetchone())


def whale_catchup_states(db_path=None):
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS whale_catchup_state (
            provider_key TEXT NOT NULL, chamber TEXT NOT NULL, anchor_observed_at TEXT,
            next_page INTEGER NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(provider_key,chamber))""")
        return [dict(row) for row in connection.execute("SELECT * FROM whale_catchup_state")]


def run_latest_refresh(
    provider: CongressTradingProvider, *, db_path: str | Path | None = None,
    page_size: int = 25, max_pages: int = 4,
) -> list[dict[str, object]]:
    """Refresh latest plus bounded gap recovery, independently of historical cursors.

    A checkpoint survives the page budget. Overlap is tested against observations
    from BEFORE recovery began; newly imported pages cannot falsely close the gap.
    Pagination can move, so this reports observed overlap rather than full history.
    """
    if not whaleseeker_runtime_enabled():
        return [{"status": "runtime_disabled", "provider_key": provider.provider_key}]
    if not 1 <= max_pages <= 20:
        raise ValueError("max_pages must be between 1 and 20 per chamber")
    states = {(r["provider_key"], r["chamber"]): r for r in whale_catchup_states(db_path)}
    observations = get_whale_disclosures(latest_only=False, db_path=db_path)
    results = []
    for chamber in ("house", "senate"):
        previous = states.get((provider.provider_key, chamber), {})
        old = [r for r in observations if r["chamber"] == chamber and r["provider_key"] == provider.provider_key]
        entitlement_blocked = previous.get("status") == "blocked_entitlement"
        continuing = previous.get("status") in {"pending", "blocked_entitlement"}
        anchor = previous.get("anchor_observed_at") if continuing else max(
            (str(r["fetched_at"]) for r in old), default=None)
        anchored_ids = {r["observation_id"] for r in old if anchor and str(r["fetched_at"]) <= anchor}
        start_page = int(previous["next_page"]) if continuing else 0
        # On resumption page 0 is checked as well, without mistaking it for continuity.
        pages = ([0] if continuing and start_page > 0 and max_pages > 1 else []) + list(range(start_page, start_page + max_pages))
        pages = pages[:max_pages]
        if entitlement_blocked:
            pages = [0]
        inserted = received = checked = 0
        status, next_page = "pending", start_page
        error = None
        for page in pages:
            try:
                ingestion = ingest_congress_page(provider, chamber, page=page, page_size=page_size, db_path=db_path)
            except RuntimeError as exc:
                status, error = "blocked_entitlement" if getattr(exc, "code", None) == 402 else "failed", str(exc)
                next_page = page
                break
            inserted += int(ingestion["observations_inserted"])
            received += int(ingestion["rows_received"])
            checked += 1
            if entitlement_blocked:
                status = "blocked_entitlement"
                break
            # The raw batch links only newly inserted observations; use normalized
            # source identities from the persisted payload for exact overlap.
            from src.data.congress_trading import CongressProviderBatch, prepare_ingestion
            import json
            with get_connection(db_path) as connection:
                raw = connection.execute("""SELECT * FROM whale_raw_payloads
                    WHERE raw_payload_id=?""", (ingestion["raw_payload_id"],)).fetchone()
            batch = CongressProviderBatch(provider.provider_key, f"{chamber}-latest",
                {"page": page, "limit": page_size}, json.loads(raw["payload_json"]), ingestion["fetched_at"])
            _, normalized = prepare_ingestion(batch)
            overlap = any(r["observation_id"] in anchored_ids for r in normalized)
            if continuing and page == 0 and start_page > 0:
                continue
            next_page = page + 1
            if not anchor or overlap or int(ingestion["rows_received"]) < page_size:
                status = "overlap_observed" if overlap else "initial_latest_only" if not anchor else "end_observed"
                break
        with get_connection(db_path) as connection:
            connection.execute("""INSERT INTO whale_catchup_state VALUES (?,?,?,?,?,?)
                ON CONFLICT(provider_key,chamber) DO UPDATE SET
                anchor_observed_at=excluded.anchor_observed_at,next_page=excluded.next_page,
                status=excluded.status,updated_at=excluded.updated_at""",
                (provider.provider_key, chamber, anchor, next_page,
                 "pending" if status in {"pending", "failed"} else status,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
        results.append({"provider_key": provider.provider_key, "chamber": chamber, "page": 0,
                        "status": "failed" if error else "refreshed", "rows_received": received,
                        "observations_inserted": inserted, "pages_checked": checked,
                        "catchup_pending": status in {"pending", "failed", "blocked_entitlement"},
                        "continuity": status, "next_page": next_page, "error": error})
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
    relevant_tickers: set[str] | None = None,
    transaction_types: set[str] | None = None,
    order_by: str = "filed",
    limit: int | None = None,
) -> list[dict[str, object]]:
    """Build a deterministic disclosure view with both legal and app-observation delay."""
    normalized_tickers = {ticker.strip().upper() for ticker in relevant_tickers or set()}
    normalized_types = {trade.strip().lower() for trade in transaction_types or set()}
    if order_by not in {"filed", "trade"}:
        raise ValueError("order_by must be 'filed' or 'trade'")
    records = []
    for record in observations:
        ticker = str(record.get("ticker") or "").upper()
        if normalized_tickers and ticker not in normalized_tickers:
            continue
        transaction_type = str(record.get("transaction_type") or "other").lower()
        if normalized_types and transaction_type not in normalized_types:
            continue
        records.append({
            "Ticker": ticker or "—",
            "Asset": asset_display_name(ticker, record.get("asset_description")),
            "Ticker quality": reported_ticker_quality(ticker),
            "Politician": str(record.get("politician_name") or "Unknown"),
            "Chamber": str(record.get("chamber") or "unknown").title(),
            "Trade": transaction_type.title(),
            "Amount": str(record.get("amount_text") or "Not disclosed"),
            "Traded": record.get("trade_date"),
            "Filed": record.get("filed_date"),
            "Filing lag (days)": _filing_delay(record),
            "First seen by app": record.get("known_at"),
            "App lag (days)": _observation_delay(record),
            "Owner": str(record.get("owner") or "Not specified"),
            "Source": record.get("source_document_url"),
        })
    primary_date = "Traded" if order_by == "trade" else "Filed"
    records.sort(key=lambda row: (
        str(row[primary_date] or ""), str(row["Filed"] or ""),
        str(row["First seen by app"] or ""), str(row["Ticker"]),
        str(row["Politician"]),
    ), reverse=True)
    return records[:limit] if limit is not None else records


def whale_dashboard_feed(
    tickers: Sequence[str] | None = None, db_path: str | Path | None = None, *,
    transaction_types: set[str] | None = None, limit: int = 6,
) -> list[dict[str, object]]:
    observations = get_whale_disclosures(latest_only=True, db_path=db_path)
    return disclosure_feed(
        observations,
        relevant_tickers=set(tickers) if tickers is not None else None,
        transaction_types=transaction_types,
        order_by="trade", limit=limit,
    )


def add_since_trade_returns(
    feed: Sequence[Mapping[str, object]], *,
    history_fetcher: Callable[..., pd.DataFrame] = fetch_price_history,
    max_workers: int = 8,
) -> list[dict[str, object]]:
    """Add descriptive adjusted-close returns without changing feed order."""
    enriched = [dict(row) for row in feed]
    tickers = sorted({
        str(row.get("Ticker") or "").strip().upper()
        for row in enriched
        if str(row.get("Ticker") or "").strip() not in {"", "—"}
    })
    if not tickers:
        return enriched

    def fetch(ticker: str) -> tuple[str, pd.DataFrame | None]:
        trade_dates = [
            parsed for row in enriched
            if str(row.get("Ticker") or "").strip().upper() == ticker
            and (parsed := _as_date(row.get("Traded"))) is not None
        ]
        oldest = min(trade_dates) if trade_dates else None
        age_days = (date.today() - oldest).days if oldest else None
        period = "1y" if age_days is not None and age_days <= 366 else (
            "3y" if age_days is not None and age_days <= 1_096 else "max"
        )
        try:
            return ticker, history_fetcher(ticker, period=period)
        except Exception:
            return ticker, None

    worker_count = max(1, min(max_workers, len(tickers)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        histories = dict(executor.map(fetch, tickers))

    for row in enriched:
        history = histories.get(str(row.get("Ticker") or "").strip().upper())
        row["Since trade %"] = (
            calculate_return_since_date(history, row.get("Traded"))
            if history is not None else None
        )
    return enriched


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
