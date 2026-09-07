"""Unit tests for `src.services.settlement_service` (E7-S1, F077-F080)."""

from __future__ import annotations

import inspect
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.repositories.claim_repository import ClaimRepository
from src.repositories.settlement_repository import SettlementRepository
from src.services.settlement_service import settle
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
    claim_amount: str = "40000.00",
    status: str = ClaimStatus.AUTO_APPROVED.value,
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


def _insert_assessment(
    conn: sqlite3.Connection,
    *,
    claim_id: int,
    claim_amount: str = "40000.00",
    sum_insured: str = "500000.00",
    deductible: str = "5000.00",
    co_pay: str = "0.00",
    payable_amount: str = "35000.00",
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


def _approved_claim_ready_for_settlement(
    conn: sqlite3.Connection, policy_id: int
) -> tuple[int, int]:
    """An AUTO_APPROVED claim with its Assessment/Decision rows in place."""
    claim_id = _insert_claim_row(conn, policy_id=policy_id, status=ClaimStatus.AUTO_APPROVED.value)
    _insert_assessment(conn, claim_id=claim_id)
    decision_id = _insert_decision(conn, claim_id=claim_id)
    return claim_id, decision_id


class TestSettleCreatesSettlementAndMovesToSettled:
    """F077: a Settlement row is created with the decision's payable_amount
    and the claim transitions to SETTLED."""

    def test_settle_auto_approved_claim_creates_settlement_and_settles(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id, decision_id = _approved_claim_ready_for_settlement(conn, policy_id)

        settlement = settle(conn, claim_id, actor_id="admin-1")

        assert settlement.claim_id == claim_id
        assert settlement.decision_id == decision_id
        assert settlement.payout_amount == Decimal("35000.00")
        assert settlement.payment_reference

        # Re-query directly -- don't just trust the return value.
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.SETTLED

        rows = conn.execute(
            "SELECT * FROM settlements WHERE claim_id = ?", (claim_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["payout_amount"] == "35000.00"
        assert rows[0]["decision_id"] == decision_id

        transition_rows = conn.execute(
            "SELECT * FROM claim_state_transitions WHERE claim_id = ?", (claim_id,)
        ).fetchall()
        assert len(transition_rows) == 1
        assert transition_rows[0]["from_state"] == ClaimStatus.AUTO_APPROVED.value
        assert transition_rows[0]["to_state"] == ClaimStatus.SETTLED.value
        assert transition_rows[0]["event"] == "SETTLE"
        assert transition_rows[0]["actor_id"] == "admin-1"


class TestSettlementRepositoryHasNoUpdateMethod:
    """F078: no update method exists on the Settlement repository, since the
    repository (E3-S4) enforces immutability -- a genuine reflection check on
    the live class, not a static assumption."""

    def test_settlement_repository_exposes_no_update_or_delete(self) -> None:
        public_methods = {
            name
            for name, _ in inspect.getmembers(SettlementRepository, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        assert "update" not in {name.lower() for name in public_methods}
        assert "delete" not in {name.lower() for name in public_methods}


class TestSettlePaymentTriggerIsStubbed:
    """F079: the stubbed payment trigger returns a stub confirmation
    reference without contacting any real external payment rail."""

    def test_payment_reference_is_a_stub_with_no_external_call(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id, _ = _approved_claim_ready_for_settlement(conn, policy_id)

        settlement = settle(conn, claim_id)

        assert isinstance(settlement.payment_reference, str)
        assert settlement.payment_reference.startswith("STUB-PAY-")

        # No network/payment-rail client library is imported by this module --
        # confirms the "trigger" never leaves the process, not just that this
        # one call happened not to raise. Checked against the module's own
        # `__dict__` (bound names after import), not a docstring-sensitive
        # source-text grep.
        import src.services.settlement_service as module

        bound_names = {name.lower() for name in vars(module)}
        for forbidden in ("requests", "httpx", "urllib", "socket"):
            assert forbidden not in bound_names

    def test_two_settlements_get_distinct_references(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_a, _ = _approved_claim_ready_for_settlement(conn, policy_id)
        other_policy = _insert_policy(conn, policy_number="POL-002")
        claim_b, _ = _approved_claim_ready_for_settlement(conn, other_policy)

        settlement_a = settle(conn, claim_a)
        settlement_b = settle(conn, claim_b)

        assert settlement_a.payment_reference != settlement_b.payment_reference


class TestSettleRefusesNonApprovedClaim:
    """F080: settlement is refused with a typed error and no Settlement row
    is created for a non-approved (e.g. REJECTED) claim."""

    def test_settle_rejected_claim_raises_and_creates_no_settlement(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id = _insert_claim_row(conn, policy_id=policy_id, status=ClaimStatus.REJECTED.value)

        settlements_before = conn.execute("SELECT COUNT(*) AS n FROM settlements").fetchone()["n"]

        with pytest.raises(InvalidClaimStateException):
            settle(conn, claim_id)

        settlements_after = conn.execute("SELECT COUNT(*) AS n FROM settlements").fetchone()["n"]
        assert settlements_after == settlements_before

        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.REJECTED

    def test_settle_manual_review_claim_raises_and_creates_no_settlement(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id = _insert_claim_row(
            conn, policy_id=policy_id, status=ClaimStatus.MANUAL_REVIEW.value
        )

        with pytest.raises(InvalidClaimStateException):
            settle(conn, claim_id)

        settlements = conn.execute(
            "SELECT COUNT(*) AS n FROM settlements WHERE claim_id = ?", (claim_id,)
        ).fetchone()["n"]
        assert settlements == 0


class TestSettleClaimNotFound:
    """Defensive: settling a nonexistent claim_id fails loudly."""

    def test_settle_raises_lookup_error_for_unknown_claim_id(
        self, conn: sqlite3.Connection
    ) -> None:
        with pytest.raises(LookupError):
            settle(conn, 999)
