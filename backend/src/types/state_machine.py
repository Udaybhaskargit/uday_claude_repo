"""The centralized claim state-machine transition gate (E1-S2).

`TRANSITION_TABLE` is built exactly from the `{FROM_STATE: {EVENT: TO_STATE}}`
table in `specs/design/data-models.md` sec 1.1. `transition()` is the ONLY
function anywhere in `src/types/` (or, per NFR-08, anywhere in the whole
backend) that may assign to `Claim.status` -- see
`backend/tests/architecture/test_state_mutation_gate.py`.
"""

from datetime import UTC, datetime

from src.types.enums import ClaimEvent, ClaimStatus
from src.types.exceptions import InvalidClaimStateException
from src.types.models import Claim, ClaimStateTransition

TRANSITION_TABLE: dict[ClaimStatus, dict[ClaimEvent, ClaimStatus]] = {
    ClaimStatus.INTAKE: {
        ClaimEvent.ATTACH_CHECKLIST: ClaimStatus.DOCS_PENDING,
    },
    ClaimStatus.DOCS_PENDING: {
        ClaimEvent.DOCS_VERIFIED: ClaimStatus.FRAUD_SCREENING,
        ClaimEvent.ADMIN_FORCE_REJECT: ClaimStatus.REJECTED,
    },
    ClaimStatus.FRAUD_SCREENING: {
        ClaimEvent.FRAUD_CLEARED: ClaimStatus.ASSESSMENT,
        ClaimEvent.FRAUD_FLAGGED: ClaimStatus.MANUAL_REVIEW,
        ClaimEvent.PIPELINE_ERROR: ClaimStatus.PROCESSING_FAILED,
        ClaimEvent.ADMIN_FORCE_REJECT: ClaimStatus.REJECTED,
    },
    ClaimStatus.ASSESSMENT: {
        ClaimEvent.DECISION_AUTO_APPROVE: ClaimStatus.AUTO_APPROVED,
        ClaimEvent.DECISION_MANUAL_REVIEW: ClaimStatus.MANUAL_REVIEW,
        ClaimEvent.DECISION_REJECT: ClaimStatus.REJECTED,
        ClaimEvent.PIPELINE_ERROR: ClaimStatus.PROCESSING_FAILED,
    },
    ClaimStatus.MANUAL_REVIEW: {
        ClaimEvent.ASSESSOR_APPROVE: ClaimStatus.AUTO_APPROVED,
        ClaimEvent.ASSESSOR_REJECT: ClaimStatus.REJECTED,
        ClaimEvent.ADMIN_FORCE_APPROVE: ClaimStatus.AUTO_APPROVED,
        ClaimEvent.ADMIN_FORCE_REJECT: ClaimStatus.REJECTED,
        ClaimEvent.ADMIN_FORCE_MANUAL_REVIEW: ClaimStatus.MANUAL_REVIEW,
    },
    ClaimStatus.AUTO_APPROVED: {
        ClaimEvent.SETTLE: ClaimStatus.SETTLED,
    },
    ClaimStatus.REJECTED: {},
    ClaimStatus.SETTLED: {
        ClaimEvent.REOPEN: ClaimStatus.REOPENED,
    },
    ClaimStatus.REOPENED: {},
    ClaimStatus.PROCESSING_FAILED: {
        ClaimEvent.RETRY_TO_DOCS_PENDING: ClaimStatus.DOCS_PENDING,
        ClaimEvent.RETRY_TO_FRAUD_SCREENING: ClaimStatus.FRAUD_SCREENING,
        ClaimEvent.RETRY_TO_ASSESSMENT: ClaimStatus.ASSESSMENT,
        ClaimEvent.ADMIN_FORCE_REJECT: ClaimStatus.REJECTED,
    },
}


def transition(
    claim: Claim, event: ClaimEvent, actor_id: str | None = None
) -> ClaimStateTransition:
    """Apply `event` to `claim` if valid for its current state.

    On success, mutates `claim.status` in place and returns a
    `ClaimStateTransition` audit record for the caller to persist in the same
    transaction as the status update (E1-S2 AC4).

    Raises `InvalidClaimStateException` -- leaving `claim.status` unchanged --
    if `event` has no entry for the claim's current state (E1-S2 AC2/AC3).
    """
    allowed_events = TRANSITION_TABLE[claim.status]
    if event not in allowed_events:
        raise InvalidClaimStateException(
            f"Cannot apply event {event.value!r} to claim {claim.id} "
            f"in state {claim.status.value!r}."
        )

    from_state = claim.status
    to_state = allowed_events[event]
    claim.status = to_state

    return ClaimStateTransition(
        from_state=from_state,
        to_state=to_state,
        event=event.value,
        timestamp=datetime.now(UTC).isoformat(),
        claim_id=claim.id,
        actor_id=actor_id,
    )
