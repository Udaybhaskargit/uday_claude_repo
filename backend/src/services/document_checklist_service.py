"""Document checklist verification service (Service layer, E5-S1, AC-03).

Enforces that a claim cannot leave DOCS_PENDING until every checklist item
for its own claim type is VERIFIED. Reuses `fnol_intake_service.CHECKLISTS`
as the single source of truth for which `DocumentType`s belong to which
`ClaimType` (data-models.md sec 2.3), rather than redefining a second
mapping that could drift out of sync with the one E4-S1 seeds at intake.
"""

from __future__ import annotations

import sqlite3

from src.repositories.claim_document_repository import ClaimDocumentRepository
from src.repositories.claim_repository import ClaimRepository
from src.services.fnol_intake_service import CHECKLISTS
from src.types.enums import ClaimEvent, DocumentType, VerificationStatus
from src.types.exceptions import ValidationError
from src.types.models import ClaimDocument


def check_documents_complete(
    conn: sqlite3.Connection, claim_id: int, actor_id: str | None = None
) -> bool:
    """True iff every checklist document for `claim_id`'s claim type is VERIFIED.

    Only the document types in that claim's *own* `CHECKLISTS` entry are
    considered (AC3) -- e.g. a health claim's completeness never depends on
    motor/life document types, since those rows are never even attached to
    a health claim by `fnol_intake_service.submit_fnol()`.

    If every checklist item is VERIFIED, this also applies
    `ClaimEvent.DOCS_VERIFIED`, transitioning the claim from DOCS_PENDING to
    FRAUD_SCREENING (AC2) -- "checked" and "gated" are described together in
    the story as one action. If any item is still MISSING, no transition is
    attempted and the claim remains DOCS_PENDING (AC1).

    Raises `LookupError` if no claim with `claim_id` exists.
    """
    claim_repository = ClaimRepository(conn)
    claim = claim_repository.get_by_id(claim_id)
    if claim is None:
        raise LookupError(f"Claim {claim_id} not found.")

    required_types = set(CHECKLISTS[claim.claim_type])
    documents = ClaimDocumentRepository(conn).list_by_claim(claim_id)
    verified_types = {
        document.document_type
        for document in documents
        if document.verification_status == VerificationStatus.VERIFIED
    }

    all_verified = required_types <= verified_types
    if all_verified:
        claim_repository.apply_transition(claim_id, ClaimEvent.DOCS_VERIFIED, actor_id)

    return all_verified


def list_outstanding_documents(conn: sqlite3.Connection, claim_id: int) -> list[DocumentType]:
    """Return the claim-type checklist entries for `claim_id` still MISSING.

    Used by the E9-S2 pending-documents queue (`documents_router.py`) to
    report, per claim, exactly which of its own checklist items remain
    outstanding -- reusing the same `CHECKLISTS`/verified-set logic as
    `check_documents_complete()` rather than re-deriving it.

    Raises `LookupError` if no claim with `claim_id` exists.
    """
    claim = ClaimRepository(conn).get_by_id(claim_id)
    if claim is None:
        raise LookupError(f"Claim {claim_id} not found.")

    required_types = CHECKLISTS[claim.claim_type]
    documents = ClaimDocumentRepository(conn).list_by_claim(claim_id)
    verified_types = {
        document.document_type
        for document in documents
        if document.verification_status == VerificationStatus.VERIFIED
    }
    return [doc_type for doc_type in required_types if doc_type not in verified_types]


def verify_document(
    conn: sqlite3.Connection, claim_id: int, document_type: DocumentType
) -> ClaimDocument:
    """Mark one checklist row VERIFIED, after confirming it belongs to this claim.

    Raises `LookupError` if `claim_id` does not exist, or `ValidationError`
    (AC4) if `document_type` is not part of the claim's own claim-type
    checklist -- e.g. attempting to verify HOSPITAL_BILL on a motor claim.
    """
    claim = ClaimRepository(conn).get_by_id(claim_id)
    if claim is None:
        raise LookupError(f"Claim {claim_id} not found.")

    checklist = CHECKLISTS[claim.claim_type]
    if document_type not in checklist:
        raise ValidationError(
            f"{document_type.value} is not part of the {claim.claim_type.value} "
            f"checklist for claim {claim_id}."
        )

    document_repository = ClaimDocumentRepository(conn)
    document_repository.mark_verified(claim_id, document_type)

    updated = next(
        document
        for document in document_repository.list_by_claim(claim_id)
        if document.document_type == document_type
    )
    return updated
