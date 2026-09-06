"""Unit tests for the five append-only audit repositories (E3-S4, F036/F038/F039).

Covers `fraud_screening_repository`, `assessment_repository`,
`decision_repository`, `settlement_repository`, and `admin_override_repository`.
Uses a local per-file fixture (real SQLite DB via `get_connection` +
`run_migrations`) rather than a shared `conftest.py` fixture, since
`backend/tests/conftest.py` is a file other concurrently-working agents may
also be touching.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.repositories.admin_override_repository import AdminOverrideRepository
from src.repositories.assessment_repository import AssessmentRepository
from src.repositories.decision_repository import DecisionRepository
from src.repositories.fraud_screening_repository import FraudScreeningRepository
from src.repositories.settlement_repository import SettlementRepository
from src.types.enums import (
    AdminOverrideCommand,
    ClaimType,
    DecisionOutcome,
    PolicyStatus,
    ReasonCode,
)

REAL_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def _seed_connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "claimflow.db"
    conn = get_connection(str(db_path))
    run_migrations(conn, str(REAL_MIGRATIONS_DIR))
    return conn


def _seed_claim(
    conn: sqlite3.Connection,
    *,
    policy_number: str = "POL-MOTOR-0001",
    claim_amount: str = "40000.00",
) -> int:
    """Insert a policy + claim row directly via raw SQL (FK prerequisite).

    `claim_repository.py` is owned by a concurrent E3-S3 teammate and may not
    exist yet in this working tree, so audit-repository tests seed their own
    claim rows rather than importing it.
    """
    policy_cursor = conn.execute(
        "INSERT INTO policies "
        "(policy_number, product_type, status, sum_insured, effective_date, "
        "expiry_date, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (
            policy_number,
            ClaimType.MOTOR.value,
            PolicyStatus.ACTIVE.value,
            "100000.00",
            "2026-01-01",
            "2026-12-31",
        ),
    )
    policy_id = policy_cursor.lastrowid

    claim_cursor = conn.execute(
        "INSERT INTO claims "
        "(policy_id, claim_type, incident_date, claim_amount, status, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (policy_id, ClaimType.MOTOR.value, "2026-03-10", claim_amount, "INTAKE"),
    )
    conn.commit()
    return int(claim_cursor.lastrowid)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = _seed_connection(tmp_path)
    yield connection
    connection.close()


@pytest.fixture
def claim_id(conn: sqlite3.Connection) -> int:
    return _seed_claim(conn)


# --- F036: FraudScreening insert() is append-only, no overwrite -----------


def test_fraud_screening_insert_twice_persists_both_rows_with_no_overwrite(
    conn: sqlite3.Connection, claim_id: int
) -> None:
    """F036: insert() twice for the same claim leaves both rows persisted."""
    repo = FraudScreeningRepository(conn)
    breakdown_1 = [{"rule_name": "HIGH_CLAIM_TO_SUM_RATIO", "weight": 40}]
    breakdown_2 = [
        {"rule_name": "HIGH_CLAIM_TO_SUM_RATIO", "weight": 40},
        {"rule_name": "EARLY_FILING", "weight": 25},
    ]

    first_id = repo.insert(claim_id, score=40, breakdown=breakdown_1, threshold=60, flagged=False)
    second_id = repo.insert(claim_id, score=65, breakdown=breakdown_2, threshold=60, flagged=True)

    assert first_id != second_id

    row_count = conn.execute(
        "SELECT COUNT(*) FROM fraud_screenings WHERE claim_id = ?", (claim_id,)
    ).fetchone()[0]
    assert row_count == 2

    latest = repo.get_latest(claim_id)
    assert latest is not None
    assert latest.id == second_id
    assert latest.score == 65
    assert latest.flagged is True
    assert latest.breakdown == breakdown_2

    first_row = conn.execute(
        "SELECT score, flagged FROM fraud_screenings WHERE id = ?", (first_id,)
    ).fetchone()
    assert first_row["score"] == 40
    assert bool(first_row["flagged"]) is False


def test_fraud_screening_get_latest_returns_none_when_no_screening_exists(
    conn: sqlite3.Connection, claim_id: int
) -> None:
    repo = FraudScreeningRepository(conn)

    assert repo.get_latest(claim_id) is None


# --- F038: Assessment get_latest_assessment() returns the last inserted ---


def test_assessment_get_latest_returns_most_recently_inserted_row(
    conn: sqlite3.Connection, claim_id: int
) -> None:
    """F038: multiple inserts -> get_latest_assessment() returns the LAST one."""
    repo = AssessmentRepository(conn)

    repo.insert(
        claim_id,
        claim_amount=Decimal("40000.00"),
        sum_insured=Decimal("100000.00"),
        deductible=Decimal("5000.00"),
        co_pay=Decimal("0.00"),
        payable_amount=Decimal("35000.00"),
    )
    second_id = repo.insert(
        claim_id,
        claim_amount=Decimal("42000.00"),
        sum_insured=Decimal("100000.00"),
        deductible=Decimal("5000.00"),
        co_pay=Decimal("0.00"),
        payable_amount=Decimal("37000.00"),
    )

    latest = repo.get_latest_assessment(claim_id)

    assert latest is not None
    assert latest.id == second_id
    assert latest.payable_amount == Decimal("37000.00")
    assert isinstance(latest.payable_amount, Decimal)


def test_assessment_get_latest_returns_none_when_no_assessment_exists(
    conn: sqlite3.Connection, claim_id: int
) -> None:
    repo = AssessmentRepository(conn)

    assert repo.get_latest_assessment(claim_id) is None


# --- Decision repository ---------------------------------------------------


def test_decision_insert_and_get_latest_round_trips_outcome_and_reason_code(
    conn: sqlite3.Connection, claim_id: int
) -> None:
    repo = DecisionRepository(conn)

    repo.insert(
        claim_id,
        outcome=DecisionOutcome.MANUAL_REVIEW,
        reason_code=ReasonCode.FRAUD_FLAG,
        decided_by="system",
    )
    second_id = repo.insert(
        claim_id,
        outcome=DecisionOutcome.AUTO_APPROVE,
        reason_code=ReasonCode.AUTO_APPROVED_LOW_RISK,
        decided_by="assessor-1",
    )

    latest = repo.get_latest(claim_id)

    assert latest is not None
    assert latest.id == second_id
    assert latest.outcome == DecisionOutcome.AUTO_APPROVE
    assert latest.reason_code == ReasonCode.AUTO_APPROVED_LOW_RISK
    assert latest.decided_by == "assessor-1"

    row_count = conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE claim_id = ?", (claim_id,)
    ).fetchone()[0]
    assert row_count == 2


def test_decision_get_latest_returns_none_when_no_decision_exists(
    conn: sqlite3.Connection, claim_id: int
) -> None:
    repo = DecisionRepository(conn)

    assert repo.get_latest(claim_id) is None


# --- Settlement repository --------------------------------------------------


def test_settlement_insert_and_list_all_returns_persisted_settlements(
    conn: sqlite3.Connection, claim_id: int
) -> None:
    decision_repo = DecisionRepository(conn)
    decision_id = decision_repo.insert(
        claim_id,
        outcome=DecisionOutcome.AUTO_APPROVE,
        reason_code=ReasonCode.AUTO_APPROVED_LOW_RISK,
        decided_by="system",
    )

    settlement_repo = SettlementRepository(conn)
    settlement_id = settlement_repo.insert(
        claim_id,
        decision_id=decision_id,
        payout_amount=Decimal("35000.00"),
        payment_reference="STUB-PAY-0000042-01",
    )

    settlements = settlement_repo.list_all()

    assert len(settlements) == 1
    assert settlements[0].id == settlement_id
    assert settlements[0].claim_id == claim_id
    assert settlements[0].decision_id == decision_id
    assert settlements[0].payout_amount == Decimal("35000.00")
    assert isinstance(settlements[0].payout_amount, Decimal)
    assert settlements[0].payment_reference == "STUB-PAY-0000042-01"


def test_settlement_list_all_returns_empty_list_when_no_settlements_exist(
    conn: sqlite3.Connection,
) -> None:
    repo = SettlementRepository(conn)

    assert repo.list_all() == []


# --- F039: AdminOverride list_admin_overrides() ordered ascending ---------


def test_admin_override_list_returns_rows_in_ascending_insertion_order(
    conn: sqlite3.Connection, claim_id: int
) -> None:
    """F039: multiple overrides -> list_admin_overrides() ordered oldest first."""
    repo = AdminOverrideRepository(conn)

    repo.insert(
        claim_id,
        admin_actor_id="admin-1",
        command=AdminOverrideCommand.FORCE_MANUAL_REVIEW,
        reason_code="Escalated for manual review after phone call.",
    )
    repo.insert(
        claim_id,
        admin_actor_id="admin-2",
        command=AdminOverrideCommand.FORCE_APPROVE,
        reason_code="Manual goodwill approval after phone review.",
    )
    repo.insert(
        claim_id,
        admin_actor_id="admin-1",
        command=AdminOverrideCommand.FORCE_REJECT,
        reason_code="Reversed after fraud confirmation.",
    )

    overrides = repo.list_admin_overrides(claim_id)

    assert len(overrides) == 3
    assert [o.command for o in overrides] == [
        AdminOverrideCommand.FORCE_MANUAL_REVIEW,
        AdminOverrideCommand.FORCE_APPROVE,
        AdminOverrideCommand.FORCE_REJECT,
    ]
    assert [o.admin_actor_id for o in overrides] == ["admin-1", "admin-2", "admin-1"]
    assert overrides[0].id < overrides[1].id < overrides[2].id


def test_admin_override_list_returns_empty_list_when_no_overrides_exist(
    conn: sqlite3.Connection, claim_id: int
) -> None:
    repo = AdminOverrideRepository(conn)

    assert repo.list_admin_overrides(claim_id) == []
