from concurrent.futures import ThreadPoolExecutor
from datetime import date

from src.data import database as db
from src.data import backtest_refresh as refresh


def run(version="v1", day="2023-01-01"):
    return dict(ticker="TEST", as_of_date=day, coverage="price-only", entry_score=60,
                exit_score=20, entry_signal="Watch", exit_signal="Hold / no review",
                technical_score=70, valuation_score=50, risk_score=60, outcome_1m=2,
                inputs_json="{}", model_version=version)


def test_concurrent_retries_are_idempotent_and_revisions_preserve_history(tmp_path):
    path = tmp_path / "projection.db"
    for version in ("v1", "v2"):
        db.save_backtest_run(run(version), path)
    def update(_):
        db.update_backtest_outcomes("TEST", "2023-01-01", {"1M": 3, "3M": 9}, path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(update, range(8)))
    db.update_backtest_outcomes("TEST", "2023-01-01", {"3M": 10}, path)
    with db.get_connection(path) as con:
        assert con.execute("SELECT COUNT(*) FROM legacy_outcome_observations").fetchone()[0] == 4
        assert con.execute("SELECT COUNT(*) FROM latest_legacy_outcomes").fetchone()[0] == 2
        assert con.execute("SELECT SUM(outcome_1m) FROM backtest_runs").fetchone()[0] == 4
    assert [(r["outcome_1m"], r["outcome_3m"]) for r in db.get_backtest_runs(db_path=path)] == [(3, 10)] * 2


def test_migration_and_previous_version_writers_keep_projection_equivalent(tmp_path):
    path = tmp_path / "upgrade.db"
    db.save_backtest_run(run(), path)
    with db.get_connection(path) as con:
        con.executescript("DROP TRIGGER project_latest_legacy_outcome; DROP TABLE latest_legacy_outcomes;")
        con.execute("DELETE FROM schema_migrations WHERE migration_key='latest_legacy_outcomes_v1'")
        con.executemany("INSERT INTO legacy_outcome_observations (ticker,as_of_date,model_version,outcome_3m) VALUES ('TEST','2023-01-01','v1',?)", [(8,), (9,)])
    db._initialized_databases.clear()
    assert db.get_backtest_runs(db_path=path)[0]["outcome_3m"] == 9
    with db.get_connection(path) as con:
        con.execute("INSERT INTO legacy_outcome_observations (ticker,as_of_date,model_version,outcome_3m) VALUES ('TEST','2023-01-01','v1',10)")
    assert db.get_backtest_runs(db_path=path)[0]["outcome_3m"] == 10
    db._initialized_databases.clear()
    db.init_db(path)
    with db.get_connection(path) as con:
        assert con.execute("SELECT COUNT(*) FROM latest_legacy_outcomes").fetchone()[0] == 1


def test_daily_attempt_budget_survives_finished_worker_and_next_day(tmp_path, monkeypatch):
    path = tmp_path / "daily.db"
    db.save_backtest_run(run(), path)
    called = []
    class Done:
        def done(self):
            return True
    class Executor:
        def submit(self, fn, target):
            called.append(target)
            return Done()
    monkeypatch.setattr(refresh, "_executor", Executor())
    monkeypatch.setattr(refresh, "_outcome_future", None)
    assert refresh.schedule_outcome_refresh(path)
    assert not refresh.schedule_outcome_refresh(path)
    assert len(called) == 1
    assert db.daily_refresh_attempted("outcomes", date.today().isoformat(), path)
    assert db.claim_daily_refresh("outcomes", "2099-01-01", path)
    assert not db.claim_daily_refresh("outcomes", "2099-01-01", path)


def test_refresh_groups_versions_and_reuses_price_histories(tmp_path, monkeypatch):
    path = tmp_path / "worker.db"
    for version in ("v1", "v2"):
        for day in ("2023-01-01", "2023-02-01"):
            db.save_backtest_run(run(version, day), path)
    fetched, evaluated = [], []
    import pandas as pd
    prices = pd.DataFrame({"Close": [100.0, 101.0]}, index=pd.to_datetime(["2023-01-02", "2023-01-03"]))
    monkeypatch.setattr(refresh, "fetch_price_history", lambda ticker, **kw: fetched.append(ticker) or prices)
    monkeypatch.setattr(refresh, "evaluate_outcomes", lambda history, day: evaluated.append(day) or {"1M": 3})
    monkeypatch.setattr(refresh, "materialize_matured_prediction_labels", lambda *a, **kw: None)
    refresh._refresh_outcomes(path)
    assert fetched == ["TEST"]
    assert len(evaluated) == 2
