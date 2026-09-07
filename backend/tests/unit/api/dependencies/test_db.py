"""Unit tests for `src.api.dependencies.db` (Group F addition)."""

from __future__ import annotations

import sqlite3
import threading

import pytest
from src.api.dependencies.db import _shared_connection, get_db_connection
from src.config.app_config import AppConfig
from src.types.enums import Role


def test_shared_connection_returns_a_working_sqlite_connection() -> None:
    _shared_connection.cache_clear()
    try:
        conn = _shared_connection(":memory:")
        assert isinstance(conn, sqlite3.Connection)
        conn.execute("SELECT 1")
    finally:
        _shared_connection.cache_clear()


def test_shared_connection_is_cached_per_db_path() -> None:
    _shared_connection.cache_clear()
    try:
        first = _shared_connection(":memory:")
        second = _shared_connection(":memory:")
        assert first is second
    finally:
        _shared_connection.cache_clear()


def test_get_db_connection_wraps_shared_connection() -> None:
    _shared_connection.cache_clear()
    try:
        config = AppConfig(
            db_path=":memory:", valid_roles=(Role.CUSTOMER, Role.ASSESSOR, Role.ADMIN)
        )
        conn = get_db_connection(config)
        assert isinstance(conn, sqlite3.Connection)
    finally:
        _shared_connection.cache_clear()


@pytest.mark.parametrize("db_path", [":memory:"])
def test_shared_connection_allows_cross_thread_use(db_path: str) -> None:
    """check_same_thread=False is actually applied, not just accepted."""
    _shared_connection.cache_clear()
    try:
        conn = _shared_connection(db_path)
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.commit()

        errors: list[BaseException] = []

        def _use_from_other_thread() -> None:
            try:
                conn.execute("SELECT * FROM t")
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        thread = threading.Thread(target=_use_from_other_thread)
        thread.start()
        thread.join()

        assert errors == []
    finally:
        _shared_connection.cache_clear()
