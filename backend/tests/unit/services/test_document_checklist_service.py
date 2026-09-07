"""Unit tests for `src.services.document_checklist_service` (E5-S1, F051-F054)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.repositories.claim_repository import ClaimRepository
from src.services.document_checklist_service import (
    check_documents_complete,
    verify_document,
)
from src.services.fnol_intake_service import submit_fnol
from src.types.enums import ClaimStatus, ClaimType, DocumentType, VerificationStatus
from src.types.exceptions import ValidationError

REAL_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def _seed_connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "claimflow.db"
    conn = get_connection(str(db_path))
    run_migrations(conn, str(REAL_MIGRATIONS_DIR))
    return conn


def _insert_policy(conn: sqlite3.Connection, *, policy_number: str = "POL-001") -> None:
    conn.execute(
        "INSERT INTO policies "
        "(policy_number, product_type, status, sum_insured, effective_date, "
        "expiry_date, created_at) VALUES (?, 'MOTOR', 'ACTIVE', '500000.00', "
        "'2025-01-01', '2026-12-31', datetime('now'))",
        (policy_number,),
    )
    conn.commit()


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = _seed_connection(tmp_path)
    yield connection
    connection.close()


@pytest.fixture
def motor_claim_id(conn: sqlite3.Connection) -> int:
    _insert_policy(conn, policy_number="POL-MOTOR")
    claim = submit_fnol(
        conn,
        policy_number="POL-MOTOR",
        claim_type=ClaimType.MOTOR,
        incident_date="2026-03-10",
        claim_amount=Decimal("40000.00"),
    )
    return claim.id


@pytest.fixture
def health_claim_id(conn: sqlite3.Connection) -> int:
    _insert_policy(conn, policy_number="POL-HEALTH")
    claim = submit_fnol(
        conn,
        policy_number="POL-HEALTH",
        claim_type=ClaimType.HEALTH,
        incident_date="2026-04-01",
        claim_amount=Decimal("15000.00"),
    )
    return claim.id


class TestIncompleteChecklist:
    def test_missing_document_returns_false_and_claim_stays_docs_pending(
        self, conn: sqlite3.Connection, motor_claim_id: int
    ) -> None:
        """F051: POLICE_FIR still MISSING -> False, claim remains DOCS_PENDING."""
        verify_document(conn, motor_claim_id, DocumentType.INVOICE)

        result = check_documents_complete(conn, motor_claim_id)

        assert result is False
        claim = ClaimRepository(conn).get_by_id(motor_claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.DOCS_PENDING


class TestCompleteChecklist:
    def test_all_verified_returns_true_and_transitions_to_fraud_screening(
        self, conn: sqlite3.Connection, motor_claim_id: int
    ) -> None:
        """F052: both POLICE_FIR and INVOICE VERIFIED -> True, FRAUD_SCREENING."""
        verify_document(conn, motor_claim_id, DocumentType.POLICE_FIR)
        verify_document(conn, motor_claim_id, DocumentType.INVOICE)

        result = check_documents_complete(conn, motor_claim_id)

        assert result is True
        claim = ClaimRepository(conn).get_by_id(motor_claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.FRAUD_SCREENING

        transition_rows = conn.execute(
            "SELECT * FROM claim_state_transitions WHERE claim_id = ? ORDER BY id DESC LIMIT 1",
            (motor_claim_id,),
        ).fetchall()
        assert transition_rows[0]["event"] == "DOCS_VERIFIED"
        assert transition_rows[0]["to_state"] == ClaimStatus.FRAUD_SCREENING.value


class TestHealthChecklistScoping:
    def test_only_health_document_types_are_considered(
        self, conn: sqlite3.Connection, health_claim_id: int
    ) -> None:
        """F053: only HOSPITAL_BILL/DISCHARGE_SUMMARY matter for a health claim."""
        verify_document(conn, health_claim_id, DocumentType.HOSPITAL_BILL)
        assert check_documents_complete(conn, health_claim_id) is False

        verify_document(conn, health_claim_id, DocumentType.DISCHARGE_SUMMARY)
        assert check_documents_complete(conn, health_claim_id) is True

        claim = ClaimRepository(conn).get_by_id(health_claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.FRAUD_SCREENING


class TestVerifyDocumentValidation:
    def test_verifying_a_document_outside_the_claims_checklist_raises(
        self, conn: sqlite3.Connection, motor_claim_id: int
    ) -> None:
        """F054: HOSPITAL_BILL is not part of a motor claim's checklist."""
        with pytest.raises(ValidationError):
            verify_document(conn, motor_claim_id, DocumentType.HOSPITAL_BILL)

    def test_verify_document_returns_the_updated_document(
        self, conn: sqlite3.Connection, motor_claim_id: int
    ) -> None:
        updated = verify_document(conn, motor_claim_id, DocumentType.POLICE_FIR)

        assert updated.document_type == DocumentType.POLICE_FIR
        assert updated.verification_status == VerificationStatus.VERIFIED


class TestUnknownClaimId:
    def test_check_documents_complete_raises_lookup_error(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(LookupError):
            check_documents_complete(conn, 999999)

    def test_verify_document_raises_lookup_error(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(LookupError):
            verify_document(conn, 999999, DocumentType.POLICE_FIR)
