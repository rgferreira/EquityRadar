import pandas as pd
import pytest
from datetime import date

from src.data.database import get_outcome_labels, save_outcome_label, save_prediction_snapshot
from src.model_registry import build_prediction_snapshot, current_model_registration
from src.data.backtest_refresh import materialize_matured_prediction_labels
from src.outcome_labels import (
    RELATIVE_LABEL_VERSION, TOTAL_COST_BPS, benchmark_for_ticker,
    build_relative_outcome_label,
)


def histories(security_growth=0.002, benchmark_growth=0.001, periods=150):
    dates = pd.date_range("2026-01-02", periods=periods, freq="B")
    security = pd.DataFrame(
        {"Close": [100 * (1 + security_growth) ** index for index in range(periods)]}, index=dates,
    )
    benchmark = pd.DataFrame(
        {"Close": [200 * (1 + benchmark_growth) ** index for index in range(periods)]}, index=dates,
    )
    return security, benchmark


def test_relative_outcomes_separate_security_selection_from_rising_market():
    security, benchmark = histories()
    label = build_relative_outcome_label(
        prediction_id="p1", ticker="TEST", as_of_date="2026-01-09",
        security_history=security, benchmark_history=benchmark,
    )
    one_month = label["outcomes"]["1M"]
    assert label["label_version"] == RELATIVE_LABEL_VERSION
    assert label["benchmark_ticker"] == "SPY"
    assert one_month["security_return_pct"] > one_month["benchmark_return_pct"] > 0
    assert one_month["relative_return_after_cost_pct"] == pytest.approx(
        one_month["relative_return_before_cost_pct"] - TOTAL_COST_BPS / 100, abs=1e-6,
    )


def test_weekend_cutoff_executes_on_next_common_session_and_horizons_are_exact():
    security, benchmark = histories()
    label = build_relative_outcome_label(
        prediction_id="p2", ticker="TEST", as_of_date="2026-01-10",
        security_history=security, benchmark_history=benchmark,
    )
    assert label["execution_date"] == "2026-01-12"
    common_dates = security.index[security.index > pd.Timestamp("2026-01-10")]
    assert label["outcomes"]["1M"]["end_date"] == common_dates[21].date().isoformat()


def test_cost_is_applied_once_when_asset_and_benchmark_are_flat():
    security, benchmark = histories(0, 0)
    label = build_relative_outcome_label(
        prediction_id="p3", ticker="TEST", as_of_date="2026-01-05",
        security_history=security, benchmark_history=benchmark,
    )
    assert label["outcomes"]["1M"]["relative_return_after_cost_pct"] == -0.1
    assert label["outcomes"]["6M"]["relative_return_after_cost_pct"] == -0.1


def test_missing_or_unverified_benchmark_is_unavailable_not_directional():
    security, _ = histories()
    missing = build_relative_outcome_label(
        prediction_id="p4", ticker="TEST", as_of_date="2026-01-05",
        security_history=security, benchmark_history=None,
    )
    crypto = build_relative_outcome_label(
        prediction_id="p5", ticker="BTC-USD", as_of_date="2026-01-05",
        security_history=security, benchmark_history=None,
    )
    assert missing["status"] == "unavailable"
    assert missing["outcomes"] == {}
    assert crypto["unavailable_reason"] == "no_verified_benchmark_mapping"
    assert benchmark_for_ticker("BTC-USD") is None


def test_downside_and_immature_horizon_boundaries():
    dates = pd.date_range("2026-01-02", periods=130, freq="B")
    prices = [100.0] * 10 + [80.0] + [90.0] * 119
    security = pd.DataFrame({"Close": prices}, index=dates)
    benchmark = pd.DataFrame({"Close": [100.0] * 130}, index=dates)
    label = build_relative_outcome_label(
        prediction_id="p6", ticker="TEST", as_of_date="2026-01-02",
        security_history=security, benchmark_history=benchmark,
    )
    assert label["max_drawdown_6m_pct"] == -20.0
    assert label["outcomes"]["6M"] is not None

    pending = build_relative_outcome_label(
        prediction_id="p7", ticker="TEST", as_of_date="2026-06-01",
        security_history=security.iloc[:110], benchmark_history=benchmark.iloc[:110],
    )
    assert pending["outcomes"]["6M"] is None


def test_outcome_label_storage_is_idempotent_and_immutable(tmp_path):
    database = tmp_path / "labels.db"
    model = current_model_registration()
    snapshot = build_prediction_snapshot(
        ticker="TEST", as_of_date="2026-01-05", model=model,
        inputs={"features": {}, "temporal_coverage": {}, "input_references": {}},
        outputs={"entry_score": 50, "exit_score": 50, "entry_signal": "Watch", "exit_signal": "Hold / no review"},
    )
    save_prediction_snapshot(snapshot, database)
    security, benchmark = histories()
    label = build_relative_outcome_label(
        prediction_id=snapshot["prediction_id"], ticker="TEST", as_of_date="2026-01-05",
        security_history=security, benchmark_history=benchmark,
    )
    save_outcome_label(label, database)
    save_outcome_label(label, database)
    assert len(get_outcome_labels(prediction_id=snapshot["prediction_id"], db_path=database)) == 1
    with pytest.raises(ValueError, match="Immutable outcome label conflict"):
        save_outcome_label({**label, "outcome_hash": "different"}, database)


def test_matured_prediction_label_is_materialized_without_persisting_pending_state(tmp_path):
    database = tmp_path / "materialize.db"
    model = current_model_registration()
    snapshot = build_prediction_snapshot(
        ticker="TEST", as_of_date="2026-01-05", model=model,
        inputs={"features": {}, "temporal_coverage": {}, "input_references": {}},
        outputs={"entry_score": 50, "exit_score": 50, "entry_signal": "Watch", "exit_signal": "Hold / no review"},
    )
    save_prediction_snapshot(snapshot, database)
    security, benchmark = histories(periods=170)

    def fetcher(ticker, period="max"):
        return benchmark if ticker == "SPY" else security

    result = materialize_matured_prediction_labels(
        database, today=date(2026, 7, 17), history_fetcher=fetcher,
    )

    assert result["created"] == 1
    stored = get_outcome_labels(prediction_id=snapshot["prediction_id"], db_path=database)
    assert stored[0]["outcomes"]["3M"] is not None
