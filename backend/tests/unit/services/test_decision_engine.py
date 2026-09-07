"""Unit tests for `src.services.decision_engine` (E6-S2, F068-F072)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from src.config.assessment_rules_config import AssessmentRulesConfig, ClaimTypeRules
from src.config.fraud_rules_config import FraudRulesConfig
from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.repositories.assessment_repository import AssessmentRepository
from src.repositories.claim_repository import ClaimRepository
from src.repositories.decision_repository import DecisionRepository
from src.repositories.fraud_screening_repository import FraudScreeningRepository
from src.services.decision_engine import DecisionComputation, decide, run_decision
from src.services.document_checklist_service import check_documents_complete, verify_document
from src.services.fnol_intake_service import submit_fnol
from src.services.fraud_screening_service import run_fraud_screening
from src.types.enums import ClaimStatus, ClaimType, DecisionOutcome, DocumentType, ReasonCode
from src.types.exceptions import InvalidClaimStateException

REAL_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"

_ALWAYS_FLAG_CONFIG = FraudRulesConfig(rules=(), threshold=0)
_NEVER_FLAG_CONFIG = FraudRulesConfig(rules=(), threshold=1)

_MOTOR_RULES = AssessmentRulesConfig(
    rules_by_claim_type={
        ClaimType.MOTOR: ClaimTypeRules(deductible=5000, co_pay_pct=0),
        ClaimType.HEALTH: ClaimTypeRules(deductible=1000, co_pay_pct=10),
        ClaimType.LIFE: ClaimTypeRules(deductible=0, co_pay_pct=0),
    },
    auto_approve_ceiling=50000,
)


def _seed_connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "claimflow.db"
    conn = get_connection(str(db_path))
    run_migrations(conn, str(REAL_MIGRATIONS_DIR))
    return conn


def _insert_policy(conn: sqlite3.Connection, *, policy_number: str, sum_insured: str) -> None:
    conn.execute(
        "INSERT INTO policies "
        "(policy_number, product_type, status, sum_insured, effective_date, "
        "expiry_date, created_at) VALUES (?, 'MOTOR', 'ACTIVE', ?, "
        "'2025-01-01', '2026-12-31', datetime('now'))",
        (policy_number, sum_insured),
    )
    conn.commit()


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = _seed_connection(tmp_path)
    yield connection
    connection.close()


def _claim_in_assessment(
    conn: sqlite3.Connection,
    *,
    claim_amount: Decimal,
    sum_insured: str,
    policy_number: str,
    fraud_config: FraudRulesConfig,
) -> int:
    """Advance a fresh motor claim through the pipeline into ASSESSMENT."""
    _insert_policy(conn, policy_number=policy_number, sum_insured=sum_insured)
    claim = submit_fnol(
        conn,
        policy_number=policy_number,
        claim_type=ClaimType.MOTOR,
        incident_date="2026-03-10",
        claim_amount=claim_amount,
    )
    verify_document(conn, claim.id, DocumentType.POLICE_FIR)
    verify_document(conn, claim.id, DocumentType.INVOICE)
    assert check_documents_complete(conn, claim.id) is True
    run_fraud_screening(conn, claim.id, fraud_config)
    claim_after = ClaimRepository(conn).get_by_id(claim.id)
    assert claim_after is not None
    assert claim_after.status == ClaimStatus.ASSESSMENT
    return claim.id


class TestDecidePure:
    """Direct tests of the pure `decide()` rule, independent of persistence."""

    def test_zero_payable_amount_rejects_even_if_flagged(self) -> None:
        """F068 -- AC1 takes precedence over AC2."""
        result = decide(Decimal("0.00"), flagged=True, auto_approve_ceiling=Decimal("50000"))

        assert result == DecisionComputation(DecisionOutcome.REJECT, ReasonCode.ZERO_PAYABLE_AMOUNT)

    def test_flagged_nonzero_goes_to_manual_review(self) -> None:
        """F069."""
        result = decide(Decimal("30000.00"), flagged=True, auto_approve_ceiling=Decimal("50000"))

        assert result == DecisionComputation(DecisionOutcome.MANUAL_REVIEW, ReasonCode.FRAUD_FLAG)

    def test_unflagged_at_ceiling_auto_approves(self) -> None:
        """F070: at the ceiling itself, not just below it."""
        result = decide(Decimal("50000.00"), flagged=False, auto_approve_ceiling=Decimal("50000"))

        assert result == DecisionComputation(
            DecisionOutcome.AUTO_APPROVE, ReasonCode.AUTO_APPROVED_LOW_RISK
        )

    def test_unflagged_above_ceiling_requires_manual_review(self) -> None:
        """F071."""
        result = decide(Decimal("75000.00"), flagged=False, auto_approve_ceiling=Decimal("50000"))

        assert result == DecisionComputation(
            DecisionOutcome.MANUAL_REVIEW, ReasonCode.HIGH_VALUE_REVIEW
        )


class TestRunDecisionZeroPayable:
    def test_rejects_and_transitions_to_rejected(self, conn: sqlite3.Connection) -> None:
        """F068: claim_amount equal to the deductible yields payable_amount 0."""
        claim_id = _claim_in_assessment(
            conn,
            claim_amount=Decimal("5000.00"),
            sum_insured="500000.00",
            policy_number="POL-ZERO",
            fraud_config=_NEVER_FLAG_CONFIG,
        )

        decision = run_decision(conn, claim_id, _MOTOR_RULES)

        assert decision.outcome == DecisionOutcome.REJECT
        assert decision.reason_code == ReasonCode.ZERO_PAYABLE_AMOUNT
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.REJECTED


class TestRunDecisionFraudFlagged:
    def test_manual_review_and_transitions_to_manual_review(self, conn: sqlite3.Connection) -> None:
        """F069.

        `fraud_screening_service` itself already gates a flagged claim to
        MANUAL_REVIEW rather than ASSESSMENT (E5-S3 AC2), so a claim cannot
        reach ASSESSMENT via the normal pipeline carrying a flagged *first*
        screening. To exercise `run_decision()`'s own AC2 handling in
        isolation, this reaches ASSESSMENT normally (unflagged) and then
        inserts one further `FraudScreening` row directly with
        `flagged=True` -- standing in for a later re-screening (e.g. a
        retry) whose gating transition is Group H's not-yet-built
        `retry_pipeline()` -- so `get_latest()` returns the flagged row
        while the claim is still in ASSESSMENT.
        """
        claim_id = _claim_in_assessment(
            conn,
            claim_amount=Decimal("40000.00"),
            sum_insured="500000.00",
            policy_number="POL-FLAGGED",
            fraud_config=_NEVER_FLAG_CONFIG,
        )
        FraudScreeningRepository(conn).insert(
            claim_id, score=100, breakdown=[], threshold=60, flagged=True
        )

        decision = run_decision(conn, claim_id, _MOTOR_RULES)

        assert decision.outcome == DecisionOutcome.MANUAL_REVIEW
        assert decision.reason_code == ReasonCode.FRAUD_FLAG
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.MANUAL_REVIEW


class TestRunDecisionAutoApprove:
    def test_auto_approves_and_transitions_to_auto_approved(self, conn: sqlite3.Connection) -> None:
        """F070: claim_amount 35000 - 5000 deductible = payable_amount 30000."""
        claim_id = _claim_in_assessment(
            conn,
            claim_amount=Decimal("35000.00"),
            sum_insured="500000.00",
            policy_number="POL-AUTO",
            fraud_config=_NEVER_FLAG_CONFIG,
        )

        decision = run_decision(conn, claim_id, _MOTOR_RULES)

        assert decision.outcome == DecisionOutcome.AUTO_APPROVE
        assert decision.reason_code == ReasonCode.AUTO_APPROVED_LOW_RISK
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.AUTO_APPROVED
        assessment = AssessmentRepository(conn).get_latest_assessment(claim_id)
        assert assessment is not None
        assert assessment.payable_amount == Decimal("30000.00")


class TestRunDecisionHighValue:
    def test_manual_review_for_above_ceiling(self, conn: sqlite3.Connection) -> None:
        """F071: claim_amount 80000 - 5000 deductible = payable_amount 75000."""
        claim_id = _claim_in_assessment(
            conn,
            claim_amount=Decimal("80000.00"),
            sum_insured="500000.00",
            policy_number="POL-HIGH",
            fraud_config=_NEVER_FLAG_CONFIG,
        )

        decision = run_decision(conn, claim_id, _MOTOR_RULES)

        assert decision.outcome == DecisionOutcome.MANUAL_REVIEW
        assert decision.reason_code == ReasonCode.HIGH_VALUE_REVIEW
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.MANUAL_REVIEW


class TestDecisionRowAppendOnlyAndDecidedBy:
    def test_records_system_as_decided_by_default(self, conn: sqlite3.Connection) -> None:
        """F072."""
        claim_id = _claim_in_assessment(
            conn,
            claim_amount=Decimal("35000.00"),
            sum_insured="500000.00",
            policy_number="POL-SYSTEM",
            fraud_config=_NEVER_FLAG_CONFIG,
        )

        decision = run_decision(conn, claim_id, _MOTOR_RULES)

        assert decision.decided_by == "system"

    def test_records_an_explicit_assessor_actor_id(self, conn: sqlite3.Connection) -> None:
        """F072."""
        claim_id = _claim_in_assessment(
            conn,
            claim_amount=Decimal("35000.00"),
            sum_insured="500000.00",
            policy_number="POL-ASSESSOR",
            fraud_config=_NEVER_FLAG_CONFIG,
        )

        decision = run_decision(conn, claim_id, _MOTOR_RULES, decided_by="assessor-42")

        assert decision.decided_by == "assessor-42"

    def test_row_is_append_only_via_repository_reflection(self) -> None:
        """F072: mirrors the E3-S4 reflection guard -- no update()/delete() exists."""
        public_methods = {
            name
            for name in dir(DecisionRepository)
            if not name.startswith("_")
        }
        assert "update" not in public_methods
        assert "delete" not in public_methods


class TestRunDecisionInvalidState:
    def test_raises_when_claim_is_not_in_assessment(self, conn: sqlite3.Connection) -> None:
        """A second decision run against an already-decided claim cannot silently re-apply."""
        claim_id = _claim_in_assessment(
            conn,
            claim_amount=Decimal("35000.00"),
            sum_insured="500000.00",
            policy_number="POL-DOUBLE",
            fraud_config=_NEVER_FLAG_CONFIG,
        )
        run_decision(conn, claim_id, _MOTOR_RULES)

        with pytest.raises(InvalidClaimStateException):
            run_decision(conn, claim_id, _MOTOR_RULES)


class TestUnknownClaimId:
    def test_raises_lookup_error(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(LookupError):
            run_decision(conn, 999999, _MOTOR_RULES)
