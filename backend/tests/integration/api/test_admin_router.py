"""Integration tests for the E9-S4 admin API (F103-F106).

Builds the real app via `create_app()` (mounting `admin_router` and
`error_handlers`, per `src/main.py`) and overrides both `get_app_config`
(E8-S1 pattern) and `get_db_connection` (Group F addition) with a real,
migrated SQLite connection owned by the test fixture -- so these tests
exercise the full request -> router -> service -> repository -> DB round
trip through `TestClient`, not mocks.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.dependencies.auth import get_app_config
from src.api.dependencies.db import get_db_connection
from src.config.app_config import AppConfig
from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.main import create_app
from src.types.enums import Role

REAL_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    db_path = tmp_path / "claimflow.db"
    # check_same_thread=False: TestClient drives the app from its own portal
    # thread, distinct from this fixture's creating thread (see db.py).
    connection = get_connection(str(db_path), check_same_thread=False)
    run_migrations(connection, str(REAL_MIGRATIONS_DIR))
    yield connection
    connection.close()


@pytest.fixture
def client(conn: sqlite3.Connection) -> Iterator[TestClient]:
    app: FastAPI = create_app()
    app.dependency_overrides[get_app_config] = lambda: AppConfig(
        db_path=":memory:",
        valid_roles=(Role.CUSTOMER, Role.ASSESSOR, Role.ADMIN),
    )
    app.dependency_overrides[get_db_connection] = lambda: conn

    with TestClient(app) as test_client:
        yield test_client


def _admin_headers(actor_id: str = "admin-1") -> dict[str, str]:
    return {"X-Role": "ADMIN", "X-Actor-Id": actor_id}


def _insert_policy(conn: sqlite3.Connection, policy_number: str = "POL-001") -> int:
    cursor = conn.execute(
        "INSERT INTO policies "
        "(policy_number, product_type, status, sum_insured, effective_date, "
        "expiry_date, created_at) VALUES (?, 'MOTOR', 'ACTIVE', '500000.00', "
        "'2025-01-01', '2025-12-31', datetime('now'))",
        (policy_number,),
    )
    conn.commit()
    policy_id = cursor.lastrowid
    assert policy_id is not None
    return policy_id


def _insert_claim(
    conn: sqlite3.Connection,
    policy_id: int,
    *,
    claim_type: str = "MOTOR",
    status: str = "MANUAL_REVIEW",
    claim_amount: str = "75000.00",
) -> int:
    cursor = conn.execute(
        "INSERT INTO claims "
        "(policy_id, claim_type, incident_date, claim_amount, status, created_at, updated_at) "
        "VALUES (?, ?, '2026-03-11', ?, ?, datetime('now'), datetime('now'))",
        (policy_id, claim_type, claim_amount, status),
    )
    conn.commit()
    claim_id = cursor.lastrowid
    assert claim_id is not None
    return claim_id


def _insert_settlement(
    conn: sqlite3.Connection, claim_id: int, decision_id: int, *, payout_amount: str = "35000.00"
) -> int:
    cursor = conn.execute(
        "INSERT INTO settlements (claim_id, decision_id, payout_amount, payment_reference, "
        "created_at) VALUES (?, ?, ?, 'STUB-PAY-0000001-01', datetime('now'))",
        (claim_id, decision_id, payout_amount),
    )
    conn.commit()
    settlement_id = cursor.lastrowid
    assert settlement_id is not None
    return settlement_id


def _insert_decision(conn: sqlite3.Connection, claim_id: int) -> int:
    cursor = conn.execute(
        "INSERT INTO decisions (claim_id, outcome, reason_code, decided_by, created_at) "
        "VALUES (?, 'AUTO_APPROVE', 'AUTO_APPROVED_LOW_RISK', 'system', datetime('now'))",
        (claim_id,),
    )
    conn.commit()
    decision_id = cursor.lastrowid
    assert decision_id is not None
    return decision_id


class TestListAdminClaims:
    def test_filters_by_status_and_product(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F103."""
        policy_id = _insert_policy(conn)
        _insert_claim(conn, policy_id, claim_type="MOTOR", status="MANUAL_REVIEW")
        _insert_claim(conn, policy_id, claim_type="HEALTH", status="MANUAL_REVIEW")
        _insert_claim(conn, policy_id, claim_type="MOTOR", status="SETTLED")

        response = client.get(
            "/api/admin/claims",
            params={"status": "MANUAL_REVIEW", "product": "MOTOR"},
            headers=_admin_headers(),
        )

        assert response.status_code == 200
        claims = response.json()["claims"]
        assert len(claims) == 1
        assert claims[0]["status"] == "MANUAL_REVIEW"
        assert claims[0]["claim_type"] == "MOTOR"
        assert claims[0]["claim_amount"] == "75000.00"


