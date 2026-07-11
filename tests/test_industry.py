from src.data.database import get_cached_industry_research, save_industry_research
from src.data.industry_refresh import industry_refresh_status, schedule_industry_refresh, snapshot_is_fresh
from src.scoring.industry import (
    analyst_sentiment_score, business_quality_score, industry_entry_score,
    relative_valuation_score,
)


def sample_research():
    return {
        "profile": {
            "revenue_growth": .25, "operating_margin": .18, "free_cash_flow_margin": .16,
            "gross_margin": .78, "forward_pe": 30, "price_to_sales": 7,
        },
        "peer_profiles": [
            {"forward_pe": 45, "price_to_sales": 10},
            {"forward_pe": 40, "price_to_sales": 9},
            {"forward_pe": 50, "price_to_sales": 11},
            {"forward_pe": 35, "price_to_sales": 8},
            {"forward_pe": 55, "price_to_sales": 12},
        ],
        "recommendations": {"strongBuy": 8, "buy": 12, "hold": 5, "sell": 1, "strongSell": 0},
        "eps_revisions": {"upLast30days": 6, "downLast30days": 2, "upLast7days": 1, "downLast7days": 0},
        "price_targets": {"median_upside_pct": 25, "low": 150, "median": 200, "high": 240},
    }


def test_industry_feature_rewards_quality_and_peer_discount():
    research = sample_research()
    quality, quality_confidence, _ = business_quality_score(research)
    valuation, valuation_confidence, _ = relative_valuation_score(research)
    sentiment, sentiment_confidence, _ = analyst_sentiment_score(research)
    assert quality > 70 and quality_confidence == 1
    assert valuation > 70 and valuation_confidence == 1
    assert sentiment > 50 and sentiment_confidence > .8


def test_industry_entry_score_keeps_weak_timing_but_is_not_dominated_by_it():
    result = industry_entry_score(20, 40, sample_research())
    assert result["technical_timing"] == 20
    assert result["score"] > 50


def test_missing_industry_inputs_are_neutral_and_low_confidence():
    result = industry_entry_score(20, 40, None)
    assert result["business_quality"] == 50
    assert result["relative_valuation"] == 50
    assert result["analyst_sentiment"] == 50
    assert result["quality_confidence"] == 0


def test_industry_research_cache_round_trip(tmp_path):
    database = tmp_path / "radar.db"
    payload = sample_research()
    save_industry_research("zs", payload, "mock", "2026-07-11T12:00:00", database)
    cached = get_cached_industry_research("ZS", database)
    assert cached["profile"]["forward_pe"] == 30
    assert cached["provider_name"] == "mock"


def test_background_refresh_persists_snapshot_and_reaches_ready(tmp_path):
    import time

    class StubProvider:
        name = "stub"

        def fetch(self, ticker):
            return {"applicable": True, "profile": {"ticker": ticker}, "peer_profiles": []}

    database = tmp_path / "radar.db"
    assert schedule_industry_refresh(
        ["ABC"], max_new=1, provider_factory=StubProvider, db_path=database
    ) == ["ABC"]
    for _ in range(100):
        if industry_refresh_status("ABC", database) == "Limited coverage":
            break
        time.sleep(.01)
    assert industry_refresh_status("ABC", database) == "Limited coverage"
    assert get_cached_industry_research("ABC", database)["provider_name"] == "stub"


def test_legacy_limited_snapshot_triggers_immediate_discovery():
    from datetime import datetime
    snapshot = {"fetched_at": datetime.now().isoformat(), "applicable": True, "peer_profiles": []}
    assert snapshot_is_fresh(snapshot) is False


def test_discovery_ranks_dynamic_candidates(monkeypatch):
    from src.data.industry import YahooIndustryResearchProvider

    profiles = {
        "CRM": {"ticker": "CRM", "quote_type": "EQUITY", "sector": "Technology", "industry": "Software - Application", "market_cap": 130e9, "revenue_growth": .10, "operating_margin": .20},
        "NOW": {"ticker": "NOW", "quote_type": "EQUITY", "sector": "Technology", "industry": "Software - Application", "market_cap": 160e9, "revenue_growth": .12, "operating_margin": .18, "forward_pe": 40},
        "ADBE": {"ticker": "ADBE", "quote_type": "EQUITY", "sector": "Technology", "industry": "Software - Application", "market_cap": 140e9, "revenue_growth": .09, "operating_margin": .22, "forward_pe": 25},
        "SNOW": {"ticker": "SNOW", "quote_type": "EQUITY", "sector": "Technology", "industry": "Software - Application", "market_cap": 75e9, "revenue_growth": .20, "operating_margin": .05, "price_to_sales": 12},
    }
    provider = YahooIndustryResearchProvider(fmp_provider=None)
    provider.fmp_provider = None
    monkeypatch.setattr(provider, "_profile", lambda ticker: profiles[ticker])
    monkeypatch.setattr(provider, "_yahoo_candidates", lambda profile: ["NOW", "ADBE", "SNOW"])
    peers, source, evidence = provider._discover_peers("CRM", profiles["CRM"])
    assert set(peers) == {"NOW", "ADBE", "SNOW"}
    assert source == "Yahoo industry"
    assert all(item["similarity_score"] > 0 and item["reasons"] for item in evidence)
