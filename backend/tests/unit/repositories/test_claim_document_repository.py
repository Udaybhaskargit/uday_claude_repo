"""Smoke tests for `src.repositories.claim_document_repository` (E3-S3 scope).

Kept minimal per the story: the full checklist-verification logic belongs to
E5-S1. This file only proves basic insert/list plumbing works against a real
migrated SQLite DB.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.repositories.claim_document_repository import ClaimDocumentRepository
from src.types.enums import ClaimStatus, ClaimType, DocumentType, PolicyStatus, VerificationStatus

REAL_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def _seed_connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "claimflow.db"
    conn = get_connection(str(db_path))
    run_migrations(conn, str(REAL_MIGRATIONS_DIR))
    return conn


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = _seed_connection(tmp_path)
    yield connection
    connection.close()


@pytest.fixture
def claim_id(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        "INSERT INTO policies "
        "(policy_number, product_type, status, sum_insured, effective_date, "
        "expiry_date, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        ("POL-001", ClaimType.MOTOR.value, PolicyStatus.ACTIVE.value, "500000.00",
         "2025-01-01", "2025-12-31"),
    )
    policy_id = cursor.lastrowid
    cursor = conn.execute(
        "INSERT INTO claims "
        "(policy_id, claim_type, incident_date, claim_amount, status, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (policy_id, ClaimType.MOTOR.value, "2026-01-15", "10000.00", ClaimStatus.INTAKE.value),
    )
    conn.commit()
    new_claim_id = cursor.lastrowid
    assert new_claim_id is not None
    return new_claim_id


class TestInsert:
    def test_insert_returns_id_and_defaults_verification_status_to_missing(
        self, conn: sqlite3.Connection, claim_id: int
    ) -> None:
        repo = ClaimDocumentRepository(conn)

        document_id = repo.insert(claim_id, DocumentType.POLICE_FIR)

        assert isinstance(document_id, int)
        row = conn.execute(
            "SELECT * FROM claim_documents WHERE id = ?", (document_id,)
        ).fetchone()
        assert row is not None
        assert row["claim_id"] == claim_id
        assert row["document_type"] == DocumentType.POLICE_FIR.value
        assert row["verification_status"] == VerificationStatus.MISSING.value


class TestListByClaim:
    def test_list_by_claim_returns_typed_documents_for_that_claim(
        self, conn: sqlite3.Connection, claim_id: int
    ) -> None:
        repo = ClaimDocumentRepository(conn)
        repo.insert(claim_id, DocumentType.POLICE_FIR)
        repo.insert(claim_id, DocumentType.INVOICE)

        documents = repo.list_by_claim(claim_id)

        assert len(documents) == 2
        document_types = {doc.document_type for doc in documents}
        assert document_types == {DocumentType.POLICE_FIR, DocumentType.INVOICE}
        assert all(doc.claim_id == claim_id for doc in documents)
        assert all(doc.verification_status == VerificationStatus.MISSING for doc in documents)

    def test_list_by_claim_returns_empty_list_when_no_documents(
        self, conn: sqlite3.Connection, claim_id: int
    ) -> None:
        repo = ClaimDocumentRepository(conn)

        assert repo.list_by_claim(claim_id) == []


class TestMarkVerified:
    """Group F (E5-S1) addition: toggles one checklist row to VERIFIED."""

    def test_mark_verified_flips_status_for_matching_row_only(
        self, conn: sqlite3.Connection, claim_id: int
    ) -> None:
        repo = ClaimDocumentRepository(conn)
        repo.insert(claim_id, DocumentType.POLICE_FIR)
        repo.insert(claim_id, DocumentType.INVOICE)

        repo.mark_verified(claim_id, DocumentType.POLICE_FIR)

        documents = {d.document_type: d.verification_status for d in repo.list_by_claim(claim_id)}
        assert documents[DocumentType.POLICE_FIR] == VerificationStatus.VERIFIED
        assert documents[DocumentType.INVOICE] == VerificationStatus.MISSING

    def test_mark_verified_is_a_noop_for_a_non_matching_row(
        self, conn: sqlite3.Connection, claim_id: int
    ) -> None:
        repo = ClaimDocumentRepository(conn)
        repo.insert(claim_id, DocumentType.POLICE_FIR)

        repo.mark_verified(claim_id, DocumentType.HOSPITAL_BILL)

        documents = repo.list_by_claim(claim_id)
        assert len(documents) == 1
        assert documents[0].verification_status == VerificationStatus.MISSING
