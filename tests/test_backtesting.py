from datetime import date

import pandas as pd

from src.backtesting import (
    decision_accuracy_history, decision_outcome, diagnostic_success_rate, evaluate_outcomes, evidence_available, history_as_of, learned_score_adjustments,
    latest_model_runs, lesson_summary, reconstruct_signal, select_learning_observations,
)
from src.data.database import (
    get_backtest_job_items, get_backtest_runs, init_db, save_backtest_run, set_backtest_job_item,
    update_backtest_outcomes,
)
from src.data.backtest_refresh import ticker_backfill_status


def sample_history(days=400):
    index = pd.date_range("2023-01-02", periods=days, freq="B")
    return pd.DataFrame({"Close": [100 + i * .25 for i in range(days)]}, index=index)


def test_history_cutoff_excludes_future_prices():
    cutoff = date(2023, 6, 1)
    sliced = history_as_of(sample_history(), cutoff)
    assert sliced.index.max().date() <= cutoff


def test_reconstruction_does_not_use_later_fundamentals():
    fundamentals = {"trailing_pe": 10, "reporting_date": "2025-01-01", "fetched_at": "2025-01-02"}
    result = reconstruct_signal(sample_history(), "2023-12-01", fundamentals)
    assert result["fundamentals_used"] is False
    assert evidence_available(fundamentals, "2023-12-01") is False


def test_reconstruction_uses_only_finra_rows_available_by_cutoff():
    positioning = [
        {"reporting_date": "2023-06-30", "known_at": "2023-07-12T12:00:00+00:00",
         "known_at_status": "verified_observed", "snapshot_type": "historical_short_interest",
         "short": {"shares_short": 100, "short_change_pct": 5, "days_to_cover": 2}},
        {"reporting_date": "2024-01-31", "known_at": "2024-02-12T12:00:00+00:00",
         "known_at_status": "verified_observed", "snapshot_type": "historical_short_interest",
         "short": {"shares_short": 300, "short_change_pct": 200, "days_to_cover": 8}},
    ]
    result = reconstruct_signal(sample_history(), "2023-07-20", positioning_history=positioning)
    assert result["finra_observations_used"] == 1
    assert result["positioning_modifier"]["history_points"] == 1
    assert "FINRA" in result["coverage"]
    assert result["temporal_coverage"]["finra"] == "verified_known_at"


def test_legacy_dates_never_establish_historical_availability():
    legacy = {
        "reporting_date": "2023-01-01", "fetched_at": "2023-01-02T09:00:00",
        "trailing_pe": 10,
    }

    assert evidence_available(legacy, "2026-01-01") is False


def test_unverified_evidence_is_reported_without_breaking_price_reconstruction():
    result = reconstruct_signal(
        sample_history(), "2023-12-01",
        fundamentals={"trailing_pe": 10, "reporting_date": "2023-01-01"},
        positioning_history=[{
            "reporting_date": "2023-06-30", "snapshot_type": "historical_short_interest",
            "short": {"shares_short": 100},
        }],
    )

    assert result["coverage"] == "Price-only reconstruction"
    assert result["fundamentals_used"] is False
    assert result["finra_observations_used"] == 0
    assert result["temporal_coverage"] == {
        "price": "end_of_day_cutoff",
        "fundamentals": "unverified_or_after_cutoff",
        "finra": "unverified_or_after_cutoff",
        "technology_potential": "missing",
        "daily_short_flow": "missing",
    }


def test_outcomes_are_measured_after_cutoff():
    outcomes = evaluate_outcomes(sample_history(), "2023-06-01")
    assert outcomes["3M"] > outcomes["1M"]


def test_learning_requires_sample_and_is_bounded():
    rows = [
        {"as_of_date": f"2025-0{index + 1}-01", "entry_signal": "Wait", "entry_score": 40 + index * 5,
         "outcome_1m": 4 + index, "outcome_3m": 9 + index * 3, "outcome_6m": 12 + index * 4}
        for index in range(3)
    ]
    learned = learned_score_adjustments(rows)
    assert 0 < learned["entry_adjustment"] <= 5
    assert learned["exit_adjustment"] == -learned["entry_adjustment"]
    assert learned_score_adjustments(rows[:2])["entry_adjustment"] == 0


def test_wait_followed_by_gain_is_a_missed_opportunity():
    result = decision_outcome({"entry_signal": "Wait", "entry_score": 46,
                               "outcome_1m": 3, "outcome_3m": 6, "outcome_6m": 12})
    assert result["verdict"] == "Missed opportunity"
    assert result["decision_utility"] < 0
    assert result["should_learn"] is True
    assert result["coverage"] == 1.0


def test_buy_followed_by_decline_is_an_unfavorable_entry():
    result = decision_outcome({"entry_signal": "Buy candidate", "entry_score": 75,
                               "outcome_1m": -3, "outcome_3m": -6, "outcome_6m": -12})
    assert result["verdict"] == "Unfavorable entry"
    assert result["decision_utility"] < 0


