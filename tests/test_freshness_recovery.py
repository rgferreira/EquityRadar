from datetime import datetime
from dataclasses import replace

from src.data.database import add_ticker, get_connection, init_db, record_provider_health
from src.data.maintenance_cleanup import clean_orphan_caches
from src.data.congress_trading import CongressRequestError
from src.operations import provider_health
from src.whaleseeker import run_latest_refresh, whale_catchup_states
from test_whaleseeker import SequencedProvider, row


class NewerProvider(SequencedProvider):
    def fetch(self, *args, **kwargs):
        return replace(super().fetch(*args, **kwargs), fetched_at="2026-09-01T12:00:00Z")


def test_gap_recovery_resumes_past_new_pages_until_original_overlap(tmp_path):
    db = tmp_path / "whales.db"
    h = [row("oldh1", "House", "AAA"), row("oldh2", "House", "AAA")]
    s = [row("olds1", "Senate", "BBB"), row("olds2", "Senate", "BBB")]
    run_latest_refresh(SequencedProvider([h,s]), db_path=db, page_size=2)
    new = lambda prefix: [row(prefix+str(i), prefix, "CCC") for i in range(2)]
    first = NewerProvider([new("h0"),new("h1"),new("s0"),new("s1")])
    result = run_latest_refresh(first, db_path=db, page_size=2, max_pages=2)
    assert all(r["catchup_pending"] for r in result)
    second = NewerProvider([new("h0"),h,new("s0"),s])
    result = run_latest_refresh(second, db_path=db, page_size=2, max_pages=2)
    assert second.calls == [("house",0,2),("house",2,2),("senate",0,2),("senate",2,2)]
    assert all(r["continuity"] == "overlap_observed" for r in result)
    assert all(not r["catchup_pending"] for r in result)


def test_entitlement_gap_stays_visible_but_latest_pages_keep_refreshing(tmp_path):
    db = tmp_path / "entitlement.db"
    old = [row("old1", "Old", "AAA"),row("old2", "Old", "AAA")]
    new = [row("new1", "New", "BBB"),row("new2", "New", "BBB")]
    run_latest_refresh(SequencedProvider([old,old]), db_path=db, page_size=2)
    denied = NewerProvider([new,CongressRequestError(402),new,CongressRequestError(402)])
    run_latest_refresh(denied, db_path=db, page_size=2, max_pages=2)
    assert all(r["status"] == "blocked_entitlement" for r in whale_catchup_states(db))
    latest = NewerProvider([new,new])
    result = run_latest_refresh(latest, db_path=db, page_size=2)
    assert latest.calls == [("house",0,2),("senate",0,2)]
    assert all(r["status"] == "refreshed" and r["catchup_pending"] for r in result)


def test_disposable_orphans_are_removed_but_active_and_benchmark_caches_survive(tmp_path):
    db = tmp_path / "cleanup.db"
    add_ticker("ACTIVE",db)
    with get_connection(db) as connection:
        for ticker in ("ACTIVE","RETIRED","SPY","^GSPC"):
            connection.execute("INSERT INTO industry_research_cache (ticker,payload_json,provider_name,fetched_at) VALUES (?,?,?,?)",
                               (ticker,"{}","synthetic","2026-09-01"))
    preview = clean_orphan_caches(db)
    assert preview["total"] == 1
    assert clean_orphan_caches(db,apply=True)["total"] == 1
    assert clean_orphan_caches(db,apply=True)["total"] == 0
    with get_connection(db) as connection:
        assert {r[0] for r in connection.execute("SELECT ticker FROM industry_research_cache")} == {"ACTIVE","SPY","^GSPC"}


def test_provider_success_expires_instead_of_remaining_green(tmp_path):
    db = tmp_path / "health.db"
    init_db(db)
    record_provider_health("fmp_congress","HOUSE","healthy",db_path=db)
    with get_connection(db) as connection:
        connection.execute("UPDATE provider_health_state SET last_success_at='2026-08-12T12:00:00'")
    rows = provider_health(db,now=datetime(2026,9,24,12,0))
    assert next(r for r in rows if r["source"] == "Fmp Congress operations")["status"] == "Stale"
