"""Customer claims API router: intake, tracking, dispute (E9-S1).

`POST /api/claims` (F093-F094), `GET /api/claims/{id}` (F096), and
`POST /api/claims/{id}/reopen` (F095) per `specs/design/api-contracts.md`
sec "Claims API (E9-S1)". Thin HTTP adapters over `fnol_intake_service.
submit_fnol()` (E4-S1/E4-S2/E4-S3) and `reopen_service.reopen()` (E7-S2);
`GET /api/claims/{id}` reads directly from the Claim/ClaimDocument/Decision/
Settlement repositories -- there is no dedicated read-model service for this,
matching how `workbench_router.get_workbench_detail()` (E9-S3) also composes
its response straight from repository reads.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends

from src.api.dependencies.auth import require_role
from src.api.dependencies.db import get_db_connection
from src.api.schemas.claims_schemas import (
    ChecklistEntry,
    ClaimDecisionBody,
    ClaimDetailResponse,
    ClaimSettlementBody,
    ReopenResponse,
    SubmitFnolRequest,
    SubmitFnolResponse,
)
from src.repositories.claim_document_repository import ClaimDocumentRepository
from src.repositories.claim_repository import ClaimRepository
from src.repositories.decision_repository import DecisionRepository
from src.repositories.settlement_repository import SettlementRepository
from src.services.fnol_intake_service import submit_fnol
from src.services.reopen_service import reopen
from src.types.enums import ClaimType, Role, VerificationStatus
from src.types.exceptions import ValidationError
from src.types.models import ActorContext

router = APIRouter(prefix="/api/claims", tags=["claims"])


@router.post("", status_code=201)
async def submit_claim(
    body: SubmitFnolRequest,
    conn: sqlite3.Connection = Depends(get_db_connection),  # noqa: B008
    actor: ActorContext = Depends(require_role(Role.CUSTOMER)),  # noqa: B008
) -> SubmitFnolResponse:
    """F093/F094: submit an FNOL; 201 with claim_id/status, or a mapped error.

    `claim_type`/`claim_amount` are validated into their real domain types
    here (422 `VALIDATION_ERROR` for an unrecognized `claim_type` or a
    malformed decimal amount) before ever reaching `submit_fnol()`, whose own
    `PolicyNotActiveException` (422) and `DuplicateClaimException` (409) are
    left to propagate to `error_handlers.py`'s registered handlers (F047,
    F050 -- previously unverified at the HTTP layer for lack of any route
    that could exercise them; this route closes that gap).
    """
    try:
        claim_type = ClaimType(body.claim_type)
    except ValueError as exc:
        raise ValidationError(f"Unknown claim_type: {body.claim_type!r}") from exc

    try:
        claim_amount = Decimal(body.claim_amount)
    except InvalidOperation as exc:
        raise ValidationError(f"Malformed claim_amount: {body.claim_amount!r}") from exc

    claim = submit_fnol(
        conn,
        policy_number=body.policy_number,
        claim_type=claim_type,
        incident_date=body.incident_date,
        claim_amount=claim_amount,
        actor_id=actor.actor_id,
    )

    checklist = ClaimDocumentRepository(conn).list_by_claim(claim.id)
    return SubmitFnolResponse(
        claim_id=claim.id,
        status=claim.status.value,
        checklist=[
            ChecklistEntry(
                document_type=document.document_type.value,
                verification_status=document.verification_status.value,
            )
            for document in checklist
        ],
    )


@router.get("/{claim_id}")
async def get_claim(
    claim_id: int,
    conn: sqlite3.Connection = Depends(get_db_connection),  # noqa: B008
    _actor: ActorContext = Depends(require_role(Role.CUSTOMER, Role.ASSESSOR, Role.ADMIN)),  # noqa: B008,E501
) -> ClaimDetailResponse:
    """F096: status, decision.reason_codes if decided, and missing_documents.

    `decision`/`settlement` are `None` until the corresponding row exists
    (api-contracts.md: "`decision` is `null` until a `Decision` row exists.
    `settlement` is `null` until a `Settlement` row exists").

    Raises `LookupError` (-> 404) if `claim_id` doesn't exist.
    """
    claim = ClaimRepository(conn).get_by_id(claim_id)
    if claim is None:
        raise LookupError(f"Claim {claim_id} not found.")

    documents = ClaimDocumentRepository(conn).list_by_claim(claim_id)
    missing_documents = [
        document.document_type.value
        for document in documents
        if document.verification_status == VerificationStatus.MISSING
    ]

    decision = DecisionRepository(conn).get_latest(claim_id)
    settlement = SettlementRepository(conn).get_latest_for_claim(claim_id)

    return ClaimDetailResponse(
        claim_id=claim.id,
        claim_type=claim.claim_type.value,
        status=claim.status.value,
        incident_date=claim.incident_date,
        claim_amount=str(claim.claim_amount),
        missing_documents=missing_documents,
        decision=(
            ClaimDecisionBody(
                outcome=decision.outcome.value,
                reason_code=decision.reason_code.value,
                decided_by=decision.decided_by,
                created_at=decision.created_at,
            )
            if decision is not None
            else None
        ),
        settlement=(
            ClaimSettlementBody(
                settlement_id=settlement.id,
                payout_amount=str(settlement.payout_amount),
                payment_reference=settlement.payment_reference,
                created_at=settlement.created_at,
            )
            if settlement is not None
            else None
        ),
        parent_claim_id=claim.parent_claim_id,
    )


@router.post("/{claim_id}/reopen", status_code=201)
async def reopen_claim(
    claim_id: int,
    conn: sqlite3.Connection = Depends(get_db_connection),  # noqa: B008
    actor: ActorContext = Depends(require_role(Role.CUSTOMER)),  # noqa: B008
) -> ReopenResponse:
    """F095: dispute a SETTLED claim; 201 with the new sub-claim id.

    Raises `LookupError` (-> 404) if `claim_id` doesn't exist, or
    `InvalidClaimStateException` (-> 409) if it is not currently `SETTLED`
    (E7-S2 AC4).
    """
    sub_claim = reopen(conn, claim_id, actor_id=actor.actor_id)
    return ReopenResponse(
        sub_claim_id=sub_claim.id,
        parent_claim_id=claim_id,
        status=sub_claim.status.value,
    )
