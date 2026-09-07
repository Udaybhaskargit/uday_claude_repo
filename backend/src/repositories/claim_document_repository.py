"""Claim document repository (Repository layer, E3-S3 scope).

Minimal data access for the `claim_documents` table -- basic insert and
per-claim listing. This exists in E3-S3 per the folder-structure ownership
map; the full checklist-verification workflow (seeding the checklist per
claim type, toggling verification status, completeness checks) is E5-S1's
job and is intentionally NOT implemented here.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from src.types.enums import DocumentType, VerificationStatus
from src.types.models import ClaimDocument


class ClaimDocumentRepository:
    """SQLite-backed data access for `ClaimDocument` entities."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert(self, claim_id: int, document_type: DocumentType) -> int:
        """Insert a checklist row for `claim_id`, defaulting to MISSING."""
        now = datetime.now(UTC).isoformat()
        cursor = self._connection.execute(
            "INSERT INTO claim_documents "
            "(claim_id, document_type, verification_status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (claim_id, document_type.value, VerificationStatus.MISSING.value, now, now),
        )
        self._connection.commit()
        document_id = cursor.lastrowid
        assert document_id is not None
        return document_id

    def mark_verified(self, claim_id: int, document_type: DocumentType) -> None:
        """Flip one checklist row from MISSING to VERIFIED (E5-S1).

        Unlike the append-only audit repositories, `ClaimDocument` rows are
        genuinely mutable -- a checklist entry's status is toggled in place
        as the assessor verifies each document, rather than persisting a new
        row per change. `backend/tests/architecture/test_audit_repositories_
        insert_only.py` scopes its no-update()/delete() rule to the 5 named
        audit entities (FraudScreening/Assessment/Decision/Settlement/
        AdminOverride) and does not include `ClaimDocument`, so this UPDATE
        does not violate that architectural invariant.

        A no-op (no rows affected, no error) if `claim_id`/`document_type`
        does not match an existing row -- the caller (`document_checklist_
        service.verify_document`) is responsible for validating that the
        document type belongs to the claim's own checklist before calling
        this (E5-S1 AC4); this method itself trusts its inputs.
        """
        now = datetime.now(UTC).isoformat()
        self._connection.execute(
            "UPDATE claim_documents SET verification_status = ?, updated_at = ? "
            "WHERE claim_id = ? AND document_type = ?",
            (VerificationStatus.VERIFIED.value, now, claim_id, document_type.value),
        )
        self._connection.commit()

    def list_by_claim(self, claim_id: int) -> list[ClaimDocument]:
        """Return every checklist row attached to `claim_id`."""
        rows = self._connection.execute(
            "SELECT id, claim_id, document_type, verification_status, "
            "created_at, updated_at FROM claim_documents WHERE claim_id = ? "
            "ORDER BY id",
            (claim_id,),
        ).fetchall()
        return [
            ClaimDocument(
                id=row["id"],
                claim_id=row["claim_id"],
                document_type=DocumentType(row["document_type"]),
                verification_status=VerificationStatus(row["verification_status"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
