from datetime import date
import pandas as pd

from src.data.backtest_refresh import materialize_matured_prediction_labels
from src.data.database import get_outcome_labels, save_outcome_label, save_prediction_snapshot
from src.data.outcome_maturation import get_current_outcome_labels
from src.model_registry import build_prediction_snapshot, current_model_registration
from src.outcome_labels import build_relative_outcome_label


def setup_prediction(database):
    snapshot = build_prediction_snapshot(
        ticker="TEST", as_of_date="2026-01-05", model=current_model_registration(),
        inputs={"features": {}, "temporal_coverage": {}, "input_references": {}},
        outputs={"entry_score": 50, "exit_score": 50, "entry_signal": "Watch", "exit_signal": "Hold"})
    save_prediction_snapshot(snapshot, database)
    return snapshot


def history(periods, growth=.001):
    return pd.DataFrame({"Close": [100*(1+growth)**i for i in range(periods)]},
                        index=pd.date_range("2026-01-05", periods=periods, freq="B"))


def test_pending_archive_is_preserved_while_each_horizon_matures(tmp_path):
    db = tmp_path / "outcomes.db"
    p = setup_prediction(db)
    pending = build_relative_outcome_label(prediction_id=p["prediction_id"], ticker="TEST",
        as_of_date=p["as_of_date"], security_history=history(10), benchmark_history=history(10))
    save_outcome_label(pending, db)
    result = materialize_matured_prediction_labels(db, today=date(2026, 3, 1),
        history_fetcher=lambda *a, **k: history(30))
    assert result["horizons_created"] == 1
    first = get_current_outcome_labels(db_path=db)[0]
    assert first["outcomes"]["1M"] is not None
    assert first["outcomes"].get("3M") is None
    original = get_outcome_labels(db_path=db)[0]
    assert original["outcome_hash"] == pending["outcome_hash"]
    assert original["status"] == "pending"
    materialize_matured_prediction_labels(db, today=date(2026, 6, 1),
        history_fetcher=lambda *a, **k: history(90, .002))
    final = get_current_outcome_labels(db_path=db)[0]
    assert final["outcomes"]["1M"] == first["outcomes"]["1M"]
    assert final["horizon_provenance"]["1M"] == first["horizon_provenance"]["1M"]
    assert final["outcomes"]["3M"] is not None
    assert final["horizon_provenance"]["1M"]["security_entry_price"] != final["horizon_provenance"]["3M"]["security_entry_price"]
    assert get_outcome_labels(db_path=db)[0]["outcome_hash"] == pending["outcome_hash"]
    again = materialize_matured_prediction_labels(db, today=date(2026, 6, 1),
        history_fetcher=lambda *a, **k: history(90, .003))
    assert again["created"] == 0
    assert get_current_outcome_labels(db_path=db)[0]["outcome_hash"] == final["outcome_hash"]


def test_one_month_live_outcomes_do_not_wait_for_three_months_or_freeze_intraday(tmp_path):
    db = tmp_path / "live.db"
    setup_prediction(db)
    prices = history(23)  # next-session entry at index 1; 1M end at index 22
    day = prices.index[-1].date()
    fetch = lambda *a, **k: prices
    materialize_matured_prediction_labels(db, today=day, history_fetcher=fetch)
    assert get_current_outcome_labels(db_path=db) == []
    from datetime import timedelta
    result = materialize_matured_prediction_labels(db, today=day+timedelta(days=1), history_fetcher=fetch)
    assert result["horizons_created"] == 1
    label = get_current_outcome_labels(db_path=db)[0]
    assert label["outcomes"]["1M"]["end_date"] == day.isoformat()
    assert get_outcome_labels(db_path=db) == []  # immutable archive has no partial new label


def test_failed_history_is_cached_and_remains_missing(tmp_path):
    db = tmp_path / "failure.db"
    setup_prediction(db)
    calls = []
    def fetch(ticker, **kwargs):
        calls.append(ticker)
        raise RuntimeError("synthetic outage")
    result = materialize_matured_prediction_labels(db, today=date(2026, 6, 1), history_fetcher=fetch)
    assert result["failed"] == 1
    assert get_current_outcome_labels(db_path=db) == []
