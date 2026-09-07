"""Shared SQLite connection dependency (API layer, Group F).

`get_connection()` (E3-S1) opens a brand-new `sqlite3.Connection` on every
call -- fine for tests and one-off scripts, but calling it fresh per
*request* would be wrong for `AppConfig.db_path == ":memory:"`, since SQLite
gives every `:memory:` connection its own private, empty database. This
module caches one connection per distinct `db_path` for the life of the
process (`lru_cache`), matching the single-operator local-demo deployment
model (BRD sec 11: no concurrent-request scaling concerns) and the same
`lru_cache`-wrapped-settings pattern `src.api.dependencies.auth.
get_app_config` already uses.

Tests override this dependency directly with a fixture-owned connection via
`app.dependency_overrides[get_db_connection]`, exactly as
`test_auth_dependency.py` already overrides `get_app_config` -- so route
tests never depend on this caching behavior at all.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache

from fastapi import Depends

from src.api.dependencies.auth import get_app_config
from src.config.app_config import AppConfig
from src.db.connection import get_connection


@lru_cache
def _shared_connection(db_path: str) -> sqlite3.Connection:
    """Open (once per `db_path`) the connection every request shares.

    `check_same_thread=False`: FastAPI runs a plain (non-`async`) `Depends`
    callable like `get_db_connection` via `anyio.to_thread` -- a worker
    thread that can differ request to request -- while this connection is
    opened exactly once and cached. SQLite's default same-thread guard would
    reject that as cross-thread use even though, per BRD sec 11 (single-
    operator local demo, no concurrent-request scaling), nothing here ever
    performs concurrent writes on it from two threads at once.
    """
    return get_connection(db_path, check_same_thread=False)


def get_db_connection(app_config: AppConfig = Depends(get_app_config)) -> sqlite3.Connection:  # noqa: B008
    """FastAPI dependency: a process-wide cached connection to `app_config.db_path`."""
    return _shared_connection(app_config.db_path)