class TestListPayouts:
    def test_lists_every_settlement_as_audit_trail(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F104."""
        policy_id = _insert_policy(conn)
        claim_id = _insert_claim(conn, policy_id, status="AUTO_APPROVED")
        decision_id = _insert_decision(conn, claim_id)
        settlement_id = _insert_settlement(conn, claim_id, decision_id, payout_amount="35000.00")

        response = client.get("/api/admin/payouts", headers=_admin_headers())

        assert response.status_code == 200
        payouts = response.json()["payouts"]
        assert len(payouts) == 1
        assert payouts[0]["settlement_id"] == settlement_id
        assert payouts[0]["claim_id"] == claim_id
        assert payouts[0]["payout_amount"] == "35000.00"
        assert payouts[0]["payment_reference"] == "STUB-PAY-0000001-01"


class TestOverrideClaim:
    def test_override_succeeds_and_is_visible_in_subsequent_get(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F105."""
        policy_id = _insert_policy(conn)
        claim_id = _insert_claim(conn, policy_id, status="MANUAL_REVIEW")

        response = client.post(
            f"/api/admin/claims/{claim_id}/override",
            json={"command": "FORCE_APPROVE", "reason_code": "Manual goodwill approval"},
            headers=_admin_headers(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["claim_id"] == claim_id
        assert body["claim_status"] == "AUTO_APPROVED"
        override_id = body["override_id"]

        follow_up = client.get(
            f"/api/admin/claims/{claim_id}/overrides", headers=_admin_headers()
        )
        assert follow_up.status_code == 200
        overrides = follow_up.json()["overrides"]
        assert len(overrides) == 1
        assert overrides[0]["override_id"] == override_id
        assert overrides[0]["admin_actor_id"] == "admin-1"
        assert overrides[0]["command"] == "FORCE_APPROVE"
        assert overrides[0]["reason_code"] == "Manual goodwill approval"

    def test_missing_reason_code_is_rejected_with_422(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        policy_id = _insert_policy(conn)
        claim_id = _insert_claim(conn, policy_id, status="MANUAL_REVIEW")

        response = client.post(
            f"/api/admin/claims/{claim_id}/override",
            json={"command": "FORCE_APPROVE", "reason_code": ""},
            headers=_admin_headers(),
        )

        # Pydantic's own min_length=1 validation rejects this before the
        # route body even runs (FastAPI's native 422), so no override row exists.
        assert response.status_code == 422
        overrides = client.get(
            f"/api/admin/claims/{claim_id}/overrides", headers=_admin_headers()
        ).json()["overrides"]
        assert overrides == []

    def test_invalid_transition_is_rejected_with_409(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        policy_id = _insert_policy(conn)
        claim_id = _insert_claim(conn, policy_id, status="SETTLED")

        response = client.post(
            f"/api/admin/claims/{claim_id}/override",
            json={"command": "FORCE_APPROVE", "reason_code": "test"},
            headers=_admin_headers(),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    def test_unknown_claim_id_is_rejected_with_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/admin/claims/999999/override",
            json={"command": "FORCE_APPROVE", "reason_code": "test"},
            headers=_admin_headers(),
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_unknown_override_command_is_rejected_with_422(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        policy_id = _insert_policy(conn)
        claim_id = _insert_claim(conn, policy_id, status="MANUAL_REVIEW")

        response = client.post(
            f"/api/admin/claims/{claim_id}/override",
            json={"command": "SELF_DESTRUCT", "reason_code": "test"},
            headers=_admin_headers(),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


class TestListClaimOverrides:
    def test_unknown_claim_id_is_rejected_with_404(self, client: TestClient) -> None:
        response = client.get("/api/admin/claims/999999/overrides", headers=_admin_headers())

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestAdminRoutesForbidNonAdmin:
    def test_assessor_role_is_forbidden_on_every_admin_route(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F106."""
        policy_id = _insert_policy(conn)
        claim_id = _insert_claim(conn, policy_id)
        headers = {"X-Role": "ASSESSOR", "X-Actor-Id": "assessor-1"}

        get_claims = client.get("/api/admin/claims", headers=headers)
        get_payouts = client.get("/api/admin/payouts", headers=headers)
        post_override = client.post(
            f"/api/admin/claims/{claim_id}/override",
            json={"command": "FORCE_APPROVE", "reason_code": "test"},
            headers=headers,
        )
        get_overrides = client.get(f"/api/admin/claims/{claim_id}/overrides", headers=headers)

        for response in (get_claims, get_payouts, post_override, get_overrides):
            assert response.status_code == 403
            assert response.json()["detail"]["error"]["code"] == "FORBIDDEN"
