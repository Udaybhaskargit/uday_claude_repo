"""Canonical domain entities (E1-S1, E1-S2 ClaimStateTransition shape).

Plain dataclasses -- no ORM, no pydantic -- so this module has zero dependencies
on any other layer (Layer 1: Types, per `.claude/architecture.md`). Repository
code (Group D) maps these to/from SQLite rows; API schemas (later groups) map
these to/from JSON.

Money fields are always `decimal.Decimal`, never `float` (NFR-01). Dates are
ISO `YYYY-MM-DD` strings; timestamps are ISO-8601 UTC strings -- see the
Conventions section of `specs/design/data-models.md`.
"""

from dataclasses import dataclass
from decimal import Decimal

from src.types.enums import (
    AdminOverrideCommand,
    ClaimStatus,
    ClaimType,
    DecisionOutcome,
    DocumentType,
    PolicyStatus,
    ReasonCode,
    Role,
    VerificationStatus,
)


@dataclass
class Policy:
    """An insurance policy (data-models.md sec 2.1)."""

    id: int
    policy_number: str
    product_type: ClaimType
    status: PolicyStatus
    sum_insured: Decimal
    effective_date: str
    expiry_date: str
    created_at: str

    def is_active_on(self, on_date: str) -> bool:
        """True iff status is ACTIVE and on_date falls within the policy window."""
        return (
            self.status == PolicyStatus.ACTIVE
            and self.effective_date <= on_date <= self.expiry_date
        )


@dataclass
class Claim:
    """A claim filed against a Policy (data-models.md sec 2.2, E1-S1 AC1)."""

    id: int
    policy_id: int
    claim_type: ClaimType
    incident_date: str
    claim_amount: Decimal
    status: ClaimStatus
    parent_claim_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class ClaimDocument:
    """A checklist item attached to a Claim (data-models.md sec 2.3)."""

    id: int
    claim_id: int
    document_type: DocumentType
    verification_status: VerificationStatus
    created_at: str
    updated_at: str


@dataclass
class FraudScreening:
    """An append-only fraud scoring result (data-models.md sec 2.4)."""

    id: int
    claim_id: int
    score: int
    breakdown: list[dict[str, object]]
    threshold: int
    flagged: bool
    created_at: str


@dataclass
class Assessment:
    """An append-only payable-amount computation (data-models.md sec 2.5)."""

    id: int
    claim_id: int
    claim_amount: Decimal
    sum_insured: Decimal
    deductible: Decimal
    co_pay: Decimal
    payable_amount: Decimal
    created_at: str


@dataclass
class Decision:
    """An append-only outcome record (data-models.md sec 2.6)."""

    id: int
    claim_id: int
    outcome: DecisionOutcome
    reason_code: ReasonCode
    decided_by: str
    created_at: str


@dataclass
class Settlement:
    """An append-only, immutable payout record (data-models.md sec 2.7)."""

    id: int
    claim_id: int
    decision_id: int
    payout_amount: Decimal
    payment_reference: str
    created_at: str


@dataclass
class ClaimStateTransition:
    """An append-only audit record returned by state_machine.transition().

    Per E1-S2 AC4 the caller persists this in the same transaction as the
    Claim.status update. `claim_id` and `actor_id` are optional per
    data-models.md sec 2.8 (actor_id is null for system-internal steps).
    """

    from_state: ClaimStatus
    to_state: ClaimStatus
    event: str
    timestamp: str
    claim_id: int | None = None
    actor_id: str | None = None


@dataclass
class AdminOverride:
    """An append-only admin override audit record (data-models.md sec 2.9)."""

    id: int
    claim_id: int
    admin_actor_id: str
    command: AdminOverrideCommand
    reason_code: str
    created_at: str


@dataclass
class ActorContext:
    """Non-persisted value object produced per-request by the E8-S1 auth stub."""

    role: Role
    actor_id: str
