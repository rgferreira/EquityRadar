import sqlite3
from datetime import datetime

from src.backup import create_verified_backup, run_restore_drill, verify_backup_manifest


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
    drill = run_restore_drill(result["manifest_path"])
    assert drill["valid"] is True
    assert drill["row_counts_match"] is True
    assert drill["temporary_copy_removed"] is True


def test_download_includes_uncheckpointed_wal_and_private_permissions(tmp_path):
    from src.backup import sqlite_backup_bytes
    source = tmp_path / "wal.db"
    with sqlite3.connect(source) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA wal_autocheckpoint=0")
        con.execute("CREATE TABLE sample(value TEXT)")
        con.commit()
        con.execute("INSERT INTO sample VALUES ('synthetic WAL record')")
        con.commit()
        downloaded = tmp_path / "download.db"
        downloaded.write_bytes(sqlite_backup_bytes(source))
        with sqlite3.connect(downloaded) as copy:
            assert copy.execute("SELECT value FROM sample").fetchone()[0] == "synthetic WAL record"
        result = create_verified_backup(source, tmp_path / "private")
    from pathlib import Path
    assert (tmp_path / "private").stat().st_mode & 0o777 == 0o700
    assert Path(result["database_path"]).stat().st_mode & 0o777 == 0o600
    assert Path(result["manifest_path"]).stat().st_mode & 0o777 == 0o600
