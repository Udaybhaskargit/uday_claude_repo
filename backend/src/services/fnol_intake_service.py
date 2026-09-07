"""FNOL intake service (Service layer, E4-S1).

Accepts a first-notice-of-loss submission (policy, claim type, incident date,
claim amount) and creates the initial `Claim` plus its per-claim-type
`ClaimDocument` checklist rows (AC1-AC3), then moves the claim from INTAKE to
DOCS_PENDING once the checklist is attached (AC4).

The checklist mapping hardcoded below only seeds the initial MISSING rows for
the claim's product type -- the full checklist-verification workflow
(toggling VERIFIED, completeness checks) is E5-S1's job, not this story's.

Note on atomicity: `ClaimRepository.create()`, `ClaimDocumentRepository.insert()`,
and `ClaimRepository.apply_transition()` each commit their own write
individually (see their docstrings). Wrapping these calls in an additional
`with conn:` block here would not add real atomicity -- the inner commits
already fire before an outer block could roll anything back -- so no such
wrapper is added; a failure partway through does leave a partially-built
claim, which is consistent with how every other multi-step workflow in this
codebase already behaves given the repositories' individual commit points.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from src.repositories.claim_document_repository import ClaimDocumentRepository
from src.repositories.claim_repository import ClaimRepository
from src.types.enums import ClaimEvent, ClaimType, DocumentType
from src.types.exceptions import UnknownClaimTypeError
from src.types.models import Claim

CHECKLISTS: dict[ClaimType, tuple[DocumentType, ...]] = {
    ClaimType.MOTOR: (DocumentType.POLICE_FIR, DocumentType.INVOICE),
    ClaimType.HEALTH: (DocumentType.HOSPITAL_BILL, DocumentType.DISCHARGE_SUMMARY),
    ClaimType.LIFE: (DocumentType.DEATH_CERTIFICATE,),
}


def _checklist_for(claim_type: ClaimType) -> tuple[DocumentType, ...]:
    """Look up the checklist document types for `claim_type`.

    Raises `UnknownClaimTypeError` rather than silently returning an empty
    checklist if `claim_type` isn't one of MOTOR/HEALTH/LIFE. The `ClaimType`
    enum should prevent this in practice, but the lookup fails loudly instead
    of masking a caller bug.
    """
    try:
        return CHECKLISTS[claim_type]
    except KeyError:
        raise UnknownClaimTypeError(str(claim_type)) from None


def submit_fnol(
    conn: sqlite3.Connection,
    policy_id: int,
    claim_type: ClaimType,
    incident_date: str,
    claim_amount: Decimal,
    actor_id: str | None = None,
) -> Claim:
    """Create a claim and its checklist, then transition it to DOCS_PENDING.

    1. Looks up the checklist document types for `claim_type`, raising
       `UnknownClaimTypeError` first if there is no mapping -- so an
       unrecognized claim type never creates a claim row at all.
    2. Creates the claim row via `ClaimRepository.create()`, which starts at
       `status=INTAKE` (AC4, first half).
    3. Attaches one `ClaimDocument` row per checklist entry via
       `ClaimDocumentRepository.insert()`, each defaulting to
       `VerificationStatus.MISSING` (AC1-AC3).
    4. Applies `ClaimEvent.ATTACH_CHECKLIST`, transitioning the claim from
       INTAKE to DOCS_PENDING (AC4, second half).

    Returns the claim re-fetched after the transition, so the returned
    object's `status` reflects DOCS_PENDING rather than the stale INTAKE
    value captured at creation time.
    """
    checklist = _checklist_for(claim_type)

    claim_repository = ClaimRepository(conn)
    document_repository = ClaimDocumentRepository(conn)

    claim_id = claim_repository.create(
        policy_id=policy_id,
        claim_type=claim_type,
        incident_date=incident_date,
        claim_amount=claim_amount,
    )

    for document_type in checklist:
        document_repository.insert(claim_id, document_type)

    claim_repository.apply_transition(claim_id, ClaimEvent.ATTACH_CHECKLIST, actor_id)

    claim = claim_repository.get_by_id(claim_id)
    assert claim is not None
    return claim
