"""FastAPI application factory (E8-S1 scaffold).

Business routers (claims/documents/workbench/admin) don't exist yet -- they
land in later groups (E9-S1..S4, per `specs/design/folder-structure.md`).
This module currently exposes only the bare app factory and the `/health`
liveness probe (`specs/design/api-contracts.md` "Health" section, NFR-07),
which is enough for E8-S1's auth-dependency tests to mount throwaway
protected routes against a real FastAPI app. Later groups extend
`create_app()` to `include_router(...)` each business router and register
the E1-S3 exception -> HTTP status mapping in `error_handlers.py`.
"""

from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build and return the ClaimFlow FastAPI application."""
    app = FastAPI(title="ClaimFlow API")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
