from datetime import datetime

from src.data.database import init_db
from src.operations import get_operation_runs, provider_health, run_due_maintenance


def test_provider_health_preserves_missing_as_missing(tmp_path):
    database = tmp_path / "health.db"
    init_db(database)
    rows = provider_health(database, now=datetime(2026, 7, 14, 12, 0))
    assert {row["status"] for row in rows} == {"Missing"}


def test_due_maintenance_records_verified_backup(tmp_path, monkeypatch):
    database = tmp_path / "operations.db"
    init_db(database)
    monkeypatch.setattr("src.data.industry_refresh.schedule_industry_refresh", lambda *a, **k: [])
    monkeypatch.setattr("src.data.positioning_refresh.schedule_positioning_refresh", lambda *a, **k: [])
    monkeypatch.setattr("src.data.extended_hours_refresh.schedule_extended_hours_refresh", lambda *a, **k: [])

    def backup_runner(**_kwargs):
        return {"manifest_path": "synthetic.manifest.json", "sha256": "abc"}

    run_due_maintenance(
        database, now=datetime(2026, 7, 14, 12, 0), backup_runner=backup_runner,
    )
    runs = {row["operation_key"]: row for row in get_operation_runs(database)}
    assert runs["scheduled_refresh"]["status"] == "completed"
    assert runs["verified_backup"]["status"] == "completed"
