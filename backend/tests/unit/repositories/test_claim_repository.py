"""Unit tests for `src.repositories.claim_repository` (E3-S3, F031-F035)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.repositories.claim_repository import ClaimRepository
from src.types.enums import ClaimEvent, ClaimStatus, ClaimType, PolicyStatus
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


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = _seed_connection(tmp_path)
    yield connection
    connection.close()


@pytest.fixture
def policy_id(conn: sqlite3.Connection) -> int:
    return _insert_policy(conn)


class TestCreate:
    """F031: create() inserts with status='INTAKE' and returns the generated id."""

    def test_create_inserts_row_with_intake_status_and_returns_id(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        repo = ClaimRepository(conn)

        claim_id = repo.create(
            policy_id=policy_id,
            claim_type=ClaimType.MOTOR,
            incident_date="2026-03-10",
            claim_amount=Decimal("40000.00"),
        )

        assert isinstance(claim_id, int)

        row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        assert row is not None
        assert row["status"] == ClaimStatus.INTAKE.value
        assert row["policy_id"] == policy_id
        assert row["claim_type"] == ClaimType.MOTOR.value
        assert row["incident_date"] == "2026-03-10"
        assert row["claim_amount"] == "40000.00"
        assert row["created_at"] is not None
        assert row["updated_at"] is not None

    def test_create_stores_claim_amount_as_canonical_decimal_string(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        repo = ClaimRepository(conn)

        claim_id = repo.create(
            policy_id=policy_id,
            claim_type=ClaimType.HEALTH,
            incident_date="2026-04-01",
            claim_amount=Decimal("1500"),
        )

        row = conn.execute(
            "SELECT claim_amount FROM claims WHERE id = ?", (claim_id,)
        ).fetchone()
        assert row["claim_amount"] == str(Decimal("1500"))


class TestGetById:
    def test_get_by_id_returns_typed_claim(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        repo = ClaimRepository(conn)
        claim_id = repo.create(
            policy_id=policy_id,
            claim_type=ClaimType.LIFE,
            incident_date="2026-02-01",
            claim_amount=Decimal("99999.99"),
        )

        claim = repo.get_by_id(claim_id)

        assert claim is not None
        assert claim.id == claim_id
        assert claim.policy_id == policy_id
        assert claim.claim_type == ClaimType.LIFE
        assert claim.incident_date == "2026-02-01"
        assert claim.claim_amount == Decimal("99999.99")
        assert claim.status == ClaimStatus.INTAKE

    def test_get_by_id_returns_none_when_not_found(self, conn: sqlite3.Connection) -> None:
        repo = ClaimRepository(conn)

        assert repo.get_by_id(999) is None


class TestApplyTransition:
    """F032/F033: apply_transition() success and failure paths."""

    def test_valid_event_updates_status_and_inserts_transition_row(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id = _insert_claim_row(conn, policy_id=policy_id, status=ClaimStatus.INTAKE.value)
        repo = ClaimRepository(conn)

        result = repo.apply_transition(
            claim_id, ClaimEvent.ATTACH_CHECKLIST, actor_id="assessor-1"
        )

        assert result.from_state == ClaimStatus.INTAKE
        assert result.to_state == ClaimStatus.DOCS_PENDING
        assert result.claim_id == claim_id

        # Re-query the DB directly -- don't just trust the return value (AC2).
        claim_row = conn.execute(
            "SELECT status FROM claims WHERE id = ?", (claim_id,)
        ).fetchone()
        assert claim_row["status"] == ClaimStatus.DOCS_PENDING.value

        transition_rows = conn.execute(
            "SELECT * FROM claim_state_transitions WHERE claim_id = ?", (claim_id,)
        ).fetchall()
        assert len(transition_rows) == 1
        transition_row = transition_rows[0]
        assert transition_row["from_state"] == ClaimStatus.INTAKE.value
        assert transition_row["to_state"] == ClaimStatus.DOCS_PENDING.value
        assert transition_row["event"] == ClaimEvent.ATTACH_CHECKLIST.value
        assert transition_row["actor_id"] == "assessor-1"
        assert transition_row["created_at"] is not None

    def test_valid_event_bumps_updated_at(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id = _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.INTAKE.value,
        )
        conn.execute(
            "UPDATE claims SET updated_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
            (claim_id,),
        )
        conn.commit()
        repo = ClaimRepository(conn)

        repo.apply_transition(claim_id, ClaimEvent.ATTACH_CHECKLIST)

        row = conn.execute("SELECT updated_at FROM claims WHERE id = ?", (claim_id,)).fetchone()
        assert row["updated_at"] != "2000-01-01T00:00:00+00:00"

    def test_invalid_event_raises_and_leaves_row_unmutated(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id = _insert_claim_row(conn, policy_id=policy_id, status=ClaimStatus.INTAKE.value)
        repo = ClaimRepository(conn)

        with pytest.raises(InvalidClaimStateException):
            # SETTLE is not a valid event from INTAKE.
            repo.apply_transition(claim_id, ClaimEvent.SETTLE)

        # Critical assertion: re-query the claim row -- status must be unchanged (AC3).
        claim_row = conn.execute(
            "SELECT status, updated_at FROM claims WHERE id = ?", (claim_id,)
        ).fetchone()
        assert claim_row["status"] == ClaimStatus.INTAKE.value

        transition_rows = conn.execute(
            "SELECT * FROM claim_state_transitions WHERE claim_id = ?", (claim_id,)
        ).fetchall()
        assert len(transition_rows) == 0

    def test_apply_transition_raises_when_claim_not_found(self, conn: sqlite3.Connection) -> None:
        repo = ClaimRepository(conn)

        with pytest.raises(LookupError):
            repo.apply_transition(999, ClaimEvent.ATTACH_CHECKLIST)


class TestListByStatusAndProduct:
    """F034: filters are optional and composable."""

    def test_no_filters_returns_all_claims(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.INTAKE.value,
            claim_type=ClaimType.MOTOR.value,
        )
        _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.DOCS_PENDING.value,
            claim_type=ClaimType.HEALTH.value,
        )
        repo = ClaimRepository(conn)

        results = repo.list_by_status_and_product()

        assert len(results) == 2

    def test_filter_by_status_only(self, conn: sqlite3.Connection, policy_id: int) -> None:
        _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.INTAKE.value,
            claim_type=ClaimType.MOTOR.value,
        )
        _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.DOCS_PENDING.value,
            claim_type=ClaimType.MOTOR.value,
        )
        _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.INTAKE.value,
            claim_type=ClaimType.HEALTH.value,
        )
        repo = ClaimRepository(conn)

        results = repo.list_by_status_and_product(status=ClaimStatus.INTAKE)

        assert len(results) == 2
        assert all(c.status == ClaimStatus.INTAKE for c in results)

    def test_filter_by_claim_type_only(self, conn: sqlite3.Connection, policy_id: int) -> None:
        _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.INTAKE.value,
            claim_type=ClaimType.MOTOR.value,
        )
        _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.DOCS_PENDING.value,
            claim_type=ClaimType.HEALTH.value,
        )
        repo = ClaimRepository(conn)

        results = repo.list_by_status_and_product(claim_type=ClaimType.HEALTH)

        assert len(results) == 1
        assert results[0].claim_type == ClaimType.HEALTH

    def test_filter_by_status_and_claim_type_combined(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.INTAKE.value,
            claim_type=ClaimType.MOTOR.value,
        )
        _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.INTAKE.value,
            claim_type=ClaimType.HEALTH.value,
        )
        _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.DOCS_PENDING.value,
            claim_type=ClaimType.MOTOR.value,
        )
        repo = ClaimRepository(conn)

        results = repo.list_by_status_and_product(
            status=ClaimStatus.INTAKE, claim_type=ClaimType.MOTOR
        )

        assert len(results) == 1
        assert results[0].status == ClaimStatus.INTAKE
        assert results[0].claim_type == ClaimType.MOTOR

    def test_filter_combination_matching_nothing_returns_empty_list(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        _insert_claim_row(
            conn,
            policy_id=policy_id,
            status=ClaimStatus.INTAKE.value,
            claim_type=ClaimType.MOTOR.value,
        )
        repo = ClaimRepository(conn)

        results = repo.list_by_status_and_product(
            status=ClaimStatus.SETTLED, claim_type=ClaimType.LIFE
        )

        assert results == []


class TestExistsDuplicate:
    """F035: True for a matching (policy_id, incident_date) pair, False otherwise.

    Interpretation note: the story text says "non-void", but gives no exclusion
    list of statuses. We treat ANY existing claim row for the (policy_id,
    incident_date) pair as a duplicate, regardless of its current status --
    the story does not define which statuses count as "void", so the safest
    reading is "a claim already exists for this policy on this date at all".
    """

    def test_returns_true_for_matching_policy_and_incident_date(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        _insert_claim_row(conn, policy_id=policy_id, incident_date="2026-05-01")
        repo = ClaimRepository(conn)

        assert repo.exists_duplicate(policy_id, "2026-05-01") is True

    def test_returns_false_for_different_incident_date(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        _insert_claim_row(conn, policy_id=policy_id, incident_date="2026-05-01")
        repo = ClaimRepository(conn)

        assert repo.exists_duplicate(policy_id, "2026-05-02") is False

    def test_returns_false_for_different_policy(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        other_policy_id = _insert_policy(conn, policy_number="POL-002")
        _insert_claim_row(conn, policy_id=policy_id, incident_date="2026-05-01")
        repo = ClaimRepository(conn)

        assert repo.exists_duplicate(other_policy_id, "2026-05-01") is False

    def test_returns_false_when_no_claims_exist(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        repo = ClaimRepository(conn)

        assert repo.exists_duplicate(policy_id, "2026-05-01") is False


class TestCountRecentClaims:
    """Group F (E5-S3) addition: supplies FraudScoringInput.recent_claim_count_90d."""

    def test_counts_claims_within_window_inclusive_of_before_date(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        _insert_claim_row(conn, policy_id=policy_id, incident_date="2026-01-10")
        _insert_claim_row(conn, policy_id=policy_id, incident_date="2026-03-10")
        repo = ClaimRepository(conn)

        count = repo.count_recent_claims(policy_id, before_date="2026-03-10", window_days=90)

        assert count == 2

    def test_excludes_claims_outside_the_window(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        _insert_claim_row(conn, policy_id=policy_id, incident_date="2025-11-01")
        repo = ClaimRepository(conn)

        count = repo.count_recent_claims(policy_id, before_date="2026-03-10", window_days=90)

        assert count == 0

    def test_excludes_a_named_claim_id(self, conn: sqlite3.Connection, policy_id: int) -> None:
        claim_id = _insert_claim_row(conn, policy_id=policy_id, incident_date="2026-03-10")
        repo = ClaimRepository(conn)

        count = repo.count_recent_claims(
            policy_id, before_date="2026-03-10", window_days=90, exclude_claim_id=claim_id
        )

        assert count == 0

    def test_ignores_claims_on_a_different_policy(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        other_policy_id = _insert_policy(conn, policy_number="POL-OTHER")
        _insert_claim_row(conn, policy_id=other_policy_id, incident_date="2026-03-10")
        repo = ClaimRepository(conn)

        count = repo.count_recent_claims(policy_id, before_date="2026-03-10", window_days=90)

        assert count == 0
