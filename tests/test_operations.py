from datetime import datetime

from src.data.database import add_ticker, init_db, record_provider_health, save_positioning_snapshot
from src.operations import (
    get_operation_runs, provider_health, run_due_maintenance, short_interest_evidence_health,
)


def test_provider_health_preserves_missing_as_missing(tmp_path):
    database = tmp_path / "health.db"
    init_db(database)
    rows = provider_health(database, now=datetime(2026, 7, 14, 12, 0))
    assert {row["status"] for row in rows} == {"Missing"}


def test_provider_health_exposes_isolated_failure_and_cooldown(tmp_path):
    database = tmp_path / "health-failure.db"
    init_db(database)
    record_provider_health(
        "market_price", "AAA", "failed", error="synthetic outage",
        cooldown_until="2026-07-14T12:15:00", db_path=database,
    )
    rows = provider_health(database, now=datetime(2026, 7, 14, 12, 0))
    operational = next(row for row in rows if row["source"] == "Market Price operations")
    assert operational["status"] == "Failed"
    assert operational["last_error"] == "synthetic outage"
    assert operational["cooldown"] == "2026-07-14T12:15:00"


def test_finra_health_ignores_unsupported_instrument_failure(tmp_path):
    database = tmp_path / "health-finra.db"
    init_db(database)
    record_provider_health("finra", "MU", "healthy", db_path=database)
    record_provider_health(
        "finra", "BTC-USD", "failed", error="synthetic unsupported response",
        db_path=database,
    )

    rows = provider_health(database, now=datetime.now())
    operational = next(row for row in rows if row["source"] == "Finra operations")

    assert operational["status"] == "Healthy"
    assert operational["records"] == 1
    assert operational["last_error"] is None


def test_operations_uses_report_date_not_fetch_date_for_short_freshness(tmp_path):
    database = tmp_path / "health-short.db"
    add_ticker("MU", database)
    payload = {
        "reporting_date": "2026-05-31",
        "short": {"shares_short": 100, "short_change_pct": 5},
    }
    save_positioning_snapshot(
        "MU", payload, "synthetic", "2026-05-31", "2026-07-15T09:00:00", database,
    )
    row = short_interest_evidence_health(database, now=datetime(2026, 7, 15, 12, 0))[0]
    assert row["status"] == "Stale — excluded"
    assert row["report_age_days"] == 45
    assert row["used_in_scores"] == "No"


def test_operations_marks_crypto_short_interest_not_applicable(tmp_path):
    database = tmp_path / "health-short-crypto.db"
    add_ticker("BTC-USD", database)

    row = short_interest_evidence_health(database, now=datetime(2026, 7, 15, 12, 0))[0]

    assert row["status"] == "Not applicable"
    assert row["used_in_scores"] == "No"
    assert "does not cover" in row["reason"]


def test_due_maintenance_records_verified_backup(tmp_path, monkeypatch):
    database = tmp_path / "operations.db"
    init_db(database)
    monkeypatch.setattr("src.data.industry_refresh.schedule_industry_refresh", lambda *a, **k: [])
    monkeypatch.setattr("src.data.positioning_refresh.schedule_positioning_refresh", lambda *a, **k: [])
    monkeypatch.setattr("src.data.extended_hours_refresh.schedule_extended_hours_refresh", lambda *a, **k: [])
    monkeypatch.setattr("src.data.backtest_refresh.schedule_outcome_refresh", lambda *a, **k: False)
    monkeypatch.setattr("src.data.cutoff_suggestions.schedule_cutoff_suggestions", lambda *a, **k: False)

    def backup_runner(**_kwargs):
        return {"manifest_path": "synthetic.manifest.json", "sha256": "abc"}

    run_due_maintenance(
        database, now=datetime(2026, 7, 14, 12, 0), backup_runner=backup_runner,
    )
    runs = {row["operation_key"]: row for row in get_operation_runs(database)}
    assert runs["scheduled_refresh"]["status"] == "completed"
    assert runs["verified_backup"]["status"] == "completed"
