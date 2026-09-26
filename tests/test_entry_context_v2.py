from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from src.entry_context import (build_snapshot, candidate_weights, replay, save_snapshot, snapshots,
                               price_features)
from src.strategy_validation import (build_window, drawdown, evaluate, paired_block_interval,
                                     portfolio_path)


def cohort(day="2025-01-01", source="retrospective_unverified"):
    inputs = [{"ticker": f"T{i}", "entry_score": 80 - i, "entry_signal": "Buy candidate",
               "sector_etf": "XLK" if i < 3 else "XLF", "metrics": {"latest_price": 120, "ma_200": 100,
               "return_12m": 20 + i, "return_1m": 2, "return_3m": 30 - i}} for i in range(6)]
    return {"as_of_date": day, "source": source, "inputs": inputs,
            "market": {"latest_price": 120, "ma_200": 100, "return_3m": 5},
            "sectors": {"XLK": {"return_3m": 10}, "XLF": {"return_3m": 8}}}


def histories():
    dates = pd.bdate_range("2023-01-02", "2026-06-30")
    return {t: pd.DataFrame({"Close": 100 * np.exp(np.arange(len(dates)) * .0005 * (i + 1))}, index=dates)
            for i, t in enumerate(["SPY", "XLK", "XLF", *[f"T{i}" for i in range(6)]])}


def test_candidates_preserve_recorded_buys_market_abstention_and_sector_caps():
    c = cohort()
    weights = candidate_weights(c)["weights"]
    assert sum(weights["current_policy"].values()) == pytest.approx(1)
    assert len(weights["candidate_sector"]) == 4
    assert sum(weights["candidate_sector"].values()) == pytest.approx(.8)
    c["market"]["latest_price"] = 80
    assert candidate_weights(c)["weights"]["candidate_market"] == {}
    c["market"]["ma_200"] = None
    result = candidate_weights(c)
    assert "candidate_market" not in result["weights"]
    assert result["unavailable"]["candidate_market"] == "missing_market_regime"
    c["inputs"][0]["sector_etf"] = None
    assert "candidate_sector" not in candidate_weights(c)["weights"]
    c["inputs"][0]["entry_score"] = 0  # Valid observed zero, never coerced to a default score.
    assert "current_policy" in candidate_weights(c)["weights"]


def test_snapshot_first_daily_capture_and_replay_tampering(tmp_path):
    c = cohort()
    snap = build_snapshot(c["inputs"], captured_at="2025-01-01T15:00:00+00:00", market=c["market"], sectors=c["sectors"])
    assert replay(snap)
    db = tmp_path / "snap.db"
    assert save_snapshot(snap, db)
    second = build_snapshot(c["inputs"], captured_at="2025-01-01T16:00:00+00:00", market={}, sectors={})
    assert not save_snapshot(second, db)
    assert snapshots(db) == [snap]
    altered = deepcopy(snap); altered["inputs"][0]["entry_score"] += 1
    assert not replay(altered)
    assert evaluate([altered], histories())["exclusions"] == {"invalid_frozen_snapshot": 1}


def test_fixed_shares_fees_cash_and_drawdown_include_initial_capital():
    paths = {"SPY": [100, 110, 105], "A": [100, 80, 120]}
    result = portfolio_path(paths, {"A": .5}, 10)
    assert result["equity"][-1] == pytest.approx(.5 + .5 / 1.0005 * 1.2 * .9995)
    assert result["cost_pct"] == pytest.approx((.5 / 1.0005 + .5 / 1.0005 * 1.2) * .0005 * 100)
    assert drawdown(result["equity"]) < -10
    assert portfolio_path(paths, {}, 50)["equity"] == [1, 1, 1]
    assert portfolio_path(paths, {"A": 1}, 50)["net_return_pct"] < portfolio_path(paths, {"A": 1}, 10)["net_return_pct"]
    assert drawdown([.999, 1.1]) == pytest.approx(-.1)


def test_no_lookahead_no_missing_unselected_survivor_or_duplicate_prices():
    c, h = cohort(), histories()
    features = price_features(h["SPY"], c["as_of_date"])
    poisoned = h["SPY"].copy(); poisoned.loc[poisoned.index > c["as_of_date"], "Close"] *= 100
    assert features == price_features(poisoned, c["as_of_date"])
    window, reason = build_window(c, h, "1M")
    assert not reason and window["dates"][0] > c["as_of_date"] and len(window["dates"]) == 22
    h["T0"] = h["T0"].drop(pd.Timestamp(window["dates"][10]))
    assert build_window(c, h, "1M")[1] == "incomplete_path_for_frozen_universe"
    h = histories(); h["T0"] = pd.concat([h["T0"], h["T0"].tail(1)])
    assert build_window(c, h, "1M")[1] == "duplicate_price_dates"


