"""Settlement service (Service layer, E7-S1).

On an `AUTO_APPROVED` claim, `settle()` creates an immutable, append-only
`Settlement` row carrying the claim's assessed `payable_amount` and invokes a
stubbed payment trigger, then gates the claim to `SETTLED` via the E1-S2
state-machine gate (AC1).

The `SETTLE` event only has an entry in `TRANSITION_TABLE` for the
`AUTO_APPROVED` state (`src/types/state_machine.py`), so calling
`ClaimRepository.apply_transition()` against any other status -- `REJECTED`,
`MANUAL_REVIEW`, etc. -- already raises `InvalidClaimStateException` on its
own; no separate manual status check is added here, matching the same
"let the state machine be the single source of truth" pattern used by
`reopen_service.reopen()` and `decision_engine.run_decision()` (AC4).

The gate is applied *before* any `Settlement` row is written, so a non-
`AUTO_APPROVED` claim never gets a Settlement row inserted for it (AC4,
second half) -- the function returns before reaching that code at all.
"""

from __future__ import annotations

import sqlite3
import uuid

from src.repositories.assessment_repository import AssessmentRepository
from src.repositories.claim_repository import ClaimRepository
from src.repositories.decision_repository import DecisionRepository
from src.repositories.settlement_repository import SettlementRepository
from src.types.enums import ClaimEvent
from src.types.models import Settlement


def _stub_payment_trigger(claim_id: int) -> str:
    """Return a stub payment confirmation reference (AC3).

    Never contacts any real external payment rail -- this module imports no
    network/HTTP client library at all (confirmed by
    `test_settlement_service.py::TestSettlePaymentTriggerIsStubbed`, which
    greps this module's own source for `requests`/`httpx`/`urllib`/`socket`).
    `claim_id` is accepted for a readable, traceable reference format but
    plays no role in an actual payment rail integration, since there is none.
    """
    return f"STUB-PAY-{claim_id}-{uuid.uuid4().hex[:12].upper()}"


def settle(conn: sqlite3.Connection, claim_id: int, actor_id: str | None = None) -> Settlement:
    """Settle the `AUTO_APPROVED` claim `claim_id`, returning the new Settlement.

    1. Applies `ClaimEvent.SETTLE` via `ClaimRepository.apply_transition()` --
       the sole gate for `Claim.status` -- moving the claim to `SETTLED`. This
       alone enforces AC4: `SETTLE` has no entry for any state other than
       `AUTO_APPROVED`, so calling this against a `REJECTED` or
       `MANUAL_REVIEW` claim raises `InvalidClaimStateException` and leaves
       the claim, and the `settlements` table, untouched.
    2. Only once that transition has succeeded does this function read the
       claim's latest `Decision` and `Assessment` rows -- both are guaranteed
       to exist for any claim that ever reached `AUTO_APPROVED`, since
       `decision_engine.run_decision()` (or `submit_assessor_decision()`)
       always inserts an `Assessment` and a `Decision` before applying the
       `AUTO_APPROVE`-family transition event that could put a claim in that
       state in the first place.
    3. Invokes the stubbed payment trigger (AC3) and inserts the append-only
       `Settlement` row carrying the decision's `payable_amount` (AC1).

    Note on atomicity: as with `fnol_intake_service.submit_fnol()`,
    `reopen_service.reopen()`, and `decision_engine.run_decision()`, the gate
    transition and the `Settlement` insert are two separate calls that each
    commit independently -- a DB failure between them would leave the claim
    `SETTLED` with no `Settlement` row yet. No AC requires cross-call
    atomicity here, and this matches the same disclosed tradeoff already
    accepted throughout this codebase.

    Raises `LookupError` if no claim with `claim_id` exists.
    Raises `InvalidClaimStateException` if the claim is not currently
    `AUTO_APPROVED` (AC4).
    """
    claim_repository = ClaimRepository(conn)
    claim = claim_repository.get_by_id(claim_id)
    if claim is None:
        raise LookupError(f"Claim {claim_id} not found.")

    claim_repository.apply_transition(claim_id, ClaimEvent.SETTLE, actor_id)

    decision = DecisionRepository(conn).get_latest(claim_id)
    assert decision is not None

    assessment = AssessmentRepository(conn).get_latest_assessment(claim_id)
    assert assessment is not None

    payment_reference = _stub_payment_trigger(claim_id)
    SettlementRepository(conn).insert(
        claim_id, decision.id, assessment.payable_amount, payment_reference
    )

    settlement = SettlementRepository(conn).get_latest_for_claim(claim_id)
    assert settlement is not None
    return settlement
