"""Tests for backend/src/config/app_config.py (E2-S3)."""

import pytest
from src.config.app_config import AppConfig, load_app_config
from src.types.enums import Role
from src.types.exceptions import ConfigError

_DB_PATH_ENV_VAR = "CLAIMFLOW_DB_PATH"
_BACKEND_PORT_ENV_VAR = "CLAIMFLOW_BACKEND_PORT"
_FRONTEND_PORT_ENV_VAR = "CLAIMFLOW_FRONTEND_PORT"


@pytest.fixture(autouse=True)
def _clean_claimflow_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no ambient CLAIMFLOW_* env vars leak in between tests."""
    monkeypatch.delenv(_DB_PATH_ENV_VAR, raising=False)
    monkeypatch.delenv(_BACKEND_PORT_ENV_VAR, raising=False)
    monkeypatch.delenv(_FRONTEND_PORT_ENV_VAR, raising=False)


# --- AC1: db_path, backend_port (8000 default), frontend_port (5173 default) ---


def test_load_app_config_exposes_db_path_and_default_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_DB_PATH_ENV_VAR, "/tmp/claimflow.db")

    config = load_app_config()

    assert isinstance(config, AppConfig)
    assert config.db_path == "/tmp/claimflow.db"
    assert config.backend_port == 8000
    assert config.frontend_port == 5173


def test_load_app_config_honors_port_overrides_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_DB_PATH_ENV_VAR, "/tmp/claimflow.db")
    monkeypatch.setenv(_BACKEND_PORT_ENV_VAR, "9000")
    monkeypatch.setenv(_FRONTEND_PORT_ENV_VAR, "3000")

    config = load_app_config()

    assert config.backend_port == 9000
    assert config.frontend_port == 3000


def test_load_app_config_invalid_port_override_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_DB_PATH_ENV_VAR, "/tmp/claimflow.db")
    monkeypatch.setenv(_BACKEND_PORT_ENV_VAR, "not-a-port")

    with pytest.raises(ConfigError):
        load_app_config()


# --- AC2: valid_roles equals exactly CUSTOMER, ASSESSOR, ADMIN, from Types.Role ---


def test_load_app_config_valid_roles_matches_role_enum_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_DB_PATH_ENV_VAR, "/tmp/claimflow.db")

    config = load_app_config()

    assert list(config.valid_roles) == [Role.CUSTOMER, Role.ASSESSOR, Role.ADMIN]


# --- AC3: missing required env var (db_path) raises a typed config error
# naming the missing variable ---


def test_load_app_config_missing_db_path_raises_config_error_naming_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ConfigError) as exc_info:
        load_app_config()

    assert exc_info.value.variable_name == _DB_PATH_ENV_VAR
    assert _DB_PATH_ENV_VAR in str(exc_info.value)


def test_load_app_config_empty_db_path_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_DB_PATH_ENV_VAR, "")

    with pytest.raises(ConfigError):
        load_app_config()


def test_load_app_config_accepts_explicit_env_mapping() -> None:
    config = load_app_config(
        {
            _DB_PATH_ENV_VAR: "/data/claimflow.db",
            _BACKEND_PORT_ENV_VAR: "8080",
        }
    )

    assert config.db_path == "/data/claimflow.db"
    assert config.backend_port == 8080
    assert config.frontend_port == 5173
