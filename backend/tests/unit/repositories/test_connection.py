"""Unit tests for `src.db.connection` (E3-S1)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.db.connection import get_connection


def test_get_connection_uses_row_factory(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = get_connection(str(db_path))
    try:
        assert conn.row_factory is sqlite3.Row
    finally:
        conn.close()


def test_get_connection_enables_foreign_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = get_connection(str(db_path))
    try:
        (foreign_keys_on,) = conn.execute("PRAGMA foreign_keys").fetchone()
        assert foreign_keys_on == 1
    finally:
        conn.close()


def test_get_connection_rows_support_dict_like_access(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = get_connection(str(db_path))
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO t (name) VALUES ('sample')")
        conn.commit()

        row = conn.execute("SELECT id, name FROM t").fetchone()

        assert row["name"] == "sample"
    finally:
        conn.close()


def test_get_connection_foreign_key_violation_is_enforced(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = get_connection(str(db_path))
    try:
        conn.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER, "
            "FOREIGN KEY (parent_id) REFERENCES parent (id))"
        )
        conn.commit()

        try:
            conn.execute("INSERT INTO child (id, parent_id) VALUES (1, 999)")
            conn.commit()
            raised = False
        except sqlite3.IntegrityError:
            raised = True

        assert raised, "foreign key enforcement should reject an orphaned reference"
    finally:
        conn.close()
