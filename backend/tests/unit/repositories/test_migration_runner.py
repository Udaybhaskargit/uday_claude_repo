"""Unit tests for `src.db.migration_runner` (E3-S1, F024-F027).

Synthetic migration sets under `tmp_path` are used to engineer specific
failure conditions (numbering gaps, checksum mismatches); the "all 9 tables"
test points the runner at the real, committed `backend/migrations/`
directory so it exercises the actual shipped SQL.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from src.db.migration_runner import run_migrations
from src.types.exceptions import ConfigError

REAL_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"

EXPECTED_TABLES = {
    "policies",
    "claims",
    "claim_documents",
    "fraud_screenings",
    "assessments",
    "decisions",
    "settlements",
    "claim_state_transitions",
    "admin_overrides",
}


_CREATE_A_SQL = "CREATE TABLE a (id INTEGER PRIMARY KEY);"
_CREATE_B_SQL = "CREATE TABLE b (id INTEGER PRIMARY KEY);"


def _write_migration(directory: Path, filename: str, sql: str) -> None:
    (directory / filename).write_text(sql, encoding="utf-8")


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def test_numbering_gap_raises_before_running_anything(tmp_path: Path) -> None:
    """F024: a directory with a gap (0001, 0003) must fail closed."""
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    _write_migration(migrations_dir, "0001_create_a.sql", _CREATE_A_SQL)
    _write_migration(migrations_dir, "0003_create_b.sql", _CREATE_B_SQL)

    conn = sqlite3.connect(":memory:")
    try:
        conn.row_factory = sqlite3.Row
        with pytest.raises(ConfigError, match="gap"):
            run_migrations(conn, str(migrations_dir))

        tables = _table_names(conn)
        assert "a" not in tables
        assert "b" not in tables
    finally:
        conn.close()


def test_duplicate_migration_number_raises(tmp_path: Path) -> None:
    """A duplicate NNNN prefix is also a numbering violation (F024)."""
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    _write_migration(migrations_dir, "0001_create_a.sql", _CREATE_A_SQL)
    _write_migration(migrations_dir, "0001_create_b.sql", _CREATE_B_SQL)

    conn = sqlite3.connect(":memory:")
    try:
        conn.row_factory = sqlite3.Row
        with pytest.raises(ConfigError, match="[Dd]uplicate"):
            run_migrations(conn, str(migrations_dir))
    finally:
        conn.close()


def test_fresh_db_with_real_migrations_creates_all_nine_tables(tmp_path: Path) -> None:
    """F025: running the real migrations/ dir against a fresh DB creates all 9 tables."""
    db_path = tmp_path / "claimflow.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        run_migrations(conn, str(REAL_MIGRATIONS_DIR))

        assert EXPECTED_TABLES.issubset(_table_names(conn))
    finally:
        conn.close()


def test_running_twice_is_idempotent(tmp_path: Path) -> None:
    """F026: a second run against the same DB is a no-op -- no error, no re-apply."""
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    _write_migration(migrations_dir, "0001_create_a.sql", _CREATE_A_SQL)

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row

        run_migrations(conn, str(migrations_dir))
        first_count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]

        # If the runner tried to re-execute 0001's CREATE TABLE (no IF NOT
        # EXISTS in domain migrations), this second call would raise
        # sqlite3.OperationalError. It must not.
        run_migrations(conn, str(migrations_dir))
        second_count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]

        assert first_count == 1
        assert second_count == 1
    finally:
        conn.close()


def test_checksum_mismatch_after_edit_raises(tmp_path: Path) -> None:
    """F027: mutating an already-applied migration file's bytes is detected."""
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    migration_path = migrations_dir / "0001_create_a.sql"
    migration_path.write_text(_CREATE_A_SQL, encoding="utf-8")

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        run_migrations(conn, str(migrations_dir))

        with migration_path.open("a", encoding="utf-8") as handle:
            handle.write("\n-- tampered after apply\n")

        with pytest.raises(ConfigError, match="checksum"):
            run_migrations(conn, str(migrations_dir))
    finally:
        conn.close()


def test_bad_filename_pattern_raises(tmp_path: Path) -> None:
    """A filename that doesn't match NNNN_description.sql is rejected."""
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    _write_migration(migrations_dir, "not_a_migration.sql", _CREATE_A_SQL)

    conn = sqlite3.connect(":memory:")
    try:
        conn.row_factory = sqlite3.Row
        with pytest.raises(ConfigError):
            run_migrations(conn, str(migrations_dir))
    finally:
        conn.close()


def test_empty_migrations_directory_is_a_noop(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()

    conn = sqlite3.connect(":memory:")
    try:
        conn.row_factory = sqlite3.Row
        run_migrations(conn, str(migrations_dir))  # must not raise
        assert _table_names(conn) == {"schema_migrations"}
    finally:
        conn.close()
