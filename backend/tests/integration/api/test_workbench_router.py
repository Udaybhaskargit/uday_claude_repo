"""Integration tests for the E9-S3 assessor workbench API (F100-F102).

Builds the real app via `create_app()` and overrides `get_app_config`/
`get_db_connection`/`get_assessment_rules_config` with real, migrated
fixtures, exercising the full request -> router -> service -> repository ->
DB round trip through `TestClient`, not mocks. Mirrors
`test_documents_router.py`'s fixture pattern. Claim state is advanced
directly through the Service layer (there is no HTTP FNOL/pipeline endpoint
yet, per E9-S1/Group I still being out of scope), the same way
`test_documents_router.py` seeds claims via `submit_fnol()` directly.
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
from src.api.dependencies.rules_config import get_assessment_rules_config
from src.config.app_config import AppConfig
from src.config.assessment_rules_config import AssessmentRulesConfig, ClaimTypeRules
from src.config.fraud_rules_config import FraudRulesConfig
from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.main import create_app
from src.services.decision_engine import run_decision
from src.services.document_checklist_service import check_documents_complete, verify_document
from src.services.fnol_intake_service import submit_fnol
from src.services.fraud_screening_service import run_fraud_screening
from src.types.enums import ClaimType, DocumentType, Role

REAL_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"

_ALWAYS_FLAG_CONFIG = FraudRulesConfig(rules=(), threshold=0)
_NEVER_FLAG_CONFIG = FraudRulesConfig(rules=(), threshold=1)

_LOW_CEILING_RULES = AssessmentRulesConfig(
    rules_by_claim_type={
        ClaimType.MOTOR: ClaimTypeRules(deductible=5000, co_pay_pct=0),
        ClaimType.HEALTH: ClaimTypeRules(deductible=1000, co_pay_pct=10),
        ClaimType.LIFE: ClaimTypeRules(deductible=0, co_pay_pct=0),
    },
    auto_approve_ceiling=100,
)


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
    app.dependency_overrides[get_assessment_rules_config] = lambda: _LOW_CEILING_RULES

    with TestClient(app) as test_client:
        yield test_client


def _assessor_headers(actor_id: str = "assessor-1") -> dict[str, str]:
    return {"X-Role": "ASSESSOR", "X-Actor-Id": actor_id}


def _admin_headers(actor_id: str = "admin-1") -> dict[str, str]:
    return {"X-Role": "ADMIN", "X-Actor-Id": actor_id}


def _customer_headers(actor_id: str = "customer-1") -> dict[str, str]:
    return {"X-Role": "CUSTOMER", "X-Actor-Id": actor_id}


def _insert_policy(conn: sqlite3.Connection, policy_number: str) -> None:
    conn.execute(
        "INSERT INTO policies "
        "(policy_number, product_type, status, sum_insured, effective_date, "
        "expiry_date, created_at) VALUES (?, 'MOTOR', 'ACTIVE', '500000.00', "
        "'2025-01-01', '2026-12-31', datetime('now'))",
        (policy_number,),
    )
    conn.commit()


def _claim_flagged_in_manual_review(conn: sqlite3.Connection, policy_number: str) -> int:
    """A fraud-flagged claim: MANUAL_REVIEW with no Assessment row."""
    _insert_policy(conn, policy_number)
    claim = submit_fnol(
        conn,
        policy_number=policy_number,
        claim_type=ClaimType.MOTOR,
        incident_date="2026-03-10",
        claim_amount=Decimal("40000.00"),
    )
    verify_document(conn, claim.id, DocumentType.POLICE_FIR)
    verify_document(conn, claim.id, DocumentType.INVOICE)
    check_documents_complete(conn, claim.id)
    run_fraud_screening(conn, claim.id, _ALWAYS_FLAG_CONFIG)
    return claim.id


def _claim_high_value_in_manual_review(conn: sqlite3.Connection, policy_number: str) -> int:
    """An unflagged, over-the-ceiling claim: MANUAL_REVIEW with an Assessment row."""
    _insert_policy(conn, policy_number)
    claim = submit_fnol(
        conn,
        policy_number=policy_number,
        claim_type=ClaimType.MOTOR,
        incident_date="2026-03-10",
        claim_amount=Decimal("40000.00"),
    )
    verify_document(conn, claim.id, DocumentType.POLICE_FIR)
    verify_document(conn, claim.id, DocumentType.INVOICE)
    check_documents_complete(conn, claim.id)
    run_fraud_screening(conn, claim.id, _NEVER_FLAG_CONFIG)
    run_decision(conn, claim.id, _LOW_CEILING_RULES)
    return claim.id


class TestFraudAlerts:
    def test_lists_only_flagged_claims(self, client: TestClient, conn: sqlite3.Connection) -> None:
        """F100."""
        flagged_id = _claim_flagged_in_manual_review(conn, "POL-FLAGGED")
        _claim_high_value_in_manual_review(conn, "POL-CLEAN")

        response = client.get("/api/claims/fraud-alerts", headers=_assessor_headers())

        assert response.status_code == 200
        claims = response.json()["claims"]
        assert [c["claim_id"] for c in claims] == [flagged_id]
        assert claims[0]["claim_type"] == "MOTOR"
        assert claims[0]["fraud_score"] >= 0
        assert isinstance(claims[0]["triggered_rules"], list)

    def test_empty_when_no_claims_flagged(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F100."""
        _claim_high_value_in_manual_review(conn, "POL-CLEAN-ONLY")

        response = client.get("/api/claims/fraud-alerts", headers=_assessor_headers())

        assert response.status_code == 200
        assert response.json()["claims"] == []


