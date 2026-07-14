"""Local operational health and server-lifetime scheduling."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable

from src.backup import create_verified_backup
from src.data.database import get_connection, get_watchlist, init_db
from src.utils.config import DATABASE_PATH


SCHEDULER_INTERVAL = timedelta(minutes=15)
BACKUP_INTERVAL = timedelta(days=1)
_lock = Lock()
_stop = Event()
_thread: Thread | None = None


def _parse(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _elapsed(current: datetime, previous: datetime) -> timedelta:
    """Compare timestamps safely across legacy naive and provider-aware values."""
    if current.tzinfo is None and previous.tzinfo is not None:
        current = current.replace(tzinfo=previous.tzinfo)
    elif current.tzinfo is not None and previous.tzinfo is None:
        previous = previous.replace(tzinfo=current.tzinfo)
    return current - previous


def record_operation(
    key: str, status: str, *, detail: dict[str, object] | None = None,
    error: str | None = None, db_path: str | Path | None = None,
) -> None:
    init_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    started = now if status == "running" else None
    completed = now if status in {"completed", "failed"} else None
    with get_connection(db_path) as connection:
        connection.execute(
            """INSERT INTO operation_runs
               (operation_key,status,started_at,completed_at,detail_json,error,updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(operation_key) DO UPDATE SET status=excluded.status,
                 started_at=COALESCE(excluded.started_at,operation_runs.started_at),
                 completed_at=excluded.completed_at,detail_json=excluded.detail_json,
                 error=excluded.error,updated_at=excluded.updated_at""",
            (key, status, started, completed, json.dumps(detail or {}, sort_keys=True), error, now),
        )


def get_operation_runs(db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM operation_runs ORDER BY operation_key"
        ).fetchall()]


def provider_health(db_path: str | Path | None = None, *, now: datetime | None = None) -> list[dict[str, object]]:
    """Summarize persisted provider evidence without exposing payload contents."""
    init_db(db_path)
    current = now or datetime.now()
    sources = (
        ("Fundamentals", "fundamentals_cache", "provider_name"),
        ("Industry & analysts", "industry_research_cache", "provider_name"),
        ("Positioning", "positioning_cache", "provider_name"),
        ("FINRA history", "positioning_history", "provider_name"),
        ("Extended hours", "extended_hours_cache", "provider_name"),
    )
    rows = []
    with get_connection(db_path) as connection:
        for label, table, provider_column in sources:
            result = connection.execute(
                f"SELECT COUNT(*) count, MAX(fetched_at) last_success, "
                f"GROUP_CONCAT(DISTINCT {provider_column}) providers FROM {table}"
            ).fetchone()
            last = _parse(result["last_success"])
            age_hours = _elapsed(current, last).total_seconds() / 3600 if last else None
            rows.append({
                "source": label,
                "status": "Missing" if not result["count"] else "Stale" if age_hours is not None and age_hours > 36 else "Healthy",
                "records": int(result["count"]),
                "last_success": result["last_success"],
                "age_hours": round(age_hours, 1) if age_hours is not None else None,
                "providers": result["providers"] or "—",
            })
    return rows


def run_due_maintenance(
    db_path: str | Path | None = None, *, now: datetime | None = None,
    backup_runner: Callable[..., dict[str, object]] = create_verified_backup,
) -> dict[str, object]:
    """Schedule due provider work and a daily verified backup."""
    current = now or datetime.now()
    database = db_path or DATABASE_PATH
    runs = {row["operation_key"]: row for row in get_operation_runs(database)}
    last_refresh = _parse(runs.get("scheduled_refresh", {}).get("completed_at"))
    last_backup = _parse(runs.get("verified_backup", {}).get("completed_at"))
    result: dict[str, object] = {"refresh_scheduled": [], "backup": None}
    if last_refresh is None or _elapsed(current, last_refresh) >= SCHEDULER_INTERVAL:
        record_operation("scheduled_refresh", "running", db_path=database)
        try:
            tickers = get_watchlist(database)
            from src.data.extended_hours_refresh import schedule_extended_hours_refresh
            from src.data.industry_refresh import schedule_industry_refresh
            from src.data.positioning_refresh import schedule_positioning_refresh
            from src.data.backtest_refresh import schedule_outcome_refresh
            from src.data.cutoff_suggestions import schedule_cutoff_suggestions
            from src.data.market_data import fetch_price_history
            from src.data.fmp import FMPProvider
            from src.data.fundamentals import FallbackFundamentalsProvider, get_fundamentals
            from src.data.yfinance_fundamentals import YFinanceFundamentalsProvider
            from src.utils.config import FMP_API_KEY
            scheduled = sorted(set(
                schedule_industry_refresh(tickers, max_new=2, db_path=database)
                + schedule_positioning_refresh(tickers, max_new=2, db_path=database)
                + schedule_extended_hours_refresh(tickers, max_new=2, db_path=database)
            ))
            providers = [FMPProvider(FMP_API_KEY)] if FMP_API_KEY else []
            providers.append(YFinanceFundamentalsProvider())
            fundamentals_provider = FallbackFundamentalsProvider(providers)

            def warm_core(ticker: str) -> None:
                try:
                    history = fetch_price_history(ticker, period="1y")
                    price = float(history["Close"].dropna().iloc[-1]) if not history.empty else None
                except Exception:
                    price = None
                get_fundamentals(ticker, fundamentals_provider, price, db_path=database)

            pool = ThreadPoolExecutor(max_workers=min(4, max(1, len(tickers))), thread_name_prefix="core-refresh")
            futures = [pool.submit(warm_core, ticker) for ticker in tickers]
            wait(futures, timeout=45)
            pool.shutdown(wait=False, cancel_futures=True)
            schedule_outcome_refresh(database)
            schedule_cutoff_suggestions(tickers, database)
            result["refresh_scheduled"] = scheduled
            record_operation(
                "scheduled_refresh", "completed",
                detail={"scheduled": len(scheduled), "core_tickers": len(tickers)}, db_path=database,
            )
        except Exception as exc:
            record_operation("scheduled_refresh", "failed", error=str(exc), db_path=database)
    if last_backup is None or _elapsed(current, last_backup) >= BACKUP_INTERVAL:
        record_operation("verified_backup", "running", db_path=database)
        try:
            backup = backup_runner(source=database, now=current)
            result["backup"] = backup
            record_operation(
                "verified_backup", "completed",
                detail={"manifest_path": backup["manifest_path"], "sha256": backup["sha256"]},
                db_path=database,
            )
        except Exception as exc:
            record_operation("verified_backup", "failed", error=str(exc), db_path=database)
    return result


def start_local_scheduler(db_path: str | Path | None = None) -> bool:
    """Start one daemon scheduler for the Streamlit server process."""
    global _thread
    with _lock:
        if _thread and _thread.is_alive():
            return False
        _stop.clear()

        def loop() -> None:
            while not _stop.is_set():
                run_due_maintenance(db_path)
                _stop.wait(60)

        _thread = Thread(target=loop, name="equity-radar-maintenance", daemon=True)
        _thread.start()
        return True


def stop_local_scheduler() -> None:
    _stop.set()
