import sqlite3
from datetime import datetime

from src.backup import create_verified_backup, verify_backup_manifest


def test_verified_backup_round_trip(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO sample(value) VALUES ('synthetic')")
    result = create_verified_backup(
        source, tmp_path / "backups", now=datetime(2026, 7, 14, 12, 0),
    )
    verified = verify_backup_manifest(result["manifest_path"])
    assert verified["valid"] is True
    assert verified["integrity"] == "ok"
    with sqlite3.connect(verified["database_path"]) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "synthetic"
