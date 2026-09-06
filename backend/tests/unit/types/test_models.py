"""Tests for backend/src/types/models.py (E1-S1, E1-S2 ClaimStateTransition shape)."""

import dataclasses
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
from src.types.models import (
    ActorContext,
    AdminOverride,
    Assessment,
    Claim,
    ClaimDocument,
    ClaimStateTransition,
    Decision,
    FraudScreening,
    Policy,
    Settlement,
)

_MONEY_FIELD_NAMES = {
    "claim_amount",
    "sum_insured",
    "deductible",
    "co_pay",
    "payable_amount",
    "payout_amount",
}


def test_claim_exposes_required_fields() -> None:
    # F001 / E1-S1 AC1
    claim = Claim(
        id=42,
        policy_id=1,
        claim_type=ClaimType.MOTOR,
        incident_date="2026-03-10",
        claim_amount=Decimal("40000.00"),
        status=ClaimStatus.INTAKE,
        parent_claim_id=None,
    )
    assert claim.id == 42
    assert claim.policy_id == 1
    assert claim.claim_type == ClaimType.MOTOR
    assert claim.incident_date == "2026-03-10"
    assert isinstance(claim.claim_amount, Decimal)
    assert claim.status == ClaimStatus.INTAKE
    assert claim.parent_claim_id is None


def test_claim_parent_claim_id_is_nullable_and_settable() -> None:
    reopened_claim = Claim(
        id=2,
        policy_id=1,
        claim_type=ClaimType.LIFE,
        incident_date="2026-01-01",
        claim_amount=Decimal("100.00"),
        status=ClaimStatus.INTAKE,
        parent_claim_id=1,
    )
    assert reopened_claim.parent_claim_id == 1


def test_claim_accepts_claim_type_of_motor_health_or_life() -> None:
    for claim_type in (ClaimType.MOTOR, ClaimType.HEALTH, ClaimType.LIFE):
        claim = Claim(
            id=1,
            policy_id=1,
            claim_type=claim_type,
            incident_date="2026-01-01",
            claim_amount=Decimal("1.00"),
            status=ClaimStatus.INTAKE,
        )
        assert claim.claim_type == claim_type


def test_policy_exposes_required_fields() -> None:
    # F004 / E1-S1 AC4
    policy = Policy(
        id=1,
        policy_number="POL-MOTOR-0001",
        product_type=ClaimType.MOTOR,
        status=PolicyStatus.ACTIVE,
        sum_insured=Decimal("100000.00"),
        effective_date="2026-01-01",
        expiry_date="2026-12-31",
        created_at="2026-01-01T00:00:00Z",
    )
    assert policy.policy_number == "POL-MOTOR-0001"
    assert policy.product_type == ClaimType.MOTOR
    assert policy.status == PolicyStatus.ACTIVE
    assert isinstance(policy.sum_insured, Decimal)
    assert policy.effective_date == "2026-01-01"
    assert policy.expiry_date == "2026-12-31"


def test_policy_is_active_on_true_when_active_and_within_window() -> None:
    policy = Policy(
        id=1,
        policy_number="POL-1",
        product_type=ClaimType.MOTOR,
        status=PolicyStatus.ACTIVE,
        sum_insured=Decimal("1000"),
        effective_date="2026-01-01",
        expiry_date="2026-12-31",
        created_at="2026-01-01T00:00:00Z",
    )
    assert policy.is_active_on("2026-06-01") is True


def test_policy_is_active_on_false_when_outside_window() -> None:
    policy = Policy(
        id=1,
        policy_number="POL-1",
        product_type=ClaimType.MOTOR,
        status=PolicyStatus.ACTIVE,
        sum_insured=Decimal("1000"),
        effective_date="2026-01-01",
        expiry_date="2026-12-31",
        created_at="2026-01-01T00:00:00Z",
    )
    assert policy.is_active_on("2027-01-01") is False


def test_policy_is_active_on_false_when_status_not_active() -> None:
    policy = Policy(
        id=1,
        policy_number="POL-1",
        product_type=ClaimType.MOTOR,
        status=PolicyStatus.LAPSED,
        sum_insured=Decimal("1000"),
        effective_date="2026-01-01",
        expiry_date="2026-12-31",
        created_at="2026-01-01T00:00:00Z",
    )
    assert policy.is_active_on("2026-06-01") is False


def test_claim_document_exposes_required_fields() -> None:
    document = ClaimDocument(
        id=100,
        claim_id=42,
        document_type=DocumentType.POLICE_FIR,
        verification_status=VerificationStatus.VERIFIED,
        created_at="2026-03-11T09:00:00Z",
        updated_at="2026-03-11T09:02:00Z",
    )
    assert document.document_type == DocumentType.POLICE_FIR
    assert document.verification_status == VerificationStatus.VERIFIED