def test_one_month_only_outcome_is_provisional_and_does_not_change_learning():
    result = decision_outcome({"entry_signal": "Buy candidate", "entry_score": 75,
                               "outcome_1m": -8, "outcome_3m": None, "outcome_6m": None})
    assert result["maturity"] == "Provisional"
    assert result["should_evaluate"] is True
    assert result["should_learn"] is False


def test_pending_outcomes_are_provisional_and_safe_for_evaluation_selection():
    run = {"as_of_date": "2026-07-13", "entry_signal": "Watch", "entry_score": 60,
           "outcome_1m": None, "outcome_3m": None, "outcome_6m": None}

    result = decision_outcome(run)

    assert result["maturity"] == "Provisional"
    assert result["should_evaluate"] is False
    assert result["should_learn"] is False
    assert select_learning_observations([run], confirmed_only=False) == []


def test_watch_tolerates_modest_upside_but_not_a_large_missed_move():
    modest = decision_outcome({"entry_signal": "Watch", "entry_score": 65,
                               "outcome_1m": 1, "outcome_3m": 3, "outcome_6m": 6})
    large = decision_outcome({"entry_signal": "Watch", "entry_score": 65,
                              "outcome_1m": 8, "outcome_3m": 24, "outcome_6m": 48})
    assert modest["verdict"] == "Correct watch"
    assert modest["decision_utility"] > 0
    assert large["verdict"] == "Missed opportunity"
    assert large["decision_utility"] < 0


def test_learning_gate_skips_immature_noise_and_near_duplicates():
    runs = [
        {"as_of_date": "2025-01-01", "entry_signal": "Wait", "entry_score": 46,
         "outcome_1m": .1, "outcome_3m": None, "outcome_6m": None},
        {"as_of_date": "2025-02-01", "entry_signal": "Wait", "entry_score": 46,
         "outcome_1m": 4, "outcome_3m": 9, "outcome_6m": 12},
        {"as_of_date": "2025-03-01", "entry_signal": "Wait", "entry_score": 47,
         "outcome_1m": 4.1, "outcome_3m": 9.2, "outcome_6m": 12.2},
    ]
    selected = select_learning_observations(runs)
    assert len(selected) == 1
    assert selected[0]["as_of_date"] == "2025-02-01"


def test_learning_collapses_nearby_same_signal_into_one_episode():
    runs = [{"as_of_date": day, "entry_signal": "Wait", "entry_score": score,
             "outcome_1m": 4, "outcome_3m": 12, "outcome_6m": 24}
            for day, score in (("2025-01-01", 35), ("2025-01-08", 45), ("2025-02-01", 45))]
    selected = select_learning_observations(runs)
    assert [row["as_of_date"] for row in selected] == ["2025-01-01", "2025-02-01"]


def test_accuracy_history_is_cumulative_and_uses_confirmed_episodes_only():
    runs = [
        {"as_of_date": "2025-01-01", "entry_signal": "Buy candidate", "entry_score": 75,
         "outcome_1m": 2, "outcome_3m": 6, "outcome_6m": 12},
        {"as_of_date": "2025-02-01", "entry_signal": "Wait", "entry_score": 45,
         "outcome_1m": 3, "outcome_3m": 9, "outcome_6m": 18},
        {"as_of_date": "2025-03-01", "entry_signal": "Buy candidate", "entry_score": 75,
         "outcome_1m": -5, "outcome_3m": None, "outcome_6m": None},
    ]
    history = decision_accuracy_history(runs)
    assert [row["accuracy"] for row in history] == [100.0, 50.0]
    assert history[-1]["correct_decisions"] == 1
    assert history[-1]["episodes"] == 2


def test_latest_model_runs_prevents_duplicate_rows_after_recalculation():
    rows = [
        {"id": 9, "ticker": "TEST", "as_of_date": "2025-01-01", "model_version": "zzzz-unregistered", "model_is_active": 0},
        {"id": 2, "ticker": "TEST", "as_of_date": "2025-01-01", "model_version": "active-v1", "model_is_active": 1},
        {"id": 3, "ticker": "OTHER", "as_of_date": "2025-01-01", "model_version": "active-v1", "model_is_active": 1},
    ]
    latest = latest_model_runs(rows)
    assert len(latest) == 2
    assert next(row for row in latest if row["ticker"] == "TEST")["model_version"] == "active-v1"


