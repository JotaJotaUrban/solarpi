"""Full SQLite snapshots, independent of the one-off SD recovery process."""
from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path

from .store import SnapshotStore


def copy_database(source: Path, target: Path) -> None:
    """SQLite backup includes committed WAL data and commits atomically."""
    deadline = time.monotonic() + 300

    def progress(status: int, remaining: int, total: int) -> None:
        if time.monotonic() > deadline:
            raise TimeoutError("Database copy exceeded five minutes")

    src = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(target.resolve().as_uri() + "?mode=rw", uri=True, timeout=30)
        try:
            src.backup(dst, pages=256, progress=progress, sleep=0.05)
        finally:
            dst.close()
    finally:
        src.close()


def _schema(conn: sqlite3.Connection) -> list:
    return conn.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    ).fetchall()


def validate_database(path: Path) -> None:
    """Accept a complete database of this schema, never a snapshots-only salvage."""
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA trusted_schema=OFF")
        if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("The SQLite backup is damaged")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("The SQLite backup has invalid references")
        with tempfile.TemporaryDirectory(prefix="schema-", dir=path.parent) as folder:
            expected = Path(folder) / "expected.sqlite3"
            SnapshotStore(expected).init_db()
            reference = sqlite3.connect(expected)
            try:
                if _schema(conn) != _schema(reference):
                    raise ValueError("Incompatible database: use a full backup from the same SolarPi version")
            finally:
                reference.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError("The uploaded file is not a valid SQLite backup") from exc
    finally:
        conn.close()
