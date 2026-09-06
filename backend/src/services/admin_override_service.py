"""Admin override service (Service layer, E8-S2).

Lets an admin force a claim decision or status with a mandatory
`reason_code`, recorded as an auditable, append-only `AdminOverride` row
(data-models.md sec 2.9) distinct from the automated decision trail (AC-09).

Design note -- `FORCE_RETRY` is ambiguous, `target_event` disambiguates it:
`AdminOverrideCommand` has exactly one unambiguous `ClaimEvent` for
FORCE_APPROVE, FORCE_REJECT, and FORCE_MANUAL_REVIEW (see
`_COMMAND_TO_EVENT` below), but `PROCESSING_FAILED` has THREE valid retry
targets in the E1-S2 transition table (`RETRY_TO_DOCS_PENDING`,
`RETRY_TO_FRAUD_SCREENING`, `RETRY_TO_ASSESSMENT`) and `FORCE_RETRY` alone
cannot say which one the admin means. The story's ACs don't exercise
FORCE_RETRY directly, so this is a genuine, undocumented ambiguity rather
than a spec violation to route around. This service resolves it by
requiring the caller to pass an explicit `target_event` (one of the three
`RETRY_TO_*` values) whenever `command == FORCE_RETRY`, raising
`ValidationError` if it's omitted. For the other three commands,
`target_event` is accepted but ignored, since the mapping is already
unambiguous.

Design note -- the audit row is only inserted on success: AC1 describes the
`AdminOverride` insert as the outcome of "override() is called with a
command and reason code" on the success path, while AC3/AC4 describe the
failure paths purely in terms of `InvalidClaimStateException` propagating,
with no mention of an audit trail for rejected attempts. Since no AC
supports a "log the attempt anyway" reading, and inserting on failure
would mean the `admin_overrides` table recording override rows that never
took effect, this service only calls `AdminOverrideRepository.insert()`
after `ClaimRepository.apply_transition()` has already succeeded.
"""

from __future__ import annotations

import sqlite3

from src.repositories.admin_override_repository import AdminOverrideRepository
from src.repositories.claim_repository import ClaimRepository
from src.types.enums import AdminOverrideCommand, ClaimEvent
from src.types.exceptions import ValidationError
from src.types.models import AdminOverride

_COMMAND_TO_EVENT: dict[AdminOverrideCommand, ClaimEvent] = {
    AdminOverrideCommand.FORCE_APPROVE: ClaimEvent.ADMIN_FORCE_APPROVE,
    AdminOverrideCommand.FORCE_REJECT: ClaimEvent.ADMIN_FORCE_REJECT,
    AdminOverrideCommand.FORCE_MANUAL_REVIEW: ClaimEvent.ADMIN_FORCE_MANUAL_REVIEW,
}

_VALID_RETRY_TARGETS: frozenset[ClaimEvent] = frozenset(
    {
        ClaimEvent.RETRY_TO_DOCS_PENDING,
        ClaimEvent.RETRY_TO_FRAUD_SCREENING,
        ClaimEvent.RETRY_TO_ASSESSMENT,
    }
)


def _validate_reason_code(reason_code: str) -> None:
    """Raise `ValidationError` if `reason_code` is missing or blank (AC2)."""
    if not reason_code or not reason_code.strip():
        raise ValidationError("reason_code is required")


def _resolve_event(
    command: AdminOverrideCommand, target_event: ClaimEvent | None
) -> ClaimEvent:
    """Resolve `command` to the single `ClaimEvent` it should apply.

    FORCE_APPROVE/FORCE_REJECT/FORCE_MANUAL_REVIEW map unambiguously via
    `_COMMAND_TO_EVENT`. FORCE_RETRY requires the caller to supply an
    explicit `target_event` from `_VALID_RETRY_TARGETS`, since the command
    alone cannot say which of the three retry destinations is meant.
    """
    if command == AdminOverrideCommand.FORCE_RETRY:
        if target_event is None or target_event not in _VALID_RETRY_TARGETS:
            raise ValidationError(
                "FORCE_RETRY requires an explicit target_event, one of: "
                + ", ".join(sorted(event.value for event in _VALID_RETRY_TARGETS))
            )
        return target_event

    return _COMMAND_TO_EVENT[command]


def override(
    conn: sqlite3.Connection,
    claim_id: int,
    admin_actor_id: str,
    command: AdminOverrideCommand,
    reason_code: str,
    target_event: ClaimEvent | None = None,
) -> AdminOverride:
    """Force a claim status change through the E1-S2 gate, then audit it.

    1. Validates `reason_code` first, before any DB write (AC2) -- a
       missing/blank `reason_code` raises `ValidationError` and no row is
       ever inserted.
    2. Resolves `command` (plus `target_event` for FORCE_RETRY) to a single
       `ClaimEvent` per `_resolve_event`.
    3. Applies that event via `ClaimRepository.apply_transition()`, which
       re-fetches the claim's CURRENT status fresh from the DB and checks it
       against the E1-S2 transition table (AC3). If the event is invalid for
       the claim's current state, `InvalidClaimStateException` propagates
       unchanged and no `AdminOverride` row is inserted -- this also covers
       AC4's concurrency scenario: calling `override()` twice in a row with
       an event that was valid for the ORIGINAL status but not for the
       status the FIRST call already moved the claim to will raise on the
       second call, since `apply_transition` always reads the current row
       before deciding, with no additional locking needed here.
    4. Only once the transition succeeds does this insert the audit row via
       `AdminOverrideRepository.insert()`, then returns the resulting
       `AdminOverride` built from the known inputs plus the freshly
       persisted `created_at` (the repository's `insert()` returns only the
       new row's id, so the created row is re-read directly rather than
       reconstructed from clock values captured here).
    """
    _validate_reason_code(reason_code)
    event = _resolve_event(command, target_event)

    ClaimRepository(conn).apply_transition(claim_id, event, admin_actor_id)

    override_repository = AdminOverrideRepository(conn)
    override_id = override_repository.insert(claim_id, admin_actor_id, command, reason_code)

    created = next(
        row
        for row in override_repository.list_admin_overrides(claim_id)
        if row.id == override_id
    )
    return created