class TestWorkbenchDetail:
    def test_high_value_claim_includes_assessment_and_suggested_reason_code(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F101."""
        claim_id = _claim_high_value_in_manual_review(conn, "POL-HV")

        response = client.get(f"/api/claims/{claim_id}/workbench", headers=_assessor_headers())

        assert response.status_code == 200
        body = response.json()
        assert body["claim_id"] == claim_id
        assert body["status"] == "MANUAL_REVIEW"
        assert body["fraud_screening"]["flagged"] is False
        assert isinstance(body["fraud_screening"]["breakdown"], list)
        assert body["assessment"]["payable_amount"] == "35000.00"
        assert body["suggested_reason_code"] == "HIGH_VALUE_REVIEW"

    def test_fraud_flagged_claim_has_no_assessment_or_suggestion(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F101: a claim that never entered ASSESSMENT has null assessment/suggestion."""
        claim_id = _claim_flagged_in_manual_review(conn, "POL-FLAGGED-WB")

        response = client.get(f"/api/claims/{claim_id}/workbench", headers=_assessor_headers())

        assert response.status_code == 200
        body = response.json()
        assert body["fraud_screening"]["flagged"] is True
        assert body["assessment"] is None
        assert body["suggested_reason_code"] is None

    def test_unknown_claim_id_is_rejected_with_404(self, client: TestClient) -> None:
        response = client.get("/api/claims/999999/workbench", headers=_assessor_headers())

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestPostDecision:
    def test_assessor_approve_decision_persists_and_moves_claim(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        """F102."""
        claim_id = _claim_flagged_in_manual_review(conn, "POL-DECIDE-1")

        response = client.post(
            f"/api/claims/{claim_id}/decision",
            json={"outcome": "AUTO_APPROVE", "reason_code": "AUTO_APPROVED_LOW_RISK"},
            headers=_assessor_headers("assessor-42"),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["claim_id"] == claim_id
        assert body["decision"]["outcome"] == "AUTO_APPROVE"
        assert body["decision"]["decided_by"] == "assessor-42"
        assert body["claim_status"] == "AUTO_APPROVED"

    def test_invalid_outcome_is_rejected_with_422(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        claim_id = _claim_flagged_in_manual_review(conn, "POL-DECIDE-2")

        response = client.post(
            f"/api/claims/{claim_id}/decision",
            json={"outcome": "NOT_A_REAL_OUTCOME", "reason_code": "AUTO_APPROVED_LOW_RISK"},
            headers=_assessor_headers(),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_reason_code_is_rejected_with_422(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        claim_id = _claim_flagged_in_manual_review(conn, "POL-DECIDE-BAD-REASON")

        response = client.post(
            f"/api/claims/{claim_id}/decision",
            json={"outcome": "AUTO_APPROVE", "reason_code": "NOT_A_REAL_REASON"},
            headers=_assessor_headers(),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_claim_not_in_manual_review_is_rejected_with_409(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        claim_id = _claim_high_value_in_manual_review(conn, "POL-DECIDE-3")
        # Move it out of MANUAL_REVIEW first.
        first = client.post(
            f"/api/claims/{claim_id}/decision",
            json={"outcome": "REJECT", "reason_code": "FRAUD_FLAG"},
            headers=_assessor_headers(),
        )
        assert first.status_code == 200

        second = client.post(
            f"/api/claims/{claim_id}/decision",
            json={"outcome": "AUTO_APPROVE", "reason_code": "AUTO_APPROVED_LOW_RISK"},
            headers=_assessor_headers(),
        )

        assert second.status_code == 409
        assert second.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    def test_admin_role_is_forbidden(self, client: TestClient, conn: sqlite3.Connection) -> None:
        """POST /decision requires ASSESSOR specifically, unlike the two GET routes."""
        claim_id = _claim_flagged_in_manual_review(conn, "POL-DECIDE-ADMIN")

        response = client.post(
            f"/api/claims/{claim_id}/decision",
            json={"outcome": "AUTO_APPROVE", "reason_code": "AUTO_APPROVED_LOW_RISK"},
            headers=_admin_headers(),
        )

        assert response.status_code == 403
        assert response.json()["detail"]["error"]["code"] == "FORBIDDEN"


class TestWorkbenchRoutesForbidCustomer:
    def test_customer_role_is_forbidden_on_all_three_routes(
        self, client: TestClient, conn: sqlite3.Connection
    ) -> None:
        claim_id = _claim_flagged_in_manual_review(conn, "POL-CUST")
        headers = _customer_headers()

        alerts = client.get("/api/claims/fraud-alerts", headers=headers)
        detail = client.get(f"/api/claims/{claim_id}/workbench", headers=headers)
        decision = client.post(
            f"/api/claims/{claim_id}/decision",
            json={"outcome": "AUTO_APPROVE", "reason_code": "AUTO_APPROVED_LOW_RISK"},
            headers=headers,
        )

        for response in (alerts, detail, decision):
            assert response.status_code == 403
            assert response.json()["detail"]["error"]["code"] == "FORBIDDEN"
