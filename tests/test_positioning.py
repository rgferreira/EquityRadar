from collections import namedtuple
from datetime import datetime

import pandas as pd
import pytest

from src.data.database import (
    get_cached_positioning, get_positioning_history, init_db, record_provider_health,
    save_positioning_snapshot,
)
from src.data.positioning import YahooPositioningProvider
from src.data.positioning_refresh import (
    _refresh, finra_backfill_status, finra_refresh_due, positioning_is_fresh,
)
from src.scoring.positioning import (
    apply_positioning_adjustment, effective_positioning_snapshot,
    positioning_score_adjustments, positioning_scores, short_interest_freshness,
)


def sample_snapshot():
    return {
        "reporting_date": "2026-06-30",
        "short": {"short_percent_float": .12, "short_change_pct": 20, "days_to_cover": 6},
        "options": {"put_call_oi_ratio": .6, "put_call_volume_ratio": .7},
        "ownership": {"institutional_percent": .75},
        "insiders": {"purchase_rows": 4, "sale_rows": 1},
        "analyst_actions": {"upgrades_90d": 5, "downgrades_90d": 1},
    }


def test_positioning_scores_are_transparent_and_confidence_adjusted():
    scores = positioning_scores(sample_snapshot())
    assert scores["long_positioning"] > 50
    assert scores["short_pressure"] > 50
    assert scores["squeeze_potential"] > 50
    assert scores["confidence"] == 100
    assert any("Short float" in note for note in scores["notes"])


def test_positioning_no_longer_reuses_analyst_actions():
    snapshot = sample_snapshot()
    bullish = positioning_scores(snapshot)
    snapshot["analyst_actions"] = {"upgrades_90d": 0, "downgrades_90d": 20}
    bearish = positioning_scores(snapshot)
    assert bullish == bearish
    assert not any("Analyst" in note for note in bullish["notes"])


def test_historical_short_trend_produces_small_capped_decision_modifiers():
    history = [{
        "reporting_date": f"2026-0{month}-15", "snapshot_type": "historical_short_interest",
        "short": {"shares_short": 100 + month * 10},
    } for month in range(1, 7)]
    result = positioning_score_adjustments(sample_snapshot(), history, technical_score=70, as_of="2026-07-15")
    assert -5 <= result["entry_adjustment"] <= 5
    assert -7 <= result["exit_adjustment"] <= 7
    assert result["entry_adjustment"] < 0
    assert result["exit_adjustment"] > 0
    assert result["reliability"] == 100
    assert result["history_points"] == 6


def test_missing_positioning_never_changes_established_scores():
    result = positioning_score_adjustments(None, [], technical_score=80)
    assert result["entry_adjustment"] == 0
    assert result["exit_adjustment"] == 0
    assert apply_positioning_adjustment(98, 5) == 100


def test_short_reversal_lever_requires_falling_shorts_and_technical_confirmation():
    history = [
        {"reporting_date": "2026-05-31", "snapshot_type": "historical_short_interest", "short": {"shares_short": 100, "short_change_pct": 8}},
        {"reporting_date": "2026-06-15", "snapshot_type": "historical_short_interest", "short": {"shares_short": 108, "short_change_pct": 8}},
        {"reporting_date": "2026-06-30", "snapshot_type": "historical_short_interest", "short": {"shares_short": 102, "short_change_pct": -5.6}},
    ]
    confirmed = positioning_score_adjustments(sample_snapshot(), history, technical_score=70, as_of="2026-07-15")
    unconfirmed = positioning_score_adjustments(sample_snapshot(), history, technical_score=50, as_of="2026-07-15")
    assert confirmed["short_reversal_confirmed"] is True
    assert confirmed["entry_adjustment"] > unconfirmed["entry_adjustment"]
    assert confirmed["exit_adjustment"] < unconfirmed["exit_adjustment"]


def test_stale_short_interest_is_visible_but_cannot_change_scores():
    stale = {
        "reporting_date": "2026-05-31",
        "short": {"short_percent_float": .25, "short_change_pct": 40, "days_to_cover": 10},
    }
    result = positioning_score_adjustments(stale, [], technical_score=70, as_of="2026-07-15")
    assert result["short_evidence_status"] == "stale"
    assert result["short_scoring_eligible"] is False
    assert result["entry_adjustment"] == 0
    assert result["exit_adjustment"] == 0
    assert "excluded" in " ".join(result["notes"])


