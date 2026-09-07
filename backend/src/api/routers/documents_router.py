"""Document verification API router (E9-S2).

Both routes require `X-Role: ASSESSOR` or `X-Role: ADMIN` (per
`specs/design/api-contracts.md` sec "Document Verification API") --
`CUSTOMER` gets 403 before either handler body runs (F099). Wired to the
E5-S1 `document_checklist_service` module: this router is a thin HTTP
adapter over `list_outstanding_documents()`/`verify_document()`/
`check_documents_complete()`, with no business logic of its own.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from src.api.dependencies.auth import require_role
from src.api.dependencies.db import get_db_connection
from src.api.schemas.documents_schemas import (
    DocumentPatchRequest,
    DocumentPatchResponse,
    PendingDocsClaim,
    PendingDocsResponse,
)
from src.repositories.claim_repository import ClaimRepository
from src.services.document_checklist_service import (
    check_documents_complete,
    list_outstanding_documents,
    verify_document,
)
from src.types.enums import ClaimStatus, ClaimType, DocumentType, Role, VerificationStatus
from src.types.exceptions import ValidationError
from src.types.models import ActorContext

router = APIRouter(prefix="/api/claims", tags=["documents"])


@router.get("/documents/pending")
async def list_pending_documents(
    claim_type: ClaimType | None = None,
    conn: sqlite3.Connection = Depends(get_db_connection),  # noqa: B008
    _actor: ActorContext = Depends(require_role(Role.ASSESSOR, Role.ADMIN)),  # noqa: B008
) -> PendingDocsResponse:
    """F097: claims currently in DOCS_PENDING with their outstanding checklist items."""
    claims = ClaimRepository(conn).list_by_status_and_product(ClaimStatus.DOCS_PENDING, claim_type)
    return PendingDocsResponse(
        claims=[
            PendingDocsClaim(
                claim_id=claim.id,
                claim_type=claim.claim_type.value,
                outstanding_documents=[
                    doc_type.value for doc_type in list_outstanding_documents(conn, claim.id)
                ],
            )
            for claim in claims
        ]
    )


@router.patch("/{claim_id}/documents/{document_type}")
async def patch_document(
    claim_id: int,
    document_type: DocumentType,
    body: DocumentPatchRequest,
    conn: sqlite3.Connection = Depends(get_db_connection),  # noqa: B008
    _actor: ActorContext = Depends(require_role(Role.ASSESSOR, Role.ADMIN)),  # noqa: B008
) -> DocumentPatchResponse:
    """F098: mark a checklist item VERIFIED, auto-advancing once all are.

    `verify_document()` raises `ValidationError` (422) if `document_type`
    isn't part of the claim's own checklist (E5-S1 AC4), and `LookupError`
    (404) if `claim_id` doesn't exist -- both propagate through
    `error_handlers.py` unchanged. Only `"VERIFIED"` is a supported request
    value: no `ClaimDocumentRepository` method exists to flip a row back to
    `MISSING` (neither E5-S1 nor E3-S4 asked for one), so any other value is
    rejected with the same typed `ValidationError` rather than silently
    no-op'd.
    """
    if body.verification_status != VerificationStatus.VERIFIED.value:
        raise ValidationError(
            f"Unsupported verification_status: {body.verification_status!r}. "
            "Only 'VERIFIED' is supported."
        )

    document = verify_document(conn, claim_id, document_type)
    check_documents_complete(conn, claim_id)

    updated_claim = ClaimRepository(conn).get_by_id(claim_id)
    assert updated_claim is not None
    return DocumentPatchResponse(
        claim_id=claim_id,
        document_type=document.document_type.value,
        verification_status=document.verification_status.value,
        claim_status=updated_claim.status.value,
    )
