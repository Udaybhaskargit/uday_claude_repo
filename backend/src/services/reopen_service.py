"""Reopen/dispute service (Service layer, E7-S2).

Allows a customer to dispute a SETTLED claim (AC-08 / NFR-02). Reopening a
claim never edits the original claim's terminal record or its historical
Decision/Settlement/Assessment rows (AC2): it marks the original claim
REOPENED via the state-machine gate (AC3) and creates a brand-new,
independent `Claim` row -- a sub-claim -- starting at `status=INTAKE` and
linked back to the original via `parent_claim_id` (AC1).
"""

from __future__ import annotations

import sqlite3

from src.repositories.claim_repository import ClaimRepository
from src.types.enums import ClaimEvent
from src.types.models import Claim


def reopen(conn: sqlite3.Connection, claim_id: int, actor_id: str | None = None) -> Claim:
    """Reopen the SETTLED claim `claim_id`, returning the new sub-claim.

    1. Fetches the original claim (used below as the template for the new
       sub-claim's policy/type/incident-date/amount).
    2. Applies `ClaimEvent.REOPEN` to the original via
       `ClaimRepository.apply_transition()` -- the only place allowed to
       decide/persist a `Claim.status` change (AC3). This call alone is
       sufficient to enforce AC4: `REOPEN` is only a valid event from
       `SETTLED` in the transition table, so calling this against a claim in
       any other state raises `InvalidClaimStateException` and leaves the
       original row untouched. No separate manual status check is added here
       -- doing so would duplicate the state machine's own source of truth.
    3. Only once that transition has succeeded does this function create the
       new sub-claim, via `ClaimRepository.create(parent_claim_id=claim_id)`,
       which starts the sub-claim at `status=INTAKE` per `create()`'s
       existing behavior (AC1).

    Never touches the `decisions`, `settlements`, or `assessments` tables, so
    the original claim's historical rows are left exactly as they were
    (AC2) -- this is naturally satisfied by this function simply never
    calling those repositories.

    Note on atomicity: `apply_transition()` commits the original claim's
    REOPENED status and its audit row in its own transaction before this
    function ever calls `create()`. If `create()` were to fail afterward
    (e.g. a DB error), the original claim would be left REOPENED with no
    sub-claim yet created -- an edge case the acceptance criteria don't
    address and this implementation does not attempt to paper over with a
    wrapping transaction, since `apply_transition()` and `create()` already
    each commit independently (matching the pattern used by
    `fnol_intake_service.submit_fnol()`).

    Raises `InvalidClaimStateException` if the claim identified by
    `claim_id` is not currently SETTLED (AC4).
    """
    claim_repository = ClaimRepository(conn)

    original = claim_repository.get_by_id(claim_id)
    if original is None:
        raise LookupError(f"Claim {claim_id} not found.")

    claim_repository.apply_transition(claim_id, ClaimEvent.REOPEN, actor_id)

    sub_claim_id = claim_repository.create(
        policy_id=original.policy_id,
        claim_type=original.claim_type,
        incident_date=original.incident_date,
        claim_amount=original.claim_amount,
        parent_claim_id=claim_id,
    )

    sub_claim = claim_repository.get_by_id(sub_claim_id)
    assert sub_claim is not None
    return sub_claim
