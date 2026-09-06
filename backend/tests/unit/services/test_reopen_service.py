"""Unit tests for `src.services.reopen_service` (E7-S2, F081-F084)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.repositories.claim_repository import ClaimRepository
from src.services.reopen_service import reopen
from src.types.enums import ClaimStatus, ClaimType, DecisionOutcome, PolicyStatus, ReasonCode
from src.types.exceptions import InvalidClaimStateException

REAL_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def _seed_connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "claimflow.db"
    conn = get_connection(str(db_path))
    run_migrations(conn, str(REAL_MIGRATIONS_DIR))
    return conn


def _insert_policy(
    conn: sqlite3.Connection,
    *,
    policy_number: str = "POL-001",
    product_type: str = ClaimType.MOTOR.value,
    status: str = PolicyStatus.ACTIVE.value,
    sum_insured: str = "500000.00",
    effective_date: str = "2025-01-01",
    expiry_date: str = "2025-12-31",
) -> int:
    cursor = conn.execute(
        "INSERT INTO policies "
        "(policy_number, product_type, status, sum_insured, effective_date, "
        "expiry_date, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (policy_number, product_type, status, sum_insured, effective_date, expiry_date),
    )
    conn.commit()
    policy_id = cursor.lastrowid
    assert policy_id is not None
    return policy_id


def _insert_claim_row(
    conn: sqlite3.Connection,
    *,
    policy_id: int,
    claim_type: str = ClaimType.MOTOR.value,
    incident_date: str = "2026-01-15",
    claim_amount: str = "10000.00",
    status: str = ClaimStatus.INTAKE.value,
) -> int:
    cursor = conn.execute(
        "INSERT INTO claims "
        "(policy_id, claim_type, incident_date, claim_amount, status, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (policy_id, claim_type, incident_date, claim_amount, status),
    )
    conn.commit()
    claim_id = cursor.lastrowid
    assert claim_id is not None
    return claim_id


def _insert_decision(
    conn: sqlite3.Connection,
    *,
    claim_id: int,
    outcome: str = DecisionOutcome.AUTO_APPROVE.value,
    reason_code: str = ReasonCode.AUTO_APPROVED_LOW_RISK.value,
    decided_by: str = "system",
) -> int:
    cursor = conn.execute(
        "INSERT INTO decisions "
        "(claim_id, outcome, reason_code, decided_by, created_at) "
        "VALUES (?, ?, ?, ?, datetime('now'))",
        (claim_id, outcome, reason_code, decided_by),
    )
    conn.commit()
    decision_id = cursor.lastrowid
    assert decision_id is not None
    return decision_id


def _insert_settlement(
    conn: sqlite3.Connection,
    *,
    claim_id: int,
    decision_id: int,
    payout_amount: str = "10000.00",
    payment_reference: str = "PAY-REF-001",
) -> int:
    cursor = conn.execute(
        "INSERT INTO settlements "
        "(claim_id, decision_id, payout_amount, payment_reference, created_at) "
        "VALUES (?, ?, ?, ?, datetime('now'))",
        (claim_id, decision_id, payout_amount, payment_reference),
    )
    conn.commit()
    settlement_id = cursor.lastrowid
    assert settlement_id is not None
    return settlement_id


def _insert_assessment(
    conn: sqlite3.Connection,
    *,
    claim_id: int,
    claim_amount: str = "10000.00",
    sum_insured: str = "500000.00",
    deductible: str = "500.00",
    co_pay: str = "0.00",
    payable_amount: str = "9500.00",
) -> int:
    cursor = conn.execute(
        "INSERT INTO assessments "
        "(claim_id, claim_amount, sum_insured, deductible, co_pay, payable_amount, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (claim_id, claim_amount, sum_insured, deductible, co_pay, payable_amount),
    )
    conn.commit()
    assessment_id = cursor.lastrowid
    assert assessment_id is not None
    return assessment_id


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = _seed_connection(tmp_path)
    yield connection
    connection.close()


@pytest.fixture
def policy_id(conn: sqlite3.Connection) -> int:
    return _insert_policy(conn)


class TestReopenCreatesSubClaim:
    """F081: a new Claim row is created with parent_claim_id set to the
    original's id and status='INTAKE'."""

    def test_reopen_settled_claim_creates_intake_sub_claim(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        original_id = _insert_claim_row(
            conn,
            policy_id=policy_id,
            claim_type=ClaimType.MOTOR.value,
            incident_date="2026-01-15",
            claim_amount="10000.00",
            status=ClaimStatus.SETTLED.value,
        )

        sub_claim = reopen(conn, original_id, actor_id="customer-1")

        assert sub_claim.id != original_id
        assert sub_claim.parent_claim_id == original_id
        assert sub_claim.status == ClaimStatus.INTAKE
        assert sub_claim.policy_id == policy_id
        assert sub_claim.claim_type == ClaimType.MOTOR
        assert sub_claim.incident_date == "2026-01-15"
        assert sub_claim.claim_amount == Decimal("10000.00")

        # Re-query directly -- don't just trust the return value.
        repo = ClaimRepository(conn)
        persisted = repo.get_by_id(sub_claim.id)
        assert persisted is not None
        assert persisted.parent_claim_id == original_id
        assert persisted.status == ClaimStatus.INTAKE


class TestReopenLeavesHistoryUntouched:
    """F082: the original claim's Decision, Settlement, and Assessment rows
    are unchanged: still readable, not deleted or edited."""

    def test_reopen_does_not_mutate_decision_settlement_assessment_rows(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        original_id = _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.SETTLED.value,
        )
        decision_id = _insert_decision(conn, claim_id=original_id)
        _insert_settlement(conn, claim_id=original_id, decision_id=decision_id)
        _insert_assessment(conn, claim_id=original_id)

        decision_before = dict(
            conn.execute("SELECT * FROM decisions WHERE claim_id = ?", (original_id,)).fetchone()
        )
        settlement_before = dict(
            conn.execute(
                "SELECT * FROM settlements WHERE claim_id = ?", (original_id,)
            ).fetchone()
        )
        assessment_before = dict(
            conn.execute(
                "SELECT * FROM assessments WHERE claim_id = ?", (original_id,)
            ).fetchone()
        )

        reopen(conn, original_id)

        decision_after = dict(
            conn.execute("SELECT * FROM decisions WHERE claim_id = ?", (original_id,)).fetchone()
        )
        settlement_after = dict(
            conn.execute(
                "SELECT * FROM settlements WHERE claim_id = ?", (original_id,)
            ).fetchone()
        )
        assessment_after = dict(
            conn.execute(
                "SELECT * FROM assessments WHERE claim_id = ?", (original_id,)
            ).fetchone()
        )

        assert decision_after == decision_before
        assert settlement_after == settlement_before
        assert assessment_after == assessment_before


class TestReopenMarksOriginalReopenedViaGate:
    """F083: the original claim's status is re-read as REOPENED, set via the
    state-machine gate rather than a direct column write."""

    def test_reopen_transitions_original_to_reopened_via_gate(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        original_id = _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.SETTLED.value,
        )

        reopen(conn, original_id, actor_id="customer-2")

        repo = ClaimRepository(conn)
        original = repo.get_by_id(original_id)
        assert original is not None
        assert original.status == ClaimStatus.REOPENED

        transition_rows = conn.execute(
            "SELECT * FROM claim_state_transitions WHERE claim_id = ?", (original_id,)
        ).fetchall()
        assert len(transition_rows) == 1
        assert transition_rows[0]["from_state"] == ClaimStatus.SETTLED.value
        assert transition_rows[0]["to_state"] == ClaimStatus.REOPENED.value
        assert transition_rows[0]["event"] == "REOPEN"
        assert transition_rows[0]["actor_id"] == "customer-2"


class TestReopenRejectsNonSettledClaim:
    """F084: reopening a claim that is not SETTLED raises
    InvalidClaimStateException, leaving the claim and claims table unchanged."""

    def test_reopen_non_settled_claim_raises_and_creates_no_sub_claim(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        original_id = _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.MANUAL_REVIEW.value,
        )

        claims_count_before = conn.execute("SELECT COUNT(*) AS n FROM claims").fetchone()["n"]

        with pytest.raises(InvalidClaimStateException):
            reopen(conn, original_id)

        claims_count_after = conn.execute("SELECT COUNT(*) AS n FROM claims").fetchone()["n"]
        assert claims_count_after == claims_count_before

        repo = ClaimRepository(conn)
        original = repo.get_by_id(original_id)
        assert original is not None
        assert original.status == ClaimStatus.MANUAL_REVIEW


class TestReopenClaimNotFound:
    """Defensive: reopening a nonexistent claim_id fails loudly rather than
    silently creating an orphan sub-claim."""

    def test_reopen_raises_lookup_error_for_unknown_claim_id(
        self, conn: sqlite3.Connection
    ) -> None:
        with pytest.raises(LookupError):
            reopen(conn, 999)
