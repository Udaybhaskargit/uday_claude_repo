"""SQLite connection factory (Repository layer, E3-S1).

Every backend layer that needs a raw `sqlite3.Connection` goes through
`get_connection()` rather than calling `sqlite3.connect()` directly, so the
two cross-cutting connection settings ClaimFlow relies on -- foreign key
enforcement and dict-like row access -- are applied consistently everywhere
(startup, tests, the migration runner itself).
"""

from __future__ import annotations

import sqlite3


def get_connection(db_path: str, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open a `sqlite3.Connection` configured for ClaimFlow's needs.

    - Enables foreign key enforcement via `PRAGMA foreign_keys = ON`
      (SQLite has this off by default, per-connection).
    - Sets `row_factory = sqlite3.Row` so callers get dict-like
      (`row["column_name"]`) access instead of raw positional tuples.

    `check_same_thread` (Group F addition) defaults to `True`, preserving
    every existing caller's behavior unchanged. It exists for
    `src.api.dependencies.db.get_db_connection`, whose single cached
    connection is shared across every request the (single-threaded) async
    app handles -- and for that connection's test doubles, which Starlette's
    `TestClient` drives from a separate portal thread. Passing `False` there
    is safe: nothing in this codebase performs concurrent writes on the same
    connection from multiple threads at once (BRD sec 11: single-operator
    local demo, no concurrent-request scaling), so SQLite's same-thread
    guard is disabled deliberately rather than worked around.
    """
    connection = sqlite3.connect(db_path, check_same_thread=check_same_thread)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection
