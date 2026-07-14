"""Consistent, verifiable local SQLite backups."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from src.utils.config import DATABASE_PATH, PROJECT_ROOT


DEFAULT_BACKUP_DIR = PROJECT_ROOT / "work" / "backups"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sqlite_backup(path: str | Path) -> dict[str, object]:
    """Run SQLite integrity checks and return a privacy-safe schema summary."""
    candidate = Path(path)
    with sqlite3.connect(candidate) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        tables = [
            str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    return {
        "integrity": integrity,
        "tables": tables,
        "table_count": len(tables),
        "user_version": user_version,
        "size_bytes": candidate.stat().st_size,
        "sha256": _sha256(candidate),
    }


def create_verified_backup(
    source: str | Path = DATABASE_PATH, destination_dir: str | Path = DEFAULT_BACKUP_DIR,
    *, now: datetime | None = None,
) -> dict[str, object]:
    """Use SQLite's online backup API, then write a checksum manifest."""
    timestamp = now or datetime.now()
    destination = Path(destination_dir)
    destination.mkdir(parents=True, exist_ok=True)
    backup_path = destination / f"equity-radar-{timestamp:%Y%m%d-%H%M%S}.db"
    with sqlite3.connect(source) as live, sqlite3.connect(backup_path) as backup:
        live.backup(backup)
    verification = verify_sqlite_backup(backup_path)
    if verification["integrity"] != "ok":
        backup_path.unlink(missing_ok=True)
        raise RuntimeError("Backup failed SQLite integrity verification")
    manifest = {
        "format_version": 1,
        "created_at": timestamp.isoformat(timespec="seconds"),
        "database_file": backup_path.name,
        **verification,
    }
    manifest_path = backup_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"database_path": str(backup_path), "manifest_path": str(manifest_path), **manifest}


def verify_backup_manifest(manifest_path: str | Path) -> dict[str, object]:
    """Verify a backup against its persisted manifest without restoring live data."""
    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    database_path = manifest_file.parent / str(manifest["database_file"])
    verification = verify_sqlite_backup(database_path)
    return {
        "valid": verification["integrity"] == "ok" and verification["sha256"] == manifest["sha256"],
        "database_path": str(database_path),
        **verification,
    }
