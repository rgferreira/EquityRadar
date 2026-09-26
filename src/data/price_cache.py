"""Persist public price histories; serve the last response while refreshing stale data."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from threading import Lock
import time

import pandas as pd

from src.data import market_data
from src.data.database import get_connection, init_db, _database_path

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="price-cache")
_lock = Lock()
_pending: set[tuple[str, str, str]] = set()
_retry_after: dict[tuple[str, str, str], float] = {}
_invalidated_at = 0.0
TTL_SECONDS = 900


def invalidate_price_cache() -> None:
    global _invalidated_at
    _invalidated_at = time.time()


def _schema(db_path: str | Path | None) -> None:
    init_db(db_path)
    with get_connection(db_path) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS market_price_cache (
            ticker TEXT NOT NULL, period TEXT NOT NULL, fetched_at REAL NOT NULL,
            history_json TEXT NOT NULL, PRIMARY KEY(ticker, period))""")


def _download(ticker: str, period: str, timeout: int, db_path: str | Path | None) -> pd.DataFrame:
    # Direct bounded fetch bypasses the process LRU when a persisted response expires.
    history = market_data.fetch_price_history(ticker, period=period, timeout=timeout, force_refresh=True)
    with get_connection(db_path) as con:
        con.execute("""INSERT INTO market_price_cache VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker,period) DO UPDATE SET fetched_at=excluded.fetched_at,
            history_json=excluded.history_json""",
            (ticker, period, time.time(), history.to_json(orient="split", date_format="iso")))
    return history


def _refresh(key: tuple[str, str, str], timeout: int, db_path: str | Path | None) -> None:
    try:
        _download(key[1], key[2], timeout, db_path)
    except Exception:
        # Preserve the last successful response and bound failures to once per minute.
        pass
    finally:
        with _lock:
            _pending.discard(key)
            _retry_after[key] = time.monotonic() + 60


def fetch_cached_price_history(
    ticker: str, timeout: int = 8, period: str = "1y", *,
    db_path: str | Path | None = None, force_refresh: bool = False,
) -> pd.DataFrame:
    symbol = ticker.strip().upper()
    if not symbol or period not in market_data.SUPPORTED_PERIODS:
        raise ValueError("Invalid ticker or price-history period")
    db_path = _database_path(db_path)
    _schema(db_path)
    with get_connection(db_path) as con:
        row = con.execute("SELECT fetched_at,history_json FROM market_price_cache WHERE ticker=? AND period=?",
                          (symbol, period)).fetchone()
    if row and not force_refresh and float(row["fetched_at"]) >= _invalidated_at:
        fetched = float(row["fetched_at"])
        market_data._price_history_fetched_at[(symbol, period)] = datetime.fromtimestamp(fetched).isoformat(timespec="seconds")
        key = (str(db_path), symbol, period)
        if time.time() - fetched > TTL_SECONDS:
            with _lock:
                if key not in _pending and time.monotonic() >= _retry_after.get(key, 0):
                    _pending.add(key)
                    _pool.submit(_refresh, key, timeout, db_path)
        history = pd.read_json(StringIO(row["history_json"]), orient="split")
        history.index = pd.to_datetime(history.index)
        history.attrs["fetched_at"] = datetime.fromtimestamp(fetched, timezone.utc).isoformat()
        history.attrs["stale"] = time.time() - fetched > TTL_SECONDS
        return history
    history = _download(symbol, period, timeout, db_path)
    history.attrs["stale"] = False
    return history