def test_fraud_screening_exposes_required_fields() -> None:
    screening = FraudScreening(
        id=7,
        claim_id=42,
        score=65,
        breakdown=[
            {"rule_name": "HIGH_CLAIM_TO_SUM_RATIO", "weight": 40},
            {"rule_name": "EARLY_FILING", "weight": 25},
        ],
        threshold=60,
        flagged=True,
        created_at="2026-03-11T09:03:00Z",
    )
    assert screening.score == 65
    assert screening.flagged is True
    assert screening.breakdown[0]["rule_name"] == "HIGH_CLAIM_TO_SUM_RATIO"


def test_assessment_exposes_required_fields_and_decimal_money() -> None:
    assessment = Assessment(
        id=12,
        claim_id=55,
        claim_amount=Decimal("20000.00"),
        sum_insured=Decimal("300000.00"),
        deductible=Decimal("1000.00"),
        co_pay=Decimal("1900.00"),
        payable_amount=Decimal("17100.00"),
        created_at="2026-04-02T10:00:00Z",
    )
    assert assessment.payable_amount == Decimal("17100.00")
    for value in (
        assessment.claim_amount,
        assessment.sum_insured,
        assessment.deductible,
        assessment.co_pay,
        assessment.payable_amount,
    ):
        assert isinstance(value, Decimal)


def test_decision_exposes_required_fields() -> None:
    decision = Decision(
        id=30,
        claim_id=42,
        outcome=DecisionOutcome.AUTO_APPROVE,
        reason_code=ReasonCode.AUTO_APPROVED_LOW_RISK,
        decided_by="system",
        created_at="2026-03-11T09:04:00Z",
    )
    assert decision.outcome == DecisionOutcome.AUTO_APPROVE
    assert decision.reason_code == ReasonCode.AUTO_APPROVED_LOW_RISK
    assert decision.decided_by == "system"


def test_settlement_exposes_required_fields_and_decimal_payout() -> None:
    settlement = Settlement(
        id=9,
        claim_id=42,
        decision_id=30,
        payout_amount=Decimal("35000.00"),
        payment_reference="STUB-PAY-0000042-01",
        created_at="2026-03-11T09:05:00Z",
    )
    assert isinstance(settlement.payout_amount, Decimal)
    assert settlement.payment_reference == "STUB-PAY-0000042-01"


def test_admin_override_exposes_required_fields() -> None:
    override = AdminOverride(
        id=5,
        claim_id=77,
        admin_actor_id="admin-1",
        command=AdminOverrideCommand.FORCE_APPROVE,
        reason_code="Manual goodwill approval after phone review",
        created_at="2026-04-05T14:00:00Z",
    )
    assert override.command == AdminOverrideCommand.FORCE_APPROVE
    assert override.reason_code == "Manual goodwill approval after phone review"


def test_actor_context_exposes_role_and_actor_id() -> None:
    context = ActorContext(role=Role.ASSESSOR, actor_id="assessor-1")
    assert context.role == Role.ASSESSOR
    assert context.actor_id == "assessor-1"


def test_claim_state_transition_exposes_required_fields() -> None:
    # F009 / E1-S2 AC4
    record = ClaimStateTransition(
        from_state=ClaimStatus.DOCS_PENDING,
        to_state=ClaimStatus.FRAUD_SCREENING,
        event="DOCS_VERIFIED",
        timestamp="2026-03-11T09:02:30Z",
        claim_id=42,
        actor_id="assessor-1",
    )
    assert record.from_state == ClaimStatus.DOCS_PENDING
    assert record.to_state == ClaimStatus.FRAUD_SCREENING
    assert record.event == "DOCS_VERIFIED"
    assert record.timestamp == "2026-03-11T09:02:30Z"
    assert record.claim_id == 42
    assert record.actor_id == "assessor-1"


def test_claim_state_transition_claim_id_and_actor_id_default_to_none() -> None:
    record = ClaimStateTransition(
        from_state=ClaimStatus.INTAKE,
        to_state=ClaimStatus.DOCS_PENDING,
        event="ATTACH_CHECKLIST",
        timestamp="2026-01-01T00:00:00Z",
    )
    assert record.claim_id is None
    assert record.actor_id is None


def test_monetary_fields_across_claim_assessment_settlement_are_decimal_never_float() -> None:
    # F005 / E1-S1 AC5
    for dataclass_type in (Claim, Assessment, Settlement):
        for field in dataclasses.fields(dataclass_type):
            if field.name in _MONEY_FIELD_NAMES:
                assert field.type is Decimal, (
                    f"{dataclass_type.__name__}.{field.name} must be typed Decimal, "
                    f"got {field.type!r}"
                )
                assert field.type is not float
