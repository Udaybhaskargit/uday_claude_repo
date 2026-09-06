"""Tests for backend/src/types/state_machine.py (E1-S2)."""

from decimal import Decimal

import pytest
from src.types.enums import ClaimEvent, ClaimStatus, ClaimType
from src.types.exceptions import InvalidClaimStateException
from src.types.models import Claim, ClaimStateTransition
from src.types.state_machine import TRANSITION_TABLE, transition

_DOCUMENTED_TRANSITIONS = [
    (ClaimStatus.INTAKE, ClaimEvent.ATTACH_CHECKLIST, ClaimStatus.DOCS_PENDING),
    (ClaimStatus.DOCS_PENDING, ClaimEvent.DOCS_VERIFIED, ClaimStatus.FRAUD_SCREENING),
    (ClaimStatus.DOCS_PENDING, ClaimEvent.ADMIN_FORCE_REJECT, ClaimStatus.REJECTED),
    (ClaimStatus.FRAUD_SCREENING, ClaimEvent.FRAUD_CLEARED, ClaimStatus.ASSESSMENT),
    (ClaimStatus.FRAUD_SCREENING, ClaimEvent.FRAUD_FLAGGED, ClaimStatus.MANUAL_REVIEW),
    (ClaimStatus.FRAUD_SCREENING, ClaimEvent.PIPELINE_ERROR, ClaimStatus.PROCESSING_FAILED),
    (ClaimStatus.FRAUD_SCREENING, ClaimEvent.ADMIN_FORCE_REJECT, ClaimStatus.REJECTED),
    (ClaimStatus.ASSESSMENT, ClaimEvent.DECISION_AUTO_APPROVE, ClaimStatus.AUTO_APPROVED),
    (ClaimStatus.ASSESSMENT, ClaimEvent.DECISION_MANUAL_REVIEW, ClaimStatus.MANUAL_REVIEW),
    (ClaimStatus.ASSESSMENT, ClaimEvent.DECISION_REJECT, ClaimStatus.REJECTED),
    (ClaimStatus.ASSESSMENT, ClaimEvent.PIPELINE_ERROR, ClaimStatus.PROCESSING_FAILED),
    (ClaimStatus.MANUAL_REVIEW, ClaimEvent.ASSESSOR_APPROVE, ClaimStatus.AUTO_APPROVED),
    (ClaimStatus.MANUAL_REVIEW, ClaimEvent.ASSESSOR_REJECT, ClaimStatus.REJECTED),
    (ClaimStatus.MANUAL_REVIEW, ClaimEvent.ADMIN_FORCE_APPROVE, ClaimStatus.AUTO_APPROVED),
    (ClaimStatus.MANUAL_REVIEW, ClaimEvent.ADMIN_FORCE_REJECT, ClaimStatus.REJECTED),
    (ClaimStatus.MANUAL_REVIEW, ClaimEvent.ADMIN_FORCE_MANUAL_REVIEW, ClaimStatus.MANUAL_REVIEW),
    (ClaimStatus.AUTO_APPROVED, ClaimEvent.SETTLE, ClaimStatus.SETTLED),
    (ClaimStatus.SETTLED, ClaimEvent.REOPEN, ClaimStatus.REOPENED),
    (ClaimStatus.PROCESSING_FAILED, ClaimEvent.RETRY_TO_DOCS_PENDING, ClaimStatus.DOCS_PENDING),
    (
        ClaimStatus.PROCESSING_FAILED,
        ClaimEvent.RETRY_TO_FRAUD_SCREENING,
        ClaimStatus.FRAUD_SCREENING,
    ),
    (ClaimStatus.PROCESSING_FAILED, ClaimEvent.RETRY_TO_ASSESSMENT, ClaimStatus.ASSESSMENT),
    (ClaimStatus.PROCESSING_FAILED, ClaimEvent.ADMIN_FORCE_REJECT, ClaimStatus.REJECTED),
]