def test_purged_prior_labels_nonoverlap_cost_stress_and_no_automatic_promotion():
    dates = pd.bdate_range("2024-02-01", "2025-10-01", freq="10B")
    cs = [cohort(d.date().isoformat()) for d in dates]
    report = evaluate(cs, histories(), "1M")
    assert report["test_cohorts"] >= 10
    rows = [r for r in report["periods"] if r["strategy"] == "current_policy" and r["cost_bps"] == 10]
    for previous, current in zip(rows, rows[1:]):
        assert previous["end_date"] < current["execution_date"]
    for row in rows:
        assert len(row["purged_prior_dates"]) >= 3
        for day in row["purged_prior_dates"]:
            end = build_window(cohort(day), histories(), "1M")[0]["dates"][-1]
            assert date.fromisoformat(end) < date.fromisoformat(row["as_of_date"]) - timedelta(days=5)
    assert {r["cost_bps"] for r in report["summary"]} == {10, 30, 50}
    assert not report["promotion_eligible"]
    assert all(r["excess_current_pct"] == 0 for r in rows)


def test_confidence_intervals_require_periods_and_repeat_exactly():
    assert paired_block_interval([1] * 9) is None
    assert paired_block_interval([1] * 10) == [1, 1]
    assert paired_block_interval(list(range(12))) == paired_block_interval(list(range(12)))


def test_forward_capture_runs_without_a_dashboard_and_replays_existing_policy(tmp_path):
    from src.data.database import add_ticker
    from src.entry_context import capture_context
    db = tmp_path / "unattended.db"
    for i in range(6):
        add_ticker(f"T{i}", db)
    result = capture_context(histories(), {}, db, now=datetime(2025, 1, 7, 20, tzinfo=timezone.utc))
    assert result["snapshot_saved"] and result["inputs"] == 6
    snap = snapshots(db)[0]
    assert replay(snap)
    assert all(r["policy_inputs"] and r["decision_source"] == "shared_dashboard_policy_completed_daily_prices" for r in snap["inputs"])
    assert not capture_context(histories(), {}, db, now=datetime(2025, 1, 7, 21, tzinfo=timezone.utc))["snapshot_saved"]


def test_first_matured_price_vintage_is_immutable_and_removed_names_still_evaluate(tmp_path):
    from src.data.database import get_connection
    db = tmp_path / "paths.db"
    h = histories()
    c = cohort()
    snap = build_snapshot(c["inputs"], captured_at="2025-01-01T15:00:00+00:00", market=c["market"], sectors=c["sectors"])
    save_snapshot(snap, db)
    first = evaluate([snap], h, db_path=db, persist_paths=True)
    with get_connection(db) as con:
        raw = con.execute("SELECT payload_json FROM entry_context_paths").fetchone()[0]
    h["T0"].loc[h["T0"].index > "2025-01-01", "Close"] *= 2
    second = evaluate([snap], h, db_path=db, persist_paths=True)
    assert first["dataset_signature"] == second["dataset_signature"]
    with get_connection(db) as con:
        assert con.execute("SELECT payload_json FROM entry_context_paths").fetchone()[0] == raw


@pytest.mark.parametrize("industry,entry_mod,learning", [(None, 0, 0), (75, 3, 2), (99, 8, -4), (1, -10, 5)])
def test_shared_dashboard_combination_keeps_original_sequential_clamping(industry, entry_mod, learning):
    from src.scoring.current_policy import combine_current_decisions
    from src.scoring.decision import calculate_coverage_aware_entry_score, calculate_exit_review_score
    from src.scoring.positioning import apply_positioning_adjustment
    result = combine_current_decisions(technical=80, valuation=50, risk=60, industry_score=industry,
        valuation_available=False, entry_modifier=entry_mod, exit_modifier=-3, learning_entry=learning, learning_exit=2)
    original = industry if industry is not None else calculate_coverage_aware_entry_score(80, 50, 60, valuation_available=False)
    assert result["entry_score"] == apply_positioning_adjustment(apply_positioning_adjustment(original, entry_mod), learning)
    assert result["exit_score"] == apply_positioning_adjustment(apply_positioning_adjustment(calculate_exit_review_score(80, 60), -3), 2)
