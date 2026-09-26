from copy import deepcopy

import pytest

from src.research_lab import (CONFIG, VERSION, build_snapshot, compare_strategies,
                              get_snapshots, rank_entries, replay_snapshot, save_snapshot)


def inputs():
    return [{"ticker": f"S{i}", "metrics": {"latest_price": 120, "ma_200": 100,
              "return_12m": 10 + i * 5, "return_1m": 5}} for i in range(10)]


def cohort(day="2025-01-01", start="2025-01-02", end="2025-02-03"):
    rows = inputs()
    for i, row in enumerate(rows):
        row["label"] = {"benchmark_ticker": "SPY", "timing_convention": CONFIG["execution"],
            "cost_bps": 10.0, "execution_date": start, "outcomes": {"1M": {
                "end_date": end, "security_return_pct": i, "benchmark_return_pct": 3}}}
    return {"as_of_date": day, "inputs": rows}


def test_ranking_is_continuous_excludes_missing_and_leaves_empty_slots_in_cash():
    rows = inputs()
    rows[9]["metrics"]["ma_200"] = 130  # Highest momentum is below its trend.
    ranked = rank_entries(rows)
    assert [r["ticker"] for r in ranked["rows"] if r["selected"]] == ["S8", "S7"]
    assert ranked["rows"][0]["momentum_12_1_pct"] == pytest.approx((1.55 / 1.05 - 1) * 100)
    for row in rows[:-1]:
        row["metrics"]["return_12m"] = -1
    ranked = rank_entries(rows)
    assert ranked["cash_weight"] == 1
    rows[0]["metrics"]["return_12m"] = None
    assert len(rank_entries(rows)["excluded"]) == 1
    with pytest.raises(ValueError, match="Duplicate"):
        rank_entries(rows + [rows[0]])


def test_snapshot_exact_replay_integrity_and_first_daily_capture_is_immutable(tmp_path):
    original = build_snapshot(inputs(), captured_at="2026-09-24T12:00:00+00:00")
    assert replay_snapshot(original)
    tampered = deepcopy(original)
    tampered["inputs"][0]["metrics"]["latest_price"] = 99
    assert not replay_snapshot(tampered)
    db = tmp_path / "lab.db"
    assert save_snapshot(original, db)
    assert not save_snapshot(original, db)
    changed = build_snapshot(inputs()[1:], captured_at="2026-09-24T14:00:00+00:00")
    assert not save_snapshot(changed, db)
    assert get_snapshots(db) == [original]


def test_costs_benchmark_and_baselines_use_identical_execution_and_universe():
    report = compare_strategies([cohort()])
    result = report["periods"][0]["strategies"]
    assert result[VERSION]["net_return_pct"] == pytest.approx(8.4)
    assert result[VERSION]["excess_vs_net_benchmark_pct"] == pytest.approx(5.5)
    assert result["equal_weight_universe"]["net_return_pct"] == pytest.approx(4.4)
    assert result["SPY"]["net_return_pct"] == pytest.approx(2.9)
    assert not report["promotion_eligible"]
    assert report["drawdown"] is None


def test_missing_unselected_outcome_excludes_whole_date_and_overlap_is_not_counted():
    incomplete = cohort()
    incomplete["inputs"][0]["label"] = None  # Not selected: still prevents survivor bias.
    assert compare_strategies([incomplete])["evaluated_nonoverlapping_cohorts"] == 0
    report = compare_strategies([cohort(), cohort("2025-01-03", "2025-01-06", "2025-02-05"),
                                cohort("2025-02-04", "2025-02-05", "2025-03-06")])
    assert report["evaluated_nonoverlapping_cohorts"] == 2
    assert report["exclusions"]["overlapping_evaluation_window"] == 1
    wrong = cohort()
    wrong["inputs"][0]["label"]["cost_bps"] = 20
    assert compare_strategies([wrong])["evaluated_nonoverlapping_cohorts"] == 0


def test_all_cash_is_zero_return_and_loses_to_rising_benchmark():
    example = cohort()
    for row in example["inputs"]:
        row["metrics"]["latest_price"] = 90
    result = compare_strategies([example])["periods"][0]["strategies"][VERSION]
    assert result["net_return_pct"] == 0
    assert result["exposure"] == 0
    assert result["excess_vs_net_benchmark_pct"] == pytest.approx(-2.9)
    assert result["entry_hit_rate_pct"] is None


def test_new_horizons_append_once_and_removed_tickers_still_receive_outcomes(tmp_path, monkeypatch):
    import pandas as pd
    from src.data.database import add_ticker, get_connection
    from src.research_lab import capture_and_label, prospective_cohorts
    path = tmp_path / "prospective.db"
    old = build_snapshot(inputs(), captured_at="2025-01-01T12:00:00+00:00")
    save_snapshot(old, path)
    add_ticker("NEW", path)  # The old universe is no longer on the current watchlist.
    history = pd.DataFrame({"Close": range(100, 800)}, index=pd.bdate_range("2024-01-01", periods=700))
    requested = []
    def fetch(ticker, **kw):
        requested.append(ticker)
        return history.copy()
    monkeypatch.setattr("src.data.price_cache.fetch_cached_price_history", fetch)
    first = capture_and_label(path)
    second = capture_and_label(path)
    assert first["labels_created"] == 20
    assert second["labels_created"] == 0
    assert "S9" in requested
    with get_connection(path) as con:
        assert con.execute("SELECT COUNT(*) FROM entry_research_outcomes").fetchone()[0] == 20
    cohort = prospective_cohorts(path)[0]
    assert all(r["label"]["outcomes"]["1M"] and r["label"]["outcomes"]["3M"] for r in cohort["inputs"])
    assert get_snapshots(path)[0] == old


def test_context_exposes_coverage_without_turning_missing_families_into_direction():
    from src.research_lab import context_summary
    snapshot = build_snapshot(inputs(), captured_at="2026-09-24T12:00:00+00:00")
    context = context_summary(snapshot)
    assert context["market_above_ma200"] is None
    assert context["coverage"]["option_greeks"] == 0
    assert context["theoretical_sector_exposure_pct"] == {"Unknown": 100.0}
    assert replay_snapshot(snapshot)