def test_freshest_official_report_overrides_older_cached_short_fields():
    cached = {
        **sample_snapshot(), "reporting_date": "2026-06-13",
        "short": {"shares_short": 100, "short_change_pct": 20},
    }
    official = [{
        "reporting_date": "2026-06-30", "snapshot_type": "historical_short_interest",
        "provider_name": "FINRA", "short": {"shares_short": 80, "short_change_pct": -20},
    }]
    result = effective_positioning_snapshot(cached, official, "2026-07-15")
    assert result["report_date"] == "2026-06-30"
    assert result["snapshot"]["short"]["shares_short"] == 80
    assert result["scoring_eligible"] is True
    assert short_interest_freshness(official[0], "2026-08-01")["scoring_eligible"] is False


def test_finra_refresh_is_due_daily_even_with_existing_history(tmp_path):
    database = tmp_path / "radar.db"
    init_db(database)
    assert finra_refresh_due("MU", database, now=datetime(2026, 7, 15, 9, 0)) is True
    record_provider_health("finra", "MU", "healthy", db_path=database)
    assert finra_refresh_due("MU", database, now=datetime.now()) is False


def test_finra_refresh_skips_unsupported_instruments(tmp_path):
    database = tmp_path / "radar.db"
    init_db(database)

    assert finra_refresh_due("BTC-USD", database, now=datetime(2026, 7, 15, 9, 0)) is False
    assert finra_backfill_status("BTC-USD", database) == "Not applicable"


def test_positioning_cache_round_trip(tmp_path):
    database = tmp_path / "radar.db"
    payload = sample_snapshot()
    save_positioning_snapshot("aapl", payload, "mock", "2026-07-01", "2026-07-11T12:00:00", database)
    cached = get_cached_positioning("AAPL", database)
    assert cached["short"]["days_to_cover"] == 6
    assert cached["provider_name"] == "mock"
    assert len(get_positioning_history("AAPL", database)) == 1


def test_new_positioning_refresh_gets_observed_known_at(tmp_path):
    class StubProvider:
        name = "stub positioning"

        def fetch(self, ticker):
            return {**sample_snapshot(), "ticker": ticker, "reporting_date": "2026-06-30"}

    database = tmp_path / "radar.db"
    refreshed = _refresh("AAPL", StubProvider, database)
    cached = get_cached_positioning("AAPL", database)

    assert refreshed["period_end"] == "2026-06-30"
    assert cached["known_at"] == cached["fetched_at"]
    assert cached["known_at_status"] == "verified_observed"


def test_positioning_freshness_is_daily():
    assert positioning_is_fresh({"fetched_at": datetime.now().isoformat()})
    assert not positioning_is_fresh({"fetched_at": "2020-01-01T00:00:00"})


def test_yahoo_provider_normalizes_options_short_and_fmp_float(monkeypatch):
    Chain = namedtuple("Chain", "calls puts")
    calls = pd.DataFrame({"volume": [10, 20], "openInterest": [100, 200], "impliedVolatility": [.3, .4]})
    puts = pd.DataFrame({"volume": [15], "openInterest": [150], "impliedVolatility": [.5]})

    class FakeTicker:
        info = {
            "sharesShort": 120, "sharesShortPriorMonth": 100, "shortPercentOfFloat": .12,
            "shortRatio": 6, "heldPercentInstitutions": .75, "heldPercentInsiders": .02,
        }
        options = ("2026-08-01",)
        insider_transactions = pd.DataFrame({"Text": ["Purchase", "Sale", "Purchase"]})
        upgrades_downgrades = pd.DataFrame(
            {"Action": ["up", "down", "up"]}, index=pd.date_range(end=pd.Timestamp.now(), periods=3)
        )

        def option_chain(self, expiry):
            return Chain(calls, puts)

    class FakeFMP:
        def _optional_get(self, endpoint, **params):
            return [{"floatShares": 999}]

    monkeypatch.setattr("src.data.positioning.yf.Ticker", lambda ticker: FakeTicker())
    result = YahooPositioningProvider(FakeFMP()).fetch("abc")
    assert result["short"]["short_change_pct"] == pytest.approx(20)
    assert result["options"]["put_call_oi_ratio"] == .5
    assert result["ownership"]["public_float_shares_fmp"] == 999
    assert result["insiders"] == {"purchase_rows": 2, "sale_rows": 1}
