"""Integration tests for the E9-S1 customer claims API (F093-F096).

Builds the real app via `create_app()` and overrides `get_app_config`/
`get_db_connection` with real, migrated fixtures, exercising the full
request -> router -> service -> repository -> DB round trip through
`TestClient`, not mocks. Mirrors `test_workbench_router.py`'s fixture
pattern.
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
from src.services.settlement_service import settle
from src.types.enums import PolicyStatus, Role

REAL_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    db_path = tmp_path / "claimflow.db"
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


def _customer_headers(actor_id: str = "customer-1") -> dict[str, str]:
    return {"X-Role": "CUSTOMER", "X-Actor-Id": actor_id}


def _assessor_headers(actor_id: str = "assessor-1") -> dict[str, str]:
    return {"X-Role": "ASSESSOR", "X-Actor-Id": actor_id}


def _insert_policy(
    conn: sqlite3.Connection,
    policy_number: str,
    *,
    status: str = PolicyStatus.ACTIVE.value,
    effective_date: str = "2025-01-01",
    expiry_date: str = "2026-12-31",
) -> None:
    conn.execute(
        "INSERT INTO policies "
        "(policy_number, product_type, status, sum_insured, effective_date, "
        "expiry_date, created_at) VALUES (?, 'MOTOR', ?, '500000.00', ?, ?, datetime('now'))",
        (policy_number, status, effective_date, expiry_date),
    )
    conn.commit()


class TestSubmitClaim:
    def test_valid_motor_fnol_returns_201_with_claim_id_and_status(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F093."""
        _insert_policy(conn, "POL-INTAKE-1")

        response = client.post(
            "/api/claims",
            json={
                "policy_number": "POL-INTAKE-1",
                "claim_type": "MOTOR",
                "incident_date": "2026-03-10",
                "claim_amount": "40000.00",
            },
            headers=_customer_headers(),
        )

        assert response.status_code == 201
        body = response.json()
        assert isinstance(body["claim_id"], int)
        assert body["status"] == "DOCS_PENDING"
        assert {c["document_type"] for c in body["checklist"]} == {"POLICE_FIR", "INVOICE"}
        assert all(c["verification_status"] == "MISSING" for c in body["checklist"])

    def test_health_fnol_gets_health_checklist(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F093 (health variant)."""
        conn.execute(
            "INSERT INTO policies "
            "(policy_number, product_type, status, sum_insured, effective_date, "
            "expiry_date, created_at) VALUES ('POL-HEALTH-1', 'HEALTH', 'ACTIVE', "
            "'500000.00', '2025-01-01', '2026-12-31', datetime('now'))"
        )
        conn.commit()

        response = client.post(
            "/api/claims",
            json={
                "policy_number": "POL-HEALTH-1",
                "claim_type": "HEALTH",
                "incident_date": "2026-03-10",
                "claim_amount": "20000.00",
            },
            headers=_customer_headers(),
        )

        assert response.status_code == 201
        checklist_types = {c["document_type"] for c in response.json()["checklist"]}
        assert checklist_types == {"HOSPITAL_BILL", "DISCHARGE_SUMMARY"}

    def test_duplicate_fnol_returns_409_with_duplicate_claim_code(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F094."""
        _insert_policy(conn, "POL-DUP-1")
        payload = {
            "policy_number": "POL-DUP-1",
            "claim_type": "MOTOR",
            "incident_date": "2026-03-10",
            "claim_amount": "40000.00",
        }
        first = client.post("/api/claims", json=payload, headers=_customer_headers())
        assert first.status_code == 201

        second = client.post("/api/claims", json=payload, headers=_customer_headers())

        assert second.status_code == 409
        assert second.json()["error"]["code"] == "DUPLICATE_CLAIM"

    def test_policy_inactive_at_incident_date_returns_422(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F047 (closes the previously-unverifiable HTTP-layer gap)."""
        _insert_policy(conn, "POL-LAPSED-1", status=PolicyStatus.LAPSED.value)

        response = client.post(
            "/api/claims",
            json={
                "policy_number": "POL-LAPSED-1",
                "claim_type": "MOTOR",
                "incident_date": "2026-03-10",
                "claim_amount": "40000.00",
            },
            headers=_customer_headers(),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "POLICY_INACTIVE"

    def test_unknown_claim_type_returns_422_validation_error(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        _insert_policy(conn, "POL-BADTYPE-1")

        response = client.post(
            "/api/claims",
            json={
                "policy_number": "POL-BADTYPE-1",
                "claim_type": "PET",
                "incident_date": "2026-03-10",
                "claim_amount": "1000.00",
            },
            headers=_customer_headers(),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_malformed_claim_amount_returns_422_validation_error(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        _insert_policy(conn, "POL-BADAMT-1")

        response = client.post(
            "/api/claims",
            json={
                "policy_number": "POL-BADAMT-1",
                "claim_type": "MOTOR",
                "incident_date": "2026-03-10",
                "claim_amount": "not-a-number",
            },
            headers=_customer_headers(),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_assessor_role_is_forbidden(self, client: TestClient, conn: sqlite3.Connection) -> None:
        _insert_policy(conn, "POL-FORBID-1")

        response = client.post(
            "/api/claims",
            json={
                "policy_number": "POL-FORBID-1",
                "claim_type": "MOTOR",
                "incident_date": "2026-03-10",
                "claim_amount": "40000.00",
            },
            headers=_assessor_headers(),
        )

        assert response.status_code == 403
        assert response.json()["detail"]["error"]["code"] == "FORBIDDEN"


class TestGetClaim:
    def test_get_claim_includes_status_and_empty_missing_documents_once_verified(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F096."""
        _insert_policy(conn, "POL-TRACK-1")
        submit = client.post(
            "/api/claims",
            json={
                "policy_number": "POL-TRACK-1",
                "claim_type": "MOTOR",
                "incident_date": "2026-03-10",
                "claim_amount": "40000.00",
            },
            headers=_customer_headers(),
        )
        claim_id = submit.json()["claim_id"]

        response = client.get(f"/api/claims/{claim_id}", headers=_customer_headers())

        assert response.status_code == 200
        body = response.json()
        assert body["claim_id"] == claim_id
        assert body["claim_type"] == "MOTOR"
        assert body["status"] == "DOCS_PENDING"
        assert set(body["missing_documents"]) == {"POLICE_FIR", "INVOICE"}
        assert body["decision"] is None
        assert body["settlement"] is None
        assert body["parent_claim_id"] is None

    def test_get_claim_includes_decision_reason_code_once_decided(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F096: decision.reason_codes if decided."""
        _insert_policy(conn, "POL-TRACK-2")
        conn.execute(
            "INSERT INTO claims (policy_id, claim_type, incident_date, claim_amount, "
            "status, created_at, updated_at) SELECT id, 'MOTOR', '2026-03-10', "
            "'40000.00', 'MANUAL_REVIEW', datetime('now'), datetime('now') "
            "FROM policies WHERE policy_number = 'POL-TRACK-2'"
        )
        conn.commit()
        claim_id = conn.execute(
            "SELECT id FROM claims WHERE incident_date = '2026-03-10'"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO decisions (claim_id, outcome, reason_code, decided_by, created_at) "
            "VALUES (?, 'MANUAL_REVIEW', 'HIGH_VALUE_REVIEW', 'system', datetime('now'))",
            (claim_id,),
        )
        conn.commit()

        response = client.get(f"/api/claims/{claim_id}", headers=_customer_headers())

        assert response.status_code == 200
        decision = response.json()["decision"]
        assert decision is not None
        assert decision["outcome"] == "MANUAL_REVIEW"
        assert decision["reason_code"] == "HIGH_VALUE_REVIEW"

    def test_get_claim_includes_settlement_once_settled(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        _insert_policy(conn, "POL-TRACK-3")
        conn.execute(
            "INSERT INTO claims (policy_id, claim_type, incident_date, claim_amount, "
            "status, created_at, updated_at) SELECT id, 'MOTOR', '2026-03-10', "
            "'40000.00', 'AUTO_APPROVED', datetime('now'), datetime('now') "
            "FROM policies WHERE policy_number = 'POL-TRACK-3'"
        )
        conn.commit()
        claim_id = conn.execute(
            "SELECT id FROM claims WHERE incident_date = '2026-03-10'"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO assessments (claim_id, claim_amount, sum_insured, deductible, "
            "co_pay, payable_amount, created_at) VALUES (?, '40000.00', '500000.00', "
            "'5000.00', '0.00', '35000.00', datetime('now'))",
            (claim_id,),
        )
        conn.execute(
            "INSERT INTO decisions (claim_id, outcome, reason_code, decided_by, created_at) "
            "VALUES (?, 'AUTO_APPROVE', 'AUTO_APPROVED_LOW_RISK', 'system', datetime('now'))",
            (claim_id,),
        )
        conn.commit()
        settle(conn, claim_id)

        response = client.get(f"/api/claims/{claim_id}", headers=_customer_headers())

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "SETTLED"
        assert body["settlement"] is not None
        assert body["settlement"]["payout_amount"] == "35000.00"

    def test_unknown_claim_id_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/claims/999999", headers=_customer_headers())

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_assessor_can_also_read_a_claim(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """GET is not CUSTOMER-only, per api-contracts.md."""
        _insert_policy(conn, "POL-TRACK-4")
        submit = client.post(
            "/api/claims",
            json={
                "policy_number": "POL-TRACK-4",
                "claim_type": "MOTOR",
                "incident_date": "2026-03-10",
                "claim_amount": "40000.00",
            },
            headers=_customer_headers(),
        )
        claim_id = submit.json()["claim_id"]

        response = client.get(f"/api/claims/{claim_id}", headers=_assessor_headers())

        assert response.status_code == 200


class TestReopenClaim:
    def test_reopen_settled_claim_returns_201_with_sub_claim_and_parent(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F095."""
        _insert_policy(conn, "POL-REOPEN-1")
        conn.execute(
            "INSERT INTO claims (policy_id, claim_type, incident_date, claim_amount, "
            "status, created_at, updated_at) SELECT id, 'MOTOR', '2026-03-10', "
            "'40000.00', 'SETTLED', datetime('now'), datetime('now') "
            "FROM policies WHERE policy_number = 'POL-REOPEN-1'"
        )
        conn.commit()
        claim_id = conn.execute(
            "SELECT id FROM claims WHERE incident_date = '2026-03-10'"
        ).fetchone()["id"]

        response = client.post(f"/api/claims/{claim_id}/reopen", headers=_customer_headers())

        assert response.status_code == 201
        body = response.json()
        assert body["parent_claim_id"] == claim_id
        assert body["sub_claim_id"] != claim_id
        assert body["status"] == "INTAKE"

    def test_reopen_non_settled_claim_returns_409(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        _insert_policy(conn, "POL-REOPEN-2")
        submit = client.post(
            "/api/claims",
            json={
                "policy_number": "POL-REOPEN-2",
                "claim_type": "MOTOR",
                "incident_date": "2026-03-10",
                "claim_amount": "40000.00",
            },
            headers=_customer_headers(),
        )
        claim_id = submit.json()["claim_id"]

        response = client.post(f"/api/claims/{claim_id}/reopen", headers=_customer_headers())

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    def test_reopen_unknown_claim_id_returns_404(self, client: TestClient) -> None:
        response = client.post("/api/claims/999999/reopen", headers=_customer_headers())

        assert response.status_code == 404

    def test_assessor_role_is_forbidden(self, client: TestClient, conn: sqlite3.Connection) -> None:
        _insert_policy(conn, "POL-REOPEN-3")
        conn.execute(
            "INSERT INTO claims (policy_id, claim_type, incident_date, claim_amount, "
            "status, created_at, updated_at) SELECT id, 'MOTOR', '2026-03-10', "
            "'40000.00', 'SETTLED', datetime('now'), datetime('now') "
            "FROM policies WHERE policy_number = 'POL-REOPEN-3'"
        )
        conn.commit()
        claim_id = conn.execute(
            "SELECT id FROM claims WHERE incident_date = '2026-03-10'"
        ).fetchone()["id"]

        response = client.post(f"/api/claims/{claim_id}/reopen", headers=_assessor_headers())

        assert response.status_code == 403
