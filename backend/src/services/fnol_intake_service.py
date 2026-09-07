"""FNOL intake service (Service layer, E4-S1, E4-S2, E4-S3).

Accepts a first-notice-of-loss submission (policy, claim type, incident date,
claim amount) and creates the initial `Claim` plus its per-claim-type
`ClaimDocument` checklist rows (AC1-AC3), then moves the claim from INTAKE to
DOCS_PENDING once the checklist is attached (AC4).

The checklist mapping hardcoded below only seeds the initial MISSING rows for
the claim's product type -- the full checklist-verification workflow
(toggling VERIFIED, completeness checks) is E5-S1's job, not this story's.

E4-S2/E4-S3 (Group F) -- `submit_fnol` now takes `policy_number` instead of a
raw `policy_id`, matching how a customer actually identifies their policy
(api-contracts.md `POST /api/claims` request body carries `policy_number`,
never the internal numeric id). This lets the two Group F validations run
before any row is written:
  - **E4-S2** looks the policy up and requires it to be ACTIVE on
    `incident_date` (`Policy.is_active_on()`, E3-S2), raising
    `PolicyNotActiveException` otherwise (AC1/AC2/AC3). An unresolvable
    `policy_number` (no such policy at all) is treated the same way, since
    there is no separate "policy not found" typed exception in
    `src/types/exceptions.py` to raise instead.
  - **E4-S3** then checks `ClaimRepository.exists_duplicate()` (built in
    Group D) for the same `(policy_id, incident_date)` pair, raising
    `DuplicateClaimException` if one already exists (AC1), while a second
    FNOL on the same policy with a *different* incident date is unaffected
    (AC2). This check only ever considers rows created via `submit_fnol()`
    itself; `reopen_service.reopen()` (E7-S2) creates its sub-claim through
    a direct `ClaimRepository.create()` call that never reaches this
    function, so reopening a settled claim can never trip this duplicate
    check no matter how many prior claims share its `(policy_id,
    incident_date)` pair -- confirmed by inspection, not just by the absence
    of a failing test.

Both checks run before `ClaimRepository.create()`, so neither failure mode
ever leaves behind a partially-created claim row (both ACs require "no
Claim row is created").

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
from src.repositories.policy_repository import PolicyRepository
from src.types.enums import ClaimEvent, ClaimType, DocumentType
from src.types.exceptions import (
    DuplicateClaimException,
    PolicyNotActiveException,
    UnknownClaimTypeError,
)
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
    policy_number: str,
    claim_type: ClaimType,
    incident_date: str,
    claim_amount: Decimal,
    actor_id: str | None = None,
) -> Claim:
    """Create a claim and its checklist, then transition it to DOCS_PENDING.

    1. Looks up the checklist document types for `claim_type`, raising
       `UnknownClaimTypeError` first if there is no mapping -- so an
       unrecognized claim type never creates a claim row at all.
    2. Resolves `policy_number` to a `Policy` and requires it to be ACTIVE on
       `incident_date`, raising `PolicyNotActiveException` otherwise (E4-S2
       AC1-AC3) -- including when `policy_number` doesn't resolve to any
       policy at all.
    3. Checks `ClaimRepository.exists_duplicate()` for the same `(policy,
       incident_date)` pair, raising `DuplicateClaimException` if one
       already exists (E4-S3 AC1), while a distinct incident date on the
       same policy is unaffected (E4-S3 AC2).
    4. Creates the claim row via `ClaimRepository.create()`, which starts at
       `status=INTAKE` (AC4, first half).
    5. Attaches one `ClaimDocument` row per checklist entry via
       `ClaimDocumentRepository.insert()`, each defaulting to
       `VerificationStatus.MISSING` (AC1-AC3).
    6. Applies `ClaimEvent.ATTACH_CHECKLIST`, transitioning the claim from
       INTAKE to DOCS_PENDING (AC4, second half).

    Returns the claim re-fetched after the transition, so the returned
    object's `status` reflects DOCS_PENDING rather than the stale INTAKE
    value captured at creation time.
    """
    checklist = _checklist_for(claim_type)

    claim_repository = ClaimRepository(conn)
    document_repository = ClaimDocumentRepository(conn)

    policy = PolicyRepository(conn).get_by_number(policy_number)
    if policy is None or not policy.is_active_on(incident_date):
        raise PolicyNotActiveException(policy_number, incident_date)

    if claim_repository.exists_duplicate(policy.id, incident_date):
        raise DuplicateClaimException(policy_number, incident_date)

    claim_id = claim_repository.create(
        policy_id=policy.id,
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
