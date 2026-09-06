"""Centralized application/environment configuration (E2-S3).

Per `.claude/architecture.md`, Config is Layer 2 and may import only from
Types (here: `src.types.enums.Role`, `src.types.exceptions.ConfigError`). No
other layer should read `os.environ` directly -- every backend layer that
needs the DB path, a port, or the set of valid roles goes through
`AppConfig`/`load_app_config` instead.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from src.types.enums import Role
from src.types.exceptions import ConfigError

DB_PATH_ENV_VAR = "CLAIMFLOW_DB_PATH"
BACKEND_PORT_ENV_VAR = "CLAIMFLOW_BACKEND_PORT"
FRONTEND_PORT_ENV_VAR = "CLAIMFLOW_FRONTEND_PORT"

DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 5173

VALID_ROLES: tuple[Role, ...] = (Role.CUSTOMER, Role.ASSESSOR, Role.ADMIN)


@dataclass(frozen=True)
class AppConfig:
    """Centralized app configuration (E2-S3 AC1/AC2)."""

    db_path: str
    backend_port: int = DEFAULT_BACKEND_PORT
    frontend_port: int = DEFAULT_FRONTEND_PORT
    valid_roles: tuple[Role, ...] = VALID_ROLES


def load_app_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """Build an `AppConfig` from environment variables.

    `db_path` (`CLAIMFLOW_DB_PATH`) is required and has no default: if it is
    missing or empty, this raises `ConfigError` naming the missing variable
    (E2-S3 AC3). `backend_port`/`frontend_port` fall back to 8000/5173 when
    their env vars are unset or empty, per E2-S3 AC1.

    `env` defaults to `os.environ` and is only exposed as a parameter so
    callers (and tests) can pass an explicit mapping instead of mutating
    process-wide environment state.
    """
    source: Mapping[str, str] = env if env is not None else os.environ

    db_path = source.get(DB_PATH_ENV_VAR)
    if not db_path:
        raise ConfigError(
            f"Missing required environment variable: {DB_PATH_ENV_VAR}",
            variable_name=DB_PATH_ENV_VAR,
        )

    backend_port = _read_int_env(source, BACKEND_PORT_ENV_VAR, DEFAULT_BACKEND_PORT)
    frontend_port = _read_int_env(source, FRONTEND_PORT_ENV_VAR, DEFAULT_FRONTEND_PORT)

    return AppConfig(
        db_path=db_path,
        backend_port=backend_port,
        frontend_port=frontend_port,
        valid_roles=VALID_ROLES,
    )


def _read_int_env(source: Mapping[str, str], var_name: str, default: int) -> int:
    raw_value = source.get(var_name)
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigError(
            f"Environment variable {var_name} must be an integer, got {raw_value!r}.",
            variable_name=var_name,
        ) from exc
