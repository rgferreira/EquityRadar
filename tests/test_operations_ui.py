"""Synthetic interaction coverage for the complete Operations console."""

from __future__ import annotations

import json
from datetime import datetime

from streamlit.testing.v1 import AppTest

from src.backup import create_verified_backup
from src.data.database import (
    add_ticker, get_connection, get_research_alerts, init_db,
    record_provider_health, save_positioning_snapshot, save_research_alerts,
)


def _isolate_operations_database(tmp_path, monkeypatch):
    database = tmp_path / "operations-ui.db"
    init_db(database)
    for target in (
        "src.data.database.DATABASE_PATH", "src.utils.config.DATABASE_PATH",
        "src.operations.DATABASE_PATH", "src.backup.DATABASE_PATH",
    ):
        monkeypatch.setattr(target, database)
    return database


def _button(app: AppTest, label: str):
    matches = [button for button in app.button if button.label == label]
    assert len(matches) == 1
    return matches[0]


def test_operations_empty_state_renders_every_control_group(tmp_path, monkeypatch):
    _isolate_operations_database(tmp_path, monkeypatch)

    app = AppTest.from_file("pages/6_Operations.py", default_timeout=20).run()

    assert not app.exception
    assert [title.value for title in app.title] == ["Operations"]
    headings = {heading.value for heading in app.subheader}
    assert headings == {
        "Provider health", "Short-interest evidence freshness", "Background maintenance",
        "Verified local recovery", "Options evidence continuity", "Research alerts",
    }
    assert _button(app, "Verify existing backup").disabled
    assert _button(app, "Run isolated restore drill").disabled


def test_operations_degraded_provider_and_stale_finra_are_visible(tmp_path, monkeypatch):
    database = _isolate_operations_database(tmp_path, monkeypatch)
    add_ticker("MU", database)
    record_provider_health(
        "market_price", "MU", "failed", error="synthetic outage",
        cooldown_until="2026-07-21T12:15:00", db_path=database,
    )
    save_positioning_snapshot(
        "MU",
        {"reporting_date": "2026-05-31", "short": {"shares_short": 100}},
        "synthetic", "2026-05-31", "2026-07-21T09:00:00", database,
    )

    app = AppTest.from_file("pages/6_Operations.py", default_timeout=20).run()

    assert not app.exception
    rendered = "\n".join(table.value.to_string() for table in app.dataframe)
    assert "Market Price operations" in rendered
    assert "synthetic outage" in rendered
    assert "Stale — excluded" in rendered


def test_operations_manual_maintenance_reports_queued_count(tmp_path, monkeypatch):
    _isolate_operations_database(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "src.operations.run_due_maintenance",
        lambda: {"refresh_scheduled": ["synthetic-a", "synthetic-b"], "backup": None},
    )

    app = AppTest.from_file("pages/6_Operations.py", default_timeout=20).run()
    _button(app, "Run due maintenance now").click().run()

    assert not app.exception
    assert any("2 provider refresh(es) queued" in success.value for success in app.success)


def test_operations_manual_maintenance_failure_is_isolated(tmp_path, monkeypatch):
    _isolate_operations_database(tmp_path, monkeypatch)

    def fail_maintenance():
        raise RuntimeError("synthetic maintenance failure")

    monkeypatch.setattr("src.operations.run_due_maintenance", fail_maintenance)
    app = AppTest.from_file("pages/6_Operations.py", default_timeout=20).run()
    _button(app, "Run due maintenance now").click().run()

    assert not app.exception
    assert any("Existing cached research data remains available" in error.value for error in app.error)


def test_operations_verifies_backup_and_runs_isolated_restore(tmp_path, monkeypatch):
    database = _isolate_operations_database(tmp_path, monkeypatch)
    backup = create_verified_backup(
        database, tmp_path / "backups", now=datetime(2026, 7, 21, 12, 0),
    )

    app = AppTest.from_file("pages/6_Operations.py", default_timeout=20).run()
    manifest = next(item for item in app.text_input if item.label == "Manifest path")
    manifest.set_value(backup["manifest_path"]).run()
    _button(app, "Verify existing backup").click().run()
    assert any("Backup and manifest are valid" in success.value for success in app.success)

    _button(app, "Run isolated restore drill").click().run()
    assert not app.exception
    assert any("Restore drill passed" in success.value for success in app.success)


def test_operations_create_backup_reports_verified_artifact(tmp_path, monkeypatch):
    _isolate_operations_database(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "src.backup.create_verified_backup",
        lambda: {"database_file": "synthetic-backup.db", "sha256": "abc123"},
    )

    app = AppTest.from_file("pages/6_Operations.py", default_timeout=20).run()
    _button(app, "Create verified backup").click().run()

    assert not app.exception
    assert any("synthetic-backup.db" in success.value for success in app.success)
    assert any("abc123" in code.value for code in app.code)


def test_operations_invalid_manifest_does_not_break_page(tmp_path, monkeypatch):
    _isolate_operations_database(tmp_path, monkeypatch)
    app = AppTest.from_file("pages/6_Operations.py", default_timeout=20).run()
    manifest = next(item for item in app.text_input if item.label == "Manifest path")
    manifest.set_value(str(tmp_path / "missing.manifest.json")).run()

    _button(app, "Verify existing backup").click().run()
    assert not app.exception
    assert any("verification could not be completed" in error.value for error in app.error)

    _button(app, "Run isolated restore drill").click().run()
    assert not app.exception
    assert any("live database was never touched" in error.value for error in app.error)


def test_operations_malformed_legacy_detail_is_rendered_safely(tmp_path, monkeypatch):
    database = _isolate_operations_database(tmp_path, monkeypatch)
    with get_connection(database) as connection:
        connection.execute(
            """INSERT INTO operation_runs
               (operation_key,status,detail_json,updated_at)
               VALUES ('legacy-operation','completed','not-json','2026-07-21T12:00:00')"""
        )

    app = AppTest.from_file("pages/6_Operations.py", default_timeout=20).run()

    assert not app.exception
    rendered = "\n".join(table.value.to_string() for table in app.dataframe)
    assert "Unavailable legacy detail" in rendered


def test_operations_acknowledges_research_alert(tmp_path, monkeypatch):
    database = _isolate_operations_database(tmp_path, monkeypatch)
    alert = {
        "alert_id": "synthetic-alert", "ticker": "AAA", "alert_type": "diagnostic_change",
        "severity": "attention", "title": "AAA diagnostic changed",
        "detail": "Synthetic research-only transition", "evidence_date": "2026-07-21",
        "evidence_json": json.dumps({"synthetic": True}),
    }
    save_research_alerts([alert], database)

    app = AppTest.from_file("pages/6_Operations.py", default_timeout=20).run()
    _button(app, "Acknowledge").click().run()

    assert not app.exception
    assert get_research_alerts(db_path=database) == []
    acknowledged = get_research_alerts(include_acknowledged=True, db_path=database)
    assert acknowledged[0]["acknowledged_at"] is not None
