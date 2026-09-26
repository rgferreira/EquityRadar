from datetime import datetime, timezone
import math

import pytest

from src.data.research_signals import bounded_get, latest_batch, save_batch, record_status, statuses
from src.data.macro_context import parse_policy, parse_series, macro_summary
from src.data.institutional_positioning import normalize
from src.data.options_context import greeks, liquid_contract, summarize_chain


def test_revision_history_asof_dedup_and_failure_preserves_evidence(tmp_path):
    db = tmp_path / "signals.db"
    one = save_batch("macro", "test", {"value": 1}, observed_at="2025-01-01T12:00:00+00:00", db_path=db)
    assert one == save_batch("macro", "test", {"value": 1}, observed_at="2025-01-02T12:00:00+00:00", db_path=db)
    two = save_batch("macro", "test", {"value": 2}, observed_at="2025-01-03T12:00:00+00:00", db_path=db)
    assert two != one
    assert latest_batch("macro", "test", as_of="2025-01-02T23:00:00+00:00", db_path=db)["payload"] == {"value": 1}
    assert latest_batch("macro", "test", as_of="2024-12-31T23:00:00+00:00", db_path=db) is None
    save_batch("macro", "offset", {"v": 1}, observed_at="2025-01-01T10:00:00-05:00", db_path=db)
    assert latest_batch("macro", "offset", as_of="2025-01-01T14:59:59+00:00", db_path=db) is None
    assert latest_batch("macro", "offset", as_of="2025-01-01T15:00:00+00:00", db_path=db)["observed_at"] == "2025-01-01T15:00:00+00:00"
    record_status("macro", "test", "failed", error_code="https://secret?key=private", db_path=db)
    assert next(s for s in statuses(db) if s["scope"] == "test")["error_code"] == "provider_error"
    assert latest_batch("macro", "test", db_path=db)["batch_id"] == two
    reverted = save_batch("macro", "test", {"value": 1}, observed_at="2025-01-04T12:00:00+00:00", db_path=db)
    assert reverted != one
    assert latest_batch("macro", "test", db_path=db)["payload"] == {"value": 1}
    assert latest_batch("macro", "test", as_of="2025-01-03T23:00:00+00:00", db_path=db)["payload"] == {"value": 2}
    with pytest.raises(ValueError):
        save_batch("macro", "test", {}, observed_at="2025-01-01T12:00:00", db_path=db)


@pytest.mark.parametrize("url", ["http://www.federalreserve.gov/feed", "https://evil.test/feed", "https://u:p@www.federalreserve.gov/feed", "https://www.federalreserve.gov:123/feed"])
def test_public_provider_allowlist_before_network(url):
    with pytest.raises(ValueError):
        bounded_get(url)


def test_macro_period_is_not_publication_and_stale_or_future_cannot_contribute(tmp_path):
    raw = b'<rdf><channel><date>2025-01-03T21:15:00+00:00</date></channel><item><value>4.5</value><observationPeriod>2025-01-02</observationPeriod></item></rdf>'
    payload = parse_series(raw, "https://www.federalreserve.gov/feed")
    assert payload["records"][0]["published_at"] is None
    db = tmp_path / "macro.db"
    save_batch("macro", "nominal_2y", payload, observed_at="2025-01-03T12:00:00+00:00", db_path=db)
    report = macro_summary(db, as_of="2025-01-03T13:00:00+00:00")
    assert report["series"]["nominal_2y"]["status"] == "stale_or_unverified"
    assert report["curve_10y_minus_2y_pp"] is None
    assert macro_summary(db, as_of="2025-02-03T13:00:00+00:00")["series"]["nominal_2y"]["status"] == "stale_or_unverified"
    rss = b'<rss><channel><item><title>Policy</title><link>https://www.federalreserve.gov/test</link><pubDate>Fri, 03 Jan 2025 18:00:00 GMT</pubDate></item></channel></rss>'
    assert parse_policy(rss)["records"][0]["published_at"] == "2025-01-03T18:00:00+00:00"


def test_cftc_normalization_preserves_missing_and_weekly_gap():
    def row(day, long):
        return {"cftc_contract_market_code": "209742", "market_and_exchange_names": "Synthetic",
                "report_date_as_yyyy_mm_dd": day, "open_interest_all": "1000",
                "asset_mgr_positions_long": str(long), "asset_mgr_positions_short": "200",
                "lev_money_positions_long": "100", "lev_money_positions_short": "300"}
    rows = normalize([row("2025-01-07", 400), row("2025-01-14", 500), row("2025-01-28", 600)])
    assert rows[0]["asset_manager_net_pct_oi"] == 20
    assert rows[1]["asset_manager_weekly_change_pp"] == 10
    assert rows[2]["asset_manager_weekly_change_pp"] is None
    assert rows[0]["published_at"] is None
    bad = row("2025-01-28", 600); bad["open_interest_all"] = "0"
    assert normalize([bad]) == []


def option(kind="call", strike=100):
    return {"kind": kind, "expiry": "2025-02-07", "strike": strike, "bid": 4, "ask": 4.5,
            "openInterest": 100, "impliedVolatility": .3, "contractSize": "REGULAR", "currency": "USD",
            "lastTradeDate": "2025-01-06T20:00:00+00:00"}


def test_options_liquidity_and_greeks_do_not_invent_missing_rate_or_dividend():
    now = datetime(2025, 1, 7, 20, tzinfo=timezone.utc)
    assert liquid_contract(option(), 100, now)
    for change in ({"bid": 0}, {"ask": 20}, {"openInterest": 99}, {"lastTradeDate": "2024-12-01T00:00:00+00:00"},
                   {"impliedVolatility": float("nan")}, {"contractSize": "MINI"}, {"expiry": "2025-01-10"}):
        assert not liquid_contract({**option(), **change}, 100, now)
    assert greeks(100, 100, .1, .3, None, 0, "call") is None
    assert greeks(100, 100, .1, .3, .04, None, "call") is None
    call = greeks(100, 100, .1, .3, .04, .01, "call")
    put = greeks(100, 100, .1, .3, .04, .01, "put")
    assert call["delta"] - put["delta"] == pytest.approx(math.exp(-.001))
    assert call["gamma"] == put["gamma"] and call["vega_per_vol_point"] > 0
    rows = [option(kind, strike) for kind in ("call", "put") for strike in (99, 100, 101)]
    summary = summarize_chain(rows, 100, now, rate=.04, quote_at=now.isoformat())
    assert summary["status"] == "usable_context" and summary["greeks_contracts"] == 0
    assert summarize_chain(rows[:3], 100, now, quote_at=now.isoformat())["status"] == "insufficient_liquidity"
    assert summarize_chain(rows, 100, now, rate=.04, dividend_yield=0, quote_at=now.isoformat())["greeks_contracts"] == 6
