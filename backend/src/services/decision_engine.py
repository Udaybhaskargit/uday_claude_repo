"""Decision engine: assess, decide, and gate a claim out of ASSESSMENT (E6-S2).

Combines the pure `assessment_service.assess()` computation (E6-S1) with a
pure `decide()` outcome/reason-code rule and a persistence+gating entrypoint,
`run_decision()`, that a claim in ASSESSMENT is routed through exactly once
per decision run: it persists the `Assessment` row (never done by E6-S1
itself, which is computation-only), reads the claim's latest `FraudScreening`
verdict, decides an outcome, persists the append-only `Decision` row (AC5),
and applies the matching `DECISION_*` transition event via
`ClaimRepository.apply_transition()` -- the sole gate for `Claim.status`.

Precedence, in order (BRD section 11 / AC1-AC4): a zero payable amount always
rejects, even if the claim happens to also be fraud-flagged (AC1 takes no
`flagged` input, so it must win outright); a nonzero fraud-flagged claim goes
to manual review (AC2); otherwise the ceiling comparison decides AUTO_APPROVE
vs. HIGH_VALUE_REVIEW (AC3/AC4).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from src.config.assessment_rules_config import AssessmentRulesConfig
from src.repositories.assessment_repository import AssessmentRepository
from src.repositories.claim_repository import ClaimRepository
from src.repositories.decision_repository import DecisionRepository
from src.repositories.fraud_screening_repository import FraudScreeningRepository
from src.repositories.policy_repository import PolicyRepository
from src.services.assessment_service import assess
from src.types.enums import ClaimEvent, DecisionOutcome, ReasonCode
from src.types.models import Decision

_ZERO = Decimal("0")

_OUTCOME_TO_EVENT: dict[DecisionOutcome, ClaimEvent] = {
    DecisionOutcome.AUTO_APPROVE: ClaimEvent.DECISION_AUTO_APPROVE,
    DecisionOutcome.MANUAL_REVIEW: ClaimEvent.DECISION_MANUAL_REVIEW,
    DecisionOutcome.REJECT: ClaimEvent.DECISION_REJECT,
}


@dataclass(frozen=True)
class DecisionComputation:
    """The pure result of `decide()`."""

    outcome: DecisionOutcome
    reason_code: ReasonCode


def decide(
    payable_amount: Decimal, flagged: bool, auto_approve_ceiling: Decimal
) -> DecisionComputation:
    """Determine an outcome and reason code from assessment + fraud results.

    A `payable_amount` of exactly zero always rejects (AC1), regardless of
    `flagged` -- there is nothing to pay out either way. A nonzero amount on
    a fraud-flagged claim always goes to manual review (AC2), regardless of
    how it compares to the ceiling. Only once both of those are ruled out
    does the ceiling comparison apply: at or below it auto-approves (AC3),
    above it requires manual review for high value (AC4).
    """
    if payable_amount == _ZERO:
        return DecisionComputation(DecisionOutcome.REJECT, ReasonCode.ZERO_PAYABLE_AMOUNT)

    if flagged:
        return DecisionComputation(DecisionOutcome.MANUAL_REVIEW, ReasonCode.FRAUD_FLAG)

    if payable_amount <= auto_approve_ceiling:
        return DecisionComputation(
            DecisionOutcome.AUTO_APPROVE, ReasonCode.AUTO_APPROVED_LOW_RISK
        )

    return DecisionComputation(DecisionOutcome.MANUAL_REVIEW, ReasonCode.HIGH_VALUE_REVIEW)


def run_decision(
    conn: sqlite3.Connection,
    claim_id: int,
    assessment_config: AssessmentRulesConfig,
    decided_by: str = "system",
) -> Decision:
    """Assess, decide, persist, and gate `claim_id` out of ASSESSMENT.

    `decided_by` is recorded verbatim on the `Decision` row (AC5) and passed
    through as the state-transition's `actor_id`; it is `'system'` for the
    automatic pipeline run and an assessor's own actor id when a human
    triggers this directly (e.g. a re-run from the assessor workbench).

    Raises `LookupError` if no claim with `claim_id` exists. Raises
    `InvalidClaimStateException` (via `apply_transition()`) if the claim is
    not currently in ASSESSMENT -- in that failure case the `Assessment` row
    computed just before the gate check has already been inserted (each
    repository call commits independently), matching the same disclosed
    cross-call-atomicity tradeoff already noted in `fnol_intake_service` and
    `reopen_service`; no `Decision` row is inserted, since that insert only
    happens after the transition succeeds.
    """
    claim_repository = ClaimRepository(conn)
    claim = claim_repository.get_by_id(claim_id)
    if claim is None:
        raise LookupError(f"Claim {claim_id} not found.")

    policy = PolicyRepository(conn).get_by_id(claim.policy_id)
    assert policy is not None

    computation = assess(
        claim.claim_amount, policy.sum_insured, claim.claim_type, assessment_config
    )
    AssessmentRepository(conn).insert(
        claim_id,
        computation.claim_amount,
        computation.sum_insured,
        computation.deductible,
        computation.co_pay,
        computation.payable_amount,
    )

    screening = FraudScreeningRepository(conn).get_latest(claim_id)
    assert screening is not None
    flagged = screening.flagged

    result = decide(
        computation.payable_amount, flagged, Decimal(assessment_config.auto_approve_ceiling)
    )

    event = _OUTCOME_TO_EVENT[result.outcome]
    claim_repository.apply_transition(claim_id, event, decided_by)

    DecisionRepository(conn).insert(claim_id, result.outcome, result.reason_code, decided_by)

    decision = DecisionRepository(conn).get_latest(claim_id)
    assert decision is not None
    return decision
