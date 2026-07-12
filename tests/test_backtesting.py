from datetime import date

import pandas as pd

from src.backtesting import (
    evaluate_outcomes, evidence_available, history_as_of, learned_score_adjustments,
    lesson_summary, reconstruct_signal,
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


def test_outcomes_are_measured_after_cutoff():
    outcomes = evaluate_outcomes(sample_history(), "2023-06-01")
    assert outcomes["3M"] > outcomes["1M"]


def test_learning_requires_sample_and_is_bounded():
    rows = [{"outcome_3m": 10.0}] * 3
    learned = learned_score_adjustments(rows)
    assert 0 < learned["entry_adjustment"] <= 5
    assert learned["exit_adjustment"] == -learned["entry_adjustment"]
    assert learned_score_adjustments(rows[:2])["entry_adjustment"] == 0


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
