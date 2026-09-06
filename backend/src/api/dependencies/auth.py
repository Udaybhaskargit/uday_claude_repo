"""Role-based auth boundary dependency (E8-S1, BRD sec 7.1, NFR-04).

This is a *stub* auth boundary: the `X-Role` and `X-Actor-Id` request headers
are read verbatim and resolved into an `ActorContext`, without checking them
against any user/identity store (none exists in this project -- see the
Conventions section of `specs/design/api-contracts.md`). It is intentionally
not production-grade authentication.

`AppConfig` provisioning: `get_app_config` wraps
`src.config.app_config.load_app_config()` behind `functools.lru_cache` so the
environment is read exactly once per process and the resulting immutable
`AppConfig` is reused across requests -- the same pattern FastAPI's own docs
recommend for settings objects
(https://fastapi.tiangolo.com/advanced/settings/#creating-the-settings-only-once-with-lru_cache).
Tests override this dependency via `app.dependency_overrides[get_app_config]`
instead of mutating real environment variables.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache

from fastapi import Depends, Header, HTTPException

from src.config.app_config import AppConfig, load_app_config
from src.types.enums import ApiErrorCode, Role
from src.types.models import ActorContext


@lru_cache
def get_app_config() -> AppConfig:
    """FastAPI dependency: a process-wide cached `AppConfig`."""
    return load_app_config()


def _unauthorized(message: str) -> HTTPException:
    """Build the uniform-error-envelope 401 for a bad/missing auth header."""
    return HTTPException(
        status_code=401,
        detail={
            "error": {
                "code": ApiErrorCode.UNAUTHORIZED.value,
                "message": message,
                "details": {},
            }
        },
    )


async def get_actor_context(
    x_role: str | None = Header(default=None, alias="X-Role"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
    app_config: AppConfig = Depends(get_app_config),  # noqa: B008
) -> ActorContext:
    """Resolve the `X-Role`/`X-Actor-Id` headers into an `ActorContext`.

    E8-S1 acceptance criteria:
      - Missing `X-Role` -> 401 (AC3).
      - `X-Role` not one of `AppConfig.valid_roles` -> 401 (AC2).
      - Missing `X-Actor-Id` -> 401. The story doesn't exercise this case
        explicitly, but `api-contracts.md` requires both headers on every
        authenticated route, so a request with a role but no actor id is
        rejected the same way as a missing/invalid role.
      - Otherwise -> `ActorContext(role, actor_id)` (AC1).
    """
    if x_role is None:
        raise _unauthorized("Missing required header: X-Role.")
    if x_actor_id is None:
        raise _unauthorized("Missing required header: X-Actor-Id.")
    if x_role not in {role.value for role in app_config.valid_roles}:
        raise _unauthorized(f"'{x_role}' is not a recognized role.")
    return ActorContext(role=Role(x_role), actor_id=x_actor_id)


def require_role(*allowed_roles: Role) -> Callable[..., Awaitable[ActorContext]]:
    """Dependency factory: only let `allowed_roles` reach the route (E8-S1 AC4).

    Usage: `Depends(require_role(Role.ADMIN))`. Depends internally on
    `get_actor_context`, so a missing/invalid role/actor id still yields 401
    before the 403 role check ever runs.
    """

    async def _check_role(
        actor_context: ActorContext = Depends(get_actor_context),  # noqa: B008
    ) -> ActorContext:
        if actor_context.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": ApiErrorCode.FORBIDDEN.value,
                        "message": (
                            f"Role '{actor_context.role.value}' is not permitted "
                            "to access this resource."
                        ),
                        "details": {},
                    }
                },
            )
        return actor_context

    return _check_role
