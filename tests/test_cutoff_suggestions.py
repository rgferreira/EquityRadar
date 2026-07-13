import pandas as pd

from src.data.cutoff_suggestions import generate_cutoff_suggestions, suggestion_signature
from src.data.database import (
    get_simulation_suggestions, init_db, replace_simulation_suggestions,
)


def test_suggestions_are_persisted_with_rationale_and_evidence(tmp_path):
    db = tmp_path / "suggestions.db"
    init_db(db)
    replace_simulation_suggestions([{
        "suggested_date": "2026-03-31", "trigger_type": "Market regime",
        "rationale": "SPY crossed its 50-day average.", "priority": 82,
        "evidence": {"ticker": "SPY"},
    }], "signature", db)
    rows = get_simulation_suggestions(db)
    assert rows[0]["suggested_date"] == "2026-03-31"
    assert rows[0]["rationale"]
    assert rows[0]["evidence"]["ticker"] == "SPY"


def test_watchlist_change_invalidates_daily_signature():
    assert suggestion_signature(["AAPL"]) != suggestion_signature(["AAPL", "NVDA"])


def test_generator_ranks_distinct_market_and_watchlist_events(monkeypatch, tmp_path):
    index = pd.date_range("2025-01-02", "2026-07-10", freq="B")
    base = pd.Series([100 + index_number * .05 for index_number in range(len(index))], index=index)
    spy = base.copy()
    spy.loc["2026-02-02":"2026-03-02"] *= .78
    nvda = base.copy()
    nvda.loc["2026-04-01":"2026-05-01"] *= 1.35

    def fake_history(ticker, period="3y"):
        return pd.DataFrame({"Close": spy if ticker == "SPY" else nvda})

    monkeypatch.setattr("src.data.cutoff_suggestions.fetch_price_history", fake_history)
    suggestions = generate_cutoff_suggestions(["NVDA"], tmp_path / "suggestions.db")
    assert suggestions
    assert len({item["suggested_date"] for item in suggestions}) == len(suggestions)
    assert any(item["trigger_type"].startswith("Market") for item in suggestions)
    assert len({item["trigger_type"] for item in suggestions}) >= 3
    assert any("NVDA" in item["rationale"] for item in suggestions)
    assert all(item["rationale"] and item["evidence"] for item in suggestions)
