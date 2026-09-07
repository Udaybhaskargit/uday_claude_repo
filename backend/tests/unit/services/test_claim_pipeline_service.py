"""Unit tests for `src.services.claim_pipeline_service` (E6-S3, F073-F076)."""

from __future__ import annotations

import json
import logging
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
from src.services import claim_pipeline_service
from src.services.claim_pipeline_service import PipelineResult, retry_pipeline, run_pipeline
from src.services.document_checklist_service import verify_document
from src.services.fnol_intake_service import submit_fnol
from src.types.enums import ClaimStatus, ClaimType, DocumentType
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


def _insert_policy(conn: sqlite3.Connection, *, policy_number: str = "POL-001") -> None:
    conn.execute(
        "INSERT INTO policies "
        "(policy_number, product_type, status, sum_insured, effective_date, "
        "expiry_date, created_at) VALUES (?, 'MOTOR', 'ACTIVE', '500000.00', "
        "'2025-01-01', '2026-12-31', datetime('now'))",
        (policy_number,),
    )
    conn.commit()


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = _seed_connection(tmp_path)
    yield connection
    connection.close()


def _claim_with_complete_docs(conn: sqlite3.Connection, *, policy_number: str = "POL-001") -> int:
    """A motor claim still in DOCS_PENDING with every checklist item VERIFIED.

    Matches E6-S3 AC1's "Given a claim with complete documents" scenario
    literally: the documents are verified but nothing has yet called
    `check_documents_complete()` to fire the DOCS_PENDING -> FRAUD_SCREENING
    transition -- that's `run_pipeline()`'s own job to do internally.
    """
    _insert_policy(conn, policy_number=policy_number)
    claim = submit_fnol(
        conn,
        policy_number=policy_number,
        claim_type=ClaimType.MOTOR,
        incident_date="2026-03-10",
        claim_amount=Decimal("40000.00"),
    )
    verify_document(conn, claim.id, DocumentType.POLICE_FIR)
    verify_document(conn, claim.id, DocumentType.INVOICE)
    assert ClaimRepository(conn).get_by_id(claim.id).status == ClaimStatus.DOCS_PENDING  # type: ignore[union-attr]
    return claim.id


class TestEndsInOneTerminalStateWithDecision:
    def test_no_fraud_flag_ends_auto_approved_with_decision_row(
        self, conn: sqlite3.Connection
    ) -> None:
        """F073."""
        claim_id = _claim_with_complete_docs(conn)

        result = run_pipeline(conn, claim_id, _NEVER_FLAG_CONFIG, _MOTOR_RULES)

        assert result == PipelineResult(claim_id, ClaimStatus.AUTO_APPROVED)
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.AUTO_APPROVED
        decision = DecisionRepository(conn).get_latest(claim_id)
        assert decision is not None
        assert decision.decided_by == "system"

    def test_no_fraud_flag_high_value_ends_manual_review_with_decision_row(
        self, conn: sqlite3.Connection
    ) -> None:
        """F073: the ceiling-exceeded path is also a valid terminal state."""
        low_ceiling_rules = AssessmentRulesConfig(
            rules_by_claim_type=_MOTOR_RULES.rules_by_claim_type,
            auto_approve_ceiling=100,
        )
        claim_id = _claim_with_complete_docs(conn)

        result = run_pipeline(conn, claim_id, _NEVER_FLAG_CONFIG, low_ceiling_rules)

        assert result == PipelineResult(claim_id, ClaimStatus.MANUAL_REVIEW)
        decision = DecisionRepository(conn).get_latest(claim_id)
        assert decision is not None


class TestHaltsAtDocsPendingWhenIncomplete:
    def test_incomplete_docs_halts_without_calling_fraud_or_assessment(
        self, conn: sqlite3.Connection
    ) -> None:
        """F074."""
        _insert_policy(conn)
        claim = submit_fnol(
            conn,
            policy_number="POL-001",
            claim_type=ClaimType.MOTOR,
            incident_date="2026-03-10",
            claim_amount=Decimal("40000.00"),
        )
        verify_document(conn, claim.id, DocumentType.POLICE_FIR)
        # INVOICE deliberately left MISSING.

        result = run_pipeline(conn, claim.id, _NEVER_FLAG_CONFIG, _MOTOR_RULES)

        assert result == PipelineResult(claim.id, ClaimStatus.DOCS_PENDING)
        reloaded = ClaimRepository(conn).get_by_id(claim.id)
        assert reloaded is not None
        assert reloaded.status == ClaimStatus.DOCS_PENDING
        assert FraudScreeningRepository(conn).get_latest(claim.id) is None
        assert AssessmentRepository(conn).get_latest_assessment(claim.id) is None
        assert DecisionRepository(conn).get_latest(claim.id) is None


