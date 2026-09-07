"""FastAPI application factory (E8-S1 scaffold, extended in Group F/G/H/I).

Mounts the admin router (E9-S4, Group F), the document verification router
(E9-S2, Group G), the assessor workbench router (E9-S3, Group H), and the
customer claims router (E9-S1, Group I), and registers the E1-S3
exception -> HTTP status mapping via `register_error_handlers()`, alongside
the bare `/health` liveness probe (`specs/design/api-contracts.md` "Health"
section, NFR-07) that E8-S1's auth-dependency tests already mount throwaway
protected routes against.
"""

from __future__ import annotations

from fastapi import FastAPI

from src.api.error_handlers import register_error_handlers
from src.api.routers.admin_router import router as admin_router
from src.api.routers.claims_router import router as claims_router
from src.api.routers.documents_router import router as documents_router
from src.api.routers.workbench_router import router as workbench_router


def create_app() -> FastAPI:
    """Build and return the ClaimFlow FastAPI application."""
    app = FastAPI(title="ClaimFlow API")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # `documents_router`/`workbench_router` declare literal-path siblings under
    # the same `/api/claims` prefix (`/api/claims/documents/pending`,
    # `/api/claims/fraud-alerts`) that must be registered -- and therefore
    # route-matched -- BEFORE `claims_router`'s `/api/claims/{claim_id}`, or
    # Starlette matches the dynamic segment first (its routing is structural
    # path-shape matching, not type-directed) and only then fails `claim_id`'s
    # int conversion with a 422, instead of ever trying the literal routes.
    app.include_router(admin_router)
    app.include_router(documents_router)
    app.include_router(workbench_router)
    app.include_router(claims_router)
    register_error_handlers(app)

    return app


app = create_app()