def test_exact_diagnostic_success_is_sample_aware_for_entry_and_exit():
    runs = [{
        "as_of_date": f"2025-0{index + 1}-01", "entry_signal": "Buy candidate",
        "exit_signal": "Sell review", "entry_score": 75 + index,
        "outcome_1m": value, "outcome_3m": value * 3, "outcome_6m": value * 6,
    } for index, value in enumerate((2.0, 1.5, -1.0))]
    entry = diagnostic_success_rate(runs, "Buy candidate", "entry")
    exit_review = diagnostic_success_rate(runs, "Sell review", "exit")
    assert entry["success_rate"] == 66.7
    assert exit_review["success_rate"] == 33.3
    assert diagnostic_success_rate(runs[:2], "Buy candidate")["success_rate"] is None


def test_backtest_persistence_and_lessons(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    run = {"ticker": "TEST", "as_of_date": "2023-01-01", "coverage": "Price-only reconstruction",
           "entry_score": 60, "exit_score": 20, "entry_signal": "Watch", "exit_signal": "Hold / no review",
           "technical_score": 70, "valuation_score": 50, "risk_score": 60, "outcome_1m": 2,
           "outcome_3m": 8, "outcome_6m": 12, "outcome_12m": 20, "inputs_json": "{}",
           "model_version": "backtested-learning-v1"}
    save_backtest_run(run, db)
    rows = get_backtest_runs("TEST", db)
    assert len(rows) == 1
    assert lesson_summary(rows)["win_rate"] == 100.0
    update_backtest_outcomes("TEST", "2023-01-01", {"1M": 3, "3M": 9, "6M": 14, "12M": 25}, db)
    refreshed = get_backtest_runs("TEST", db)[0]
    assert refreshed["outcome_3m"] == 9
    assert refreshed["outcome_refreshed_at"] is not None
    from src.data.database import get_connection
    with get_connection(db) as connection:
        original = connection.execute(
            "SELECT outcome_3m, outcome_refreshed_at FROM backtest_runs WHERE ticker='TEST'"
        ).fetchone()
        observations = connection.execute("SELECT COUNT(*) FROM legacy_outcome_observations").fetchone()[0]
    assert original["outcome_3m"] == 8
    assert original["outcome_refreshed_at"] is None
    assert observations == 1
    assert refreshed["simulation_source"] == "manual"
    save_backtest_run({**run, "as_of_date": "2023-02-01", "simulation_source": "suggested",
                       "suggestion_rationale": "Market regime transition"}, db)
    suggested = next(row for row in get_backtest_runs("TEST", db) if row["as_of_date"] == "2023-02-01")
    assert suggested["simulation_source"] == "suggested"
    assert suggested["suggestion_rationale"] == "Market regime transition"


def test_backtest_score_inputs_are_not_rewritten_for_same_model_identity(tmp_path):
    db = tmp_path / "immutable-compatibility.db"
    run = {"ticker": "TEST", "as_of_date": "2023-01-01", "coverage": "Price-only reconstruction",
           "entry_score": 60, "exit_score": 20, "entry_signal": "Watch", "exit_signal": "Hold / no review",
           "technical_score": 70, "valuation_score": 50, "risk_score": 60, "outcome_1m": 2,
           "outcome_3m": 8, "outcome_6m": 12, "outcome_12m": 20, "inputs_json": "{}",
           "model_version": "legacy-test-v1"}
    save_backtest_run(run, db)
    save_backtest_run({**run, "entry_score": 99, "inputs_json": '{"changed":true}'}, db)

    stored = get_backtest_runs("TEST", db)[0]
    assert stored["entry_score"] == 60
    assert stored["inputs_json"] == "{}"


def test_backtest_job_state_is_persisted(tmp_path):
    db = tmp_path / "jobs.db"
    set_backtest_job_item("2024-05-08", "TEST", "queued", db_path=db)
    set_backtest_job_item("2024-05-08", "TEST", "running", db_path=db)
    items = get_backtest_job_items("2024-05-08", db)
    assert items[0]["status"] == "running"
    set_backtest_job_item("2024-05-08", "TEST", "failed", "provider unavailable", db)
    failed = get_backtest_job_items("2024-05-08", db)[0]
    assert failed["error"] == "provider unavailable"


def test_ticker_backfill_status_covers_saved_dates(tmp_path):
    db = tmp_path / "coverage.db"
    base = {"ticker": "OLD", "coverage": "Price-only reconstruction", "entry_score": 50,
            "exit_score": 50, "entry_signal": "Watch", "exit_signal": "Reassess",
            "technical_score": 50, "valuation_score": 50, "risk_score": 50,
            "outcome_1m": 1, "outcome_3m": 2, "outcome_6m": 3, "outcome_12m": 4,
            "inputs_json": "{}", "model_version": "backtested-learning-v1"}
    for cutoff in ("2026-01-30", "2026-02-27"):
        save_backtest_run({**base, "as_of_date": cutoff}, db)
    set_backtest_job_item("2026-01-30", "NEW", "completed", db_path=db)
    set_backtest_job_item("2026-02-27", "NEW", "failed", "insufficient history", db)
    status = ticker_backfill_status("NEW", db)
    assert status["total"] == 2
    assert status["failed"] == 1