class TestUnexpectedFailureRoutesToProcessingFailed:
    def test_fraud_screening_failure_transitions_to_processing_failed_and_logs_no_pii(
        self,
        conn: sqlite3.Connection,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """F075."""
        claim_id = _claim_with_complete_docs(conn)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("simulated fraud-screening outage")

        monkeypatch.setattr(claim_pipeline_service, "run_fraud_screening", _boom)

        with caplog.at_level(logging.ERROR):
            result = run_pipeline(conn, claim_id, _NEVER_FLAG_CONFIG, _MOTOR_RULES)

        assert result == PipelineResult(claim_id, ClaimStatus.PROCESSING_FAILED)
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.PROCESSING_FAILED

        assert len(caplog.records) == 1
        payload = json.loads(caplog.records[0].message)
        assert payload == {
            "event": "pipeline_error",
            "claim_id": claim_id,
            "step": "fraud_screening",
            "error_type": "RuntimeError",
        }
        # No PII/claim-narrative content anywhere in the log record.
        assert "simulated fraud-screening outage" not in caplog.records[0].message
        assert "40000.00" not in caplog.records[0].message
        assert "2026-03-10" not in caplog.records[0].message

    def test_decision_failure_transitions_to_processing_failed(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F075: the decision/assessment step is wrapped the same way."""
        claim_id = _claim_with_complete_docs(conn)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise ValueError("simulated decision outage")

        monkeypatch.setattr(claim_pipeline_service, "run_decision", _boom)

        result = run_pipeline(conn, claim_id, _NEVER_FLAG_CONFIG, _MOTOR_RULES)

        assert result == PipelineResult(claim_id, ClaimStatus.PROCESSING_FAILED)
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.PROCESSING_FAILED
        # run_decision() itself is replaced wholesale by the mock here, so
        # nothing inside it (including its own Assessment insert) ran.
        assert AssessmentRepository(conn).get_latest_assessment(claim_id) is None
        assert DecisionRepository(conn).get_latest(claim_id) is None


class TestRetryPipelineResumesFromFailedStep:
    def test_retry_after_fraud_screening_failure_resumes_and_completes(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F076."""
        claim_id = _claim_with_complete_docs(conn)
        real_run_fraud_screening = claim_pipeline_service.run_fraud_screening
        call_count = {"n": 0}

        def _fail_once(*args: object, **kwargs: object) -> object:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated transient outage")
            return real_run_fraud_screening(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(claim_pipeline_service, "run_fraud_screening", _fail_once)

        failed = run_pipeline(conn, claim_id, _NEVER_FLAG_CONFIG, _MOTOR_RULES)
        assert failed.status == ClaimStatus.PROCESSING_FAILED

        result = retry_pipeline(conn, claim_id, _NEVER_FLAG_CONFIG, _MOTOR_RULES)

        assert result == PipelineResult(claim_id, ClaimStatus.AUTO_APPROVED)
        assert call_count["n"] == 2
        decision = DecisionRepository(conn).get_latest(claim_id)
        assert decision is not None

        transitions = conn.execute(
            "SELECT event FROM claim_state_transitions WHERE claim_id = ? ORDER BY id",
            (claim_id,),
        ).fetchall()
        events = [row["event"] for row in transitions]
        assert "PIPELINE_ERROR" in events
        assert "RETRY_TO_FRAUD_SCREENING" in events

    def test_retry_after_decision_failure_resumes_from_assessment(
        self, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F076: a failure in the decision step retries back into ASSESSMENT."""
        claim_id = _claim_with_complete_docs(conn)
        real_run_decision = claim_pipeline_service.run_decision
        call_count = {"n": 0}

        def _fail_once(*args: object, **kwargs: object) -> object:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated transient outage")
            return real_run_decision(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(claim_pipeline_service, "run_decision", _fail_once)

        failed = run_pipeline(conn, claim_id, _NEVER_FLAG_CONFIG, _MOTOR_RULES)
        assert failed.status == ClaimStatus.PROCESSING_FAILED

        result = retry_pipeline(conn, claim_id, _NEVER_FLAG_CONFIG, _MOTOR_RULES)

        assert result == PipelineResult(claim_id, ClaimStatus.AUTO_APPROVED)

        transitions = conn.execute(
            "SELECT event FROM claim_state_transitions WHERE claim_id = ? ORDER BY id",
            (claim_id,),
        ).fetchall()
        events = [row["event"] for row in transitions]
        assert "RETRY_TO_ASSESSMENT" in events


class TestRetryPipelineWithNoRecoverableStep:
    def test_raises_when_last_transition_is_not_a_known_failure_step(
        self, conn: sqlite3.Connection
    ) -> None:
        """F076: a claim with no recorded PIPELINE_ERROR-eligible history."""
        _insert_policy(conn)
        policy_id = conn.execute(
            "SELECT id FROM policies WHERE policy_number = 'POL-001'"
        ).fetchone()["id"]
        cursor = conn.execute(
            "INSERT INTO claims (policy_id, claim_type, incident_date, claim_amount, "
            "status, created_at, updated_at) VALUES "
            "(?, 'MOTOR', '2026-01-01', '10000.00', 'PROCESSING_FAILED', "
            "datetime('now'), datetime('now'))",
            (policy_id,),
        )
        conn.commit()
        claim_id = cursor.lastrowid
        assert claim_id is not None

        with pytest.raises(InvalidClaimStateException):
            retry_pipeline(conn, claim_id, _NEVER_FLAG_CONFIG, _MOTOR_RULES)


class TestUnknownClaimId:
    def test_run_pipeline_raises_lookup_error(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(LookupError):
            run_pipeline(conn, 999999, _NEVER_FLAG_CONFIG, _MOTOR_RULES)

    def test_retry_pipeline_raises_lookup_error(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(LookupError):
            retry_pipeline(conn, 999999, _NEVER_FLAG_CONFIG, _MOTOR_RULES)
