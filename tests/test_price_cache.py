import time
import pandas as pd
from src.data import price_cache as cache
from src.data.database import get_connection


def test_persistent_prices_survive_process_lru_and_stale_read_is_nonblocking(tmp_path, monkeypatch):
    path = tmp_path / "prices.db"
    calls = []
    def provider(*a, **kw):
        calls.append(kw)
        return pd.DataFrame({"Close": [100.0, 101.5]}, index=pd.date_range("2026-01-01", periods=2))
    monkeypatch.setattr(cache.market_data, "fetch_price_history", provider)
    first = cache.fetch_cached_price_history("TEST", db_path=path)
    second = cache.fetch_cached_price_history("TEST", db_path=path)
    assert list(first.Close) == list(second.Close)
    assert len(calls) == 1
    with get_connection(path) as con:
        con.execute("UPDATE market_price_cache SET fetched_at=?", (time.time() - 3600,))
    submitted = []
    class Queue:
        def submit(self, *a):
            submitted.append(a)
    monkeypatch.setattr(cache, "_pool", Queue())
    monkeypatch.setattr(cache, "_invalidated_at", 0)
    stale = cache.fetch_cached_price_history("TEST", db_path=path)
    assert stale.attrs["stale"]
    assert len(calls) == 1
    assert len(submitted) == 1
    cache.fetch_cached_price_history("TEST", db_path=path)
    assert len(submitted) == 1
    key = submitted[0][1]
    cache._pending.discard(key)


def test_provider_failure_retains_last_good_prices(tmp_path, monkeypatch):
    path = tmp_path / "fallback.db"
    monkeypatch.setattr(cache.market_data, "fetch_price_history", lambda *a, **k: pd.DataFrame({"Close": [100.0]}, index=pd.date_range("2026-01-01", periods=1)))
    cache.fetch_cached_price_history("TEST", db_path=path)
    def fail(*a, **k):
        raise TimeoutError("provider unavailable")
    monkeypatch.setattr(cache.market_data, "fetch_price_history", fail)
    cache._refresh((str(path), "TEST", "1y"), 8, path)
    assert cache.fetch_cached_price_history("TEST", db_path=path).Close.iloc[0] == 100