_EXPECTED_TRANSITION_TABLE: dict[ClaimStatus, dict[ClaimEvent, ClaimStatus]] = {
    ClaimStatus.INTAKE: {ClaimEvent.ATTACH_CHECKLIST: ClaimStatus.DOCS_PENDING},
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
    ClaimStatus.AUTO_APPROVED: {ClaimEvent.SETTLE: ClaimStatus.SETTLED},
    ClaimStatus.REJECTED: {},
    ClaimStatus.SETTLED: {ClaimEvent.REOPEN: ClaimStatus.REOPENED},
    ClaimStatus.REOPENED: {},
    ClaimStatus.PROCESSING_FAILED: {
        ClaimEvent.RETRY_TO_DOCS_PENDING: ClaimStatus.DOCS_PENDING,
        ClaimEvent.RETRY_TO_FRAUD_SCREENING: ClaimStatus.FRAUD_SCREENING,
        ClaimEvent.RETRY_TO_ASSESSMENT: ClaimStatus.ASSESSMENT,
        ClaimEvent.ADMIN_FORCE_REJECT: ClaimStatus.REJECTED,
    },
}


def _make_claim(status: ClaimStatus, claim_id: int = 1) -> Claim:
    return Claim(
        id=claim_id,
        policy_id=1,
        claim_type=ClaimType.MOTOR,
        incident_date="2026-01-01",
        claim_amount=Decimal("1000.00"),
        status=status,
    )


def test_docs_pending_to_fraud_screening_on_docs_verified() -> None:
    # F006 / E1-S2 AC1
    claim = _make_claim(ClaimStatus.DOCS_PENDING)
    result = transition(claim, ClaimEvent.DOCS_VERIFIED)
    assert claim.status == ClaimStatus.FRAUD_SCREENING
    assert result.to_state == ClaimStatus.FRAUD_SCREENING


def test_invalid_event_for_terminal_state_raises_and_leaves_status_unchanged() -> None:
    # F007 / E1-S2 AC2.
    # The story text names the invalid event "SUBMIT_FNOL"; that name is not part of
    # the canonical ClaimEvent set defined in data-models.md sec 1.1 (see the
    # deviation note in this session's final report). We exercise the same
    # behavior -- an event with no table entry for the claim's current terminal
    # state -- using a real ClaimEvent value instead.
    claim = _make_claim(ClaimStatus.SETTLED)
    with pytest.raises(InvalidClaimStateException):
        transition(claim, ClaimEvent.DOCS_VERIFIED)
    assert claim.status == ClaimStatus.SETTLED


def test_every_claim_status_is_a_key_in_the_transition_table() -> None:
    # F008 / E1-S2 AC3
    for status in ClaimStatus:
        assert status in TRANSITION_TABLE


def test_terminal_states_have_no_outgoing_events() -> None:
    # F008 / E1-S2 AC3 (no implicit fallthrough)
    assert TRANSITION_TABLE[ClaimStatus.REJECTED] == {}
    assert TRANSITION_TABLE[ClaimStatus.REOPENED] == {}


def test_transition_table_matches_data_models_spec_exactly() -> None:
    assert TRANSITION_TABLE == _EXPECTED_TRANSITION_TABLE


def test_successful_transition_returns_claim_state_transition_record() -> None:
    # F009 / E1-S2 AC4
    claim = _make_claim(ClaimStatus.INTAKE)
    result = transition(claim, ClaimEvent.ATTACH_CHECKLIST, actor_id="system")
    assert isinstance(result, ClaimStateTransition)
    assert result.from_state == ClaimStatus.INTAKE
    assert result.to_state == ClaimStatus.DOCS_PENDING
    assert result.event == ClaimEvent.ATTACH_CHECKLIST.value
    assert result.timestamp
    assert result.claim_id == claim.id
    assert result.actor_id == "system"


def test_transition_actor_id_defaults_to_none() -> None:
    claim = _make_claim(ClaimStatus.INTAKE)
    result = transition(claim, ClaimEvent.ATTACH_CHECKLIST)
    assert result.actor_id is None


@pytest.mark.parametrize("from_status,event,to_status", _DOCUMENTED_TRANSITIONS)
def test_every_documented_transition_succeeds(
    from_status: ClaimStatus, event: ClaimEvent, to_status: ClaimStatus
) -> None:
    claim = _make_claim(from_status)
    result = transition(claim, event)
    assert claim.status == to_status
    assert result.from_state == from_status
    assert result.to_state == to_status


def test_every_undocumented_event_for_every_state_raises_and_does_not_mutate() -> None:
    for status in ClaimStatus:
        allowed_events = set(TRANSITION_TABLE[status])
        for event in ClaimEvent:
            if event in allowed_events:
                continue
            claim = _make_claim(status)
            with pytest.raises(InvalidClaimStateException):
                transition(claim, event)
            assert claim.status == status
