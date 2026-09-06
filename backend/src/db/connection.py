"""SQLite connection factory (Repository layer, E3-S1).

Every backend layer that needs a raw `sqlite3.Connection` goes through
`get_connection()` rather than calling `sqlite3.connect()` directly, so the
two cross-cutting connection settings ClaimFlow relies on -- foreign key
enforcement and dict-like row access -- are applied consistently everywhere
(startup, tests, the migration runner itself).
"""

from __future__ import annotations

import sqlite3


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a `sqlite3.Connection` configured for ClaimFlow's needs.

    - Enables foreign key enforcement via `PRAGMA foreign_keys = ON`
      (SQLite has this off by default, per-connection).
    - Sets `row_factory = sqlite3.Row` so callers get dict-like
      (`row["column_name"]`) access instead of raw positional tuples.
    """
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection
