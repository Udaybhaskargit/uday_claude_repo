"""Integration tests for the E8-S1 auth dependency (F085-F088).

There are no business routers yet for Group C (they land in later groups per
`specs/design/folder-structure.md`), so these tests build the real app via
`create_app()` and mount two throwaway routes onto it: one guarded only by
`get_actor_context` (covers F085/F086/F087) and one guarded by
`require_role(Role.ADMIN)` (covers F088). `get_app_config` is overridden with
a fixed in-memory `AppConfig` so these tests never depend on real environment
variables (`CLAIMFLOW_DB_PATH` etc.) being set in the test runner.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from src.api.dependencies.auth import get_actor_context, get_app_config, require_role
from src.config.app_config import AppConfig
from src.main import create_app
from src.types.enums import Role
from src.types.models import ActorContext


@pytest.fixture
def handler_calls() -> list[str]:
    """Records which protected route handler bodies actually executed.

    Used to assert (per E8-S1 AC2/AC3/AC4) that a rejected request never
    reaches the route handler -- not just that the status code is right.
    """
    return []


@pytest.fixture
def client(handler_calls: list[str]) -> Iterator[TestClient]:
    app: FastAPI = create_app()

    @app.get("/whoami")
    async def whoami(
        actor: ActorContext = Depends(get_actor_context),  # noqa: B008
    ) -> dict[str, str]:
        handler_calls.append("whoami")
        return {"role": actor.role.value, "actor_id": actor.actor_id}

    @app.get("/admin-only")
    async def admin_only(
        actor: ActorContext = Depends(require_role(Role.ADMIN)),  # noqa: B008
    ) -> dict[str, str]:
        handler_calls.append("admin-only")
        return {"role": actor.role.value, "actor_id": actor.actor_id}

    app.dependency_overrides[get_app_config] = lambda: AppConfig(
        db_path=":memory:",
        valid_roles=(Role.CUSTOMER, Role.ASSESSOR, Role.ADMIN),
    )

    with TestClient(app) as test_client:
        yield test_client


def test_valid_role_and_actor_id_resolves_actor_context(
    client: TestClient, handler_calls: list[str]
) -> None:
    """F085 / AC1: X-Role: ASSESSOR + a valid actor id -> 200, correct ActorContext."""
    response = client.get("/whoami", headers={"X-Role": "ASSESSOR", "X-Actor-Id": "assessor-1"})

    assert response.status_code == 200
    assert response.json() == {"role": "ASSESSOR", "actor_id": "assessor-1"}
    assert handler_calls == ["whoami"]


def test_invalid_role_value_is_rejected_before_handler_runs(
    client: TestClient, handler_calls: list[str]
) -> None:
    """F086 / AC2: X-Role: SUPERVISOR (not in valid_roles) -> 401, handler never runs."""
    response = client.get("/whoami", headers={"X-Role": "SUPERVISOR", "X-Actor-Id": "someone"})

    assert response.status_code == 401
    error = response.json()["detail"]["error"]
    assert error["code"] == "UNAUTHORIZED"
    assert isinstance(error["message"], str) and error["message"]
    assert handler_calls == []


def test_missing_role_header_is_rejected(client: TestClient, handler_calls: list[str]) -> None:
    """F087 / AC3: X-Role header missing entirely -> 401, handler never runs."""
    response = client.get("/whoami", headers={"X-Actor-Id": "someone"})

    assert response.status_code == 401
    error = response.json()["detail"]["error"]
    assert error["code"] == "UNAUTHORIZED"
    assert isinstance(error["message"], str) and error["message"]
    assert handler_calls == []


def test_missing_actor_id_header_is_rejected(
    client: TestClient, handler_calls: list[str]
) -> None:
    """Extension beyond the story's explicit ACs: X-Actor-Id is also mandatory.

    api-contracts.md requires both headers on every authenticated route; a
    request with a valid role but no actor id is rejected the same way as a
    missing/invalid role.
    """
    response = client.get("/whoami", headers={"X-Role": "ASSESSOR"})

    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"
    assert handler_calls == []


def test_valid_role_without_required_permission_is_forbidden(
    client: TestClient, handler_calls: list[str]
) -> None:
    """F088 / AC4: require_role(ADMIN) rejects X-Role: ASSESSOR with 403."""
    response = client.get(
        "/admin-only", headers={"X-Role": "ASSESSOR", "X-Actor-Id": "assessor-1"}
    )

    assert response.status_code == 403
    error = response.json()["detail"]["error"]
    assert error["code"] == "FORBIDDEN"
    assert isinstance(error["message"], str) and error["message"]
    assert handler_calls == []


def test_admin_role_is_allowed_through_require_role(
    client: TestClient, handler_calls: list[str]
) -> None:
    """require_role(ADMIN) lets a matching ADMIN actor reach the handler."""
    response = client.get("/admin-only", headers={"X-Role": "ADMIN", "X-Actor-Id": "admin-1"})

    assert response.status_code == 200
    assert response.json() == {"role": "ADMIN", "actor_id": "admin-1"}
    assert handler_calls == ["admin-only"]


def test_health_endpoint_requires_no_auth_headers(client: TestClient) -> None:
    """GET /health (api-contracts.md "Health" section) needs no auth at all."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_app_config_wraps_load_app_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """`get_app_config` is a thin `lru_cache`-wrapped `load_app_config()` call.

    All the route-level tests above override this dependency and never
    exercise the real function body, so it's covered directly here.
    """
    monkeypatch.setenv("CLAIMFLOW_DB_PATH", ":memory:")
    get_app_config.cache_clear()
    try:
        config = get_app_config()
        assert config.db_path == ":memory:"
        assert config.valid_roles == (Role.CUSTOMER, Role.ASSESSOR, Role.ADMIN)
    finally:
        get_app_config.cache_clear()
