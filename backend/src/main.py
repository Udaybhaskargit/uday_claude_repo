"""FastAPI application factory (E8-S1 scaffold, extended in Group F/G/H).

The claims intake router (E9-S1) still doesn't exist yet -- it lands in a
later group (per `specs/design/folder-structure.md`). This module mounts
the admin router (E9-S4, Group F), the document verification router
(E9-S2, Group G), and the assessor workbench router (E9-S3, Group H), and
registers the E1-S3 exception -> HTTP status mapping via
`register_error_handlers()`, alongside the bare `/health` liveness probe
(`specs/design/api-contracts.md` "Health" section, NFR-07) that E8-S1's
auth-dependency tests already mount throwaway protected routes against.

CORS (added E11-S1/E11-S4 UI catch-up): the deployed shape per `init.sh`/
`.env.example` is two separate origins -- frontend on :5173, backend on
:8000, with `VITE_API_BASE_URL` pointing the browser at the backend's
absolute origin rather than going through a same-origin proxy. Without a
CORS policy, every browser-issued request from the frontend (fetch calls in
`frontend/src/api/httpClient.ts`) is blocked before any UI story that talks
to the API can ever render real data. `allow_origins=["*"]` matches BRD sec
11's single-operator local demo scope (no auth cookies/credentials in play --
E8-S1's stub auth is header-based via `X-Role`/`X-Actor-Id`, never cookies --
so a wildcard origin carries none of the credentialed-CORS risk it would for
a cookie-authenticated API); `allow_credentials` is left at its default
(False) accordingly, which is also a hard requirement for `allow_origins=
["*"]` to be honored by browsers at all.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.error_handlers import register_error_handlers
from src.api.routers.admin_router import router as admin_router
from src.api.routers.documents_router import router as documents_router
from src.api.routers.workbench_router import router as workbench_router


def create_app() -> FastAPI:
    """Build and return the ClaimFlow FastAPI application."""
    app = FastAPI(title="ClaimFlow API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(admin_router)
    app.include_router(documents_router)
    app.include_router(workbench_router)
    register_error_handlers(app)

    return app


app = create_app()
