"""Integration tests for the E9-S2 document verification API (F097-F099).

Builds the real app via `create_app()` and overrides `get_app_config`/
`get_db_connection` with a real, migrated SQLite connection, exercising the
full request -> router -> service -> repository -> DB round trip through
`TestClient`, not mocks. Mirrors `test_admin_router.py`'s fixture pattern.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from decimal import Decimal
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
from src.services.fnol_intake_service import submit_fnol
from src.types.enums import ClaimType, Role

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


def _assessor_headers(actor_id: str = "assessor-1") -> dict[str, str]:
    return {"X-Role": "ASSESSOR", "X-Actor-Id": actor_id}


def _customer_headers(actor_id: str = "customer-1") -> dict[str, str]:
    return {"X-Role": "CUSTOMER", "X-Actor-Id": actor_id}


def _insert_policy(conn: sqlite3.Connection, policy_number: str = "POL-001") -> None:
    conn.execute(
        "INSERT INTO policies "
        "(policy_number, product_type, status, sum_insured, effective_date, "
        "expiry_date, created_at) VALUES (?, 'MOTOR', 'ACTIVE', '500000.00', "
        "'2025-01-01', '2026-12-31', datetime('now'))",
        (policy_number,),
    )
    conn.commit()


def _submit_motor_claim(conn: sqlite3.Connection, policy_number: str = "POL-001") -> int:
    _insert_policy(conn, policy_number=policy_number)
    claim = submit_fnol(
        conn,
        policy_number=policy_number,
        claim_type=ClaimType.MOTOR,
        incident_date="2026-03-10",
        claim_amount=Decimal("40000.00"),
    )
    return claim.id


class TestListPendingDocuments:
    def test_lists_only_docs_pending_claims_with_outstanding_items(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F097."""
        claim_id = _submit_motor_claim(conn)

        response = client.get("/api/claims/documents/pending", headers=_assessor_headers())

        assert response.status_code == 200
        claims = response.json()["claims"]
        assert len(claims) == 1
        assert claims[0]["claim_id"] == claim_id
        assert claims[0]["claim_type"] == "MOTOR"
        assert sorted(claims[0]["outstanding_documents"]) == ["INVOICE", "POLICE_FIR"]

    def test_excludes_claims_not_in_docs_pending(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F097."""
        _insert_policy(conn, policy_number="POL-SETTLED")
        conn.execute(
            "INSERT INTO claims (policy_id, claim_type, incident_date, claim_amount, "
            "status, created_at, updated_at) VALUES "
            "(1, 'MOTOR', '2026-01-01', '10000.00', 'SETTLED', datetime('now'), datetime('now'))"
        )
        conn.commit()

        response = client.get("/api/claims/documents/pending", headers=_assessor_headers())

        assert response.status_code == 200
        assert response.json()["claims"] == []


class TestPatchDocument:
    def test_verifying_last_item_advances_claim_to_fraud_screening(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F098."""
        claim_id = _submit_motor_claim(conn)

        first = client.patch(
            f"/api/claims/{claim_id}/documents/POLICE_FIR",
            json={"verification_status": "VERIFIED"},
            headers=_assessor_headers(),
        )
        assert first.status_code == 200
        assert first.json()["verification_status"] == "VERIFIED"
        assert first.json()["claim_status"] == "DOCS_PENDING"

        second = client.patch(
            f"/api/claims/{claim_id}/documents/INVOICE",
            json={"verification_status": "VERIFIED"},
            headers=_assessor_headers(),
        )
        assert second.status_code == 200
        assert second.json()["claim_status"] == "FRAUD_SCREENING"

        follow_up = client.get("/api/claims/documents/pending", headers=_assessor_headers())
        assert follow_up.json()["claims"] == []

    def test_unknown_document_type_for_claim_type_is_rejected_with_422(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        claim_id = _submit_motor_claim(conn)

        response = client.patch(
            f"/api/claims/{claim_id}/documents/HOSPITAL_BILL",
            json={"verification_status": "VERIFIED"},
            headers=_assessor_headers(),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_unsupported_verification_status_is_rejected_with_422(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        claim_id = _submit_motor_claim(conn)

        response = client.patch(
            f"/api/claims/{claim_id}/documents/POLICE_FIR",
            json={"verification_status": "MISSING"},
            headers=_assessor_headers(),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_unknown_claim_id_is_rejected_with_404(self, client: TestClient) -> None:
        response = client.patch(
            "/api/claims/999999/documents/POLICE_FIR",
            json={"verification_status": "VERIFIED"},
            headers=_assessor_headers(),
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestDocumentRoutesForbidCustomer:
    def test_customer_role_is_forbidden_on_both_routes(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F099."""
        claim_id = _submit_motor_claim(conn)
        headers = _customer_headers()

        get_pending = client.get("/api/claims/documents/pending", headers=headers)
        patch_doc = client.patch(
            f"/api/claims/{claim_id}/documents/POLICE_FIR",
            json={"verification_status": "VERIFIED"},
            headers=headers,
        )

        for response in (get_pending, patch_doc):
            assert response.status_code == 403
            assert response.json()["detail"]["error"]["code"] == "FORBIDDEN"
