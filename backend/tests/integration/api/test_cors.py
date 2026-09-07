"""Integration test for the app-wide CORS policy (src/main.py).

Confirms the browser-facing contract the E11 UI stories depend on: a
cross-origin request from the Vite dev server (:5173) to the API (:8000)
gets an `Access-Control-Allow-Origin` response header, so
`frontend/src/api/httpClient.ts`'s `fetch()` calls aren't silently blocked
by the browser before ever reaching a route handler.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from src.main import create_app


def test_health_response_carries_cors_allow_origin_header() -> None:
    client = TestClient(create_app())

    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_unrecognized_origin_gets_no_allow_origin_header() -> None:
    """The policy is scoped to the project's one documented dev origin
    (specs/design/deployment.md), not a wildcard -- a request claiming to
    come from anywhere else must not get an Allow-Origin header back."""
    client = TestClient(create_app())

    response = client.get("/health", headers={"Origin": "http://evil.example.com"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") is None


def test_preflight_request_is_allowed_for_a_custom_auth_header() -> None:
    """`X-Role`/`X-Actor-Id` are non-simple headers, so the browser sends a
    CORS preflight `OPTIONS` before the real request -- confirm it succeeds."""
    client = TestClient(create_app())

    response = client.options(
        "/api/admin/claims",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-role,x-actor-id",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
