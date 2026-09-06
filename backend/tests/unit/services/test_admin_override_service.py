"""Unit tests for `src.services.admin_override_service` (E8-S2, F089-F092)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.repositories.claim_repository import ClaimRepository
from src.services.admin_override_service import override
from src.types.enums import AdminOverrideCommand, ClaimEvent, ClaimStatus, ClaimType
from src.types.exceptions import InvalidClaimStateException, ValidationError
from src.types.models import AdminOverride

REAL_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def _seed_connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "claimflow.db"
    conn = get_connection(str(db_path))
    run_migrations(conn, str(REAL_MIGRATIONS_DIR))
    return conn


def _insert_policy(
    conn: sqlite3.Connection,
    *,
    policy_number: str = "POL-900",
    product_type: str = ClaimType.MOTOR.value,
    status: str = "ACTIVE",
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


def _insert_claim(
    conn: sqlite3.Connection,
    policy_id: int,
    *,
    status: ClaimStatus,
    incident_date: str = "2026-03-10",
    claim_amount: str = "40000.00",
) -> int:
    """Insert a claim directly at `status`, bypassing the transition gate.

    This is a test-setup shortcut only (seeding a claim already sitting in a
    given status) -- it does not exercise `apply_transition`, so it is not a
    substitute for the gate itself. The service under test always drives
    status changes exclusively through `ClaimRepository.apply_transition`.
    """
    cursor = conn.execute(
        "INSERT INTO claims "
        "(policy_id, claim_type, incident_date, claim_amount, status, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (policy_id, ClaimType.MOTOR.value, incident_date, claim_amount, status.value),
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


def _override_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM admin_overrides ORDER BY id ASC"
    ).fetchall()


class TestOverrideInsertsAuditRow:
    """F089: a successful override inserts an AdminOverride row and moves status."""

    def test_force_approve_inserts_row_and_moves_status(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id = _insert_claim(conn, policy_id, status=ClaimStatus.MANUAL_REVIEW)

        result = override(
            conn,
            claim_id=claim_id,
            admin_actor_id="admin-7",
            command=AdminOverrideCommand.FORCE_APPROVE,
            reason_code="goodwill",
        )

        assert isinstance(result, AdminOverride)
        assert result.claim_id == claim_id
        assert result.admin_actor_id == "admin-7"
        assert result.command == AdminOverrideCommand.FORCE_APPROVE
        assert result.reason_code == "goodwill"
        assert result.created_at

        rows = _override_rows(conn)
        assert len(rows) == 1
        assert rows[0]["claim_id"] == claim_id
        assert rows[0]["admin_actor_id"] == "admin-7"
        assert rows[0]["command"] == AdminOverrideCommand.FORCE_APPROVE.value
        assert rows[0]["reason_code"] == "goodwill"
        assert rows[0]["created_at"]

        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.AUTO_APPROVED


class TestOverrideRequiresReasonCode:
    """F090: missing/blank reason_code raises ValidationError, no row inserted."""

    @pytest.mark.parametrize("bad_reason_code", ["", "   "])
    def test_blank_reason_code_raises_and_inserts_nothing(
        self, conn: sqlite3.Connection, policy_id: int, bad_reason_code: str
    ) -> None:
        claim_id = _insert_claim(conn, policy_id, status=ClaimStatus.MANUAL_REVIEW)

        with pytest.raises(ValidationError):
            override(
                conn,
                claim_id=claim_id,
                admin_actor_id="admin-7",
                command=AdminOverrideCommand.FORCE_APPROVE,
                reason_code=bad_reason_code,
            )

        assert _override_rows(conn) == []
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.MANUAL_REVIEW


class TestOverrideGoesThroughGate:
    """F091: valid target uses the E1-S2 gate; invalid target raises and logs nothing."""

    def test_valid_target_writes_a_state_transition_row(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id = _insert_claim(conn, policy_id, status=ClaimStatus.MANUAL_REVIEW)

        override(
            conn,
            claim_id=claim_id,
            admin_actor_id="admin-1",
            command=AdminOverrideCommand.FORCE_APPROVE,
            reason_code="documented-exception",
        )

        transition_rows = conn.execute(
            "SELECT * FROM claim_state_transitions WHERE claim_id = ?", (claim_id,)
        ).fetchall()
        assert len(transition_rows) == 1
        assert transition_rows[0]["from_state"] == ClaimStatus.MANUAL_REVIEW.value
        assert transition_rows[0]["to_state"] == ClaimStatus.AUTO_APPROVED.value
        assert transition_rows[0]["event"] == ClaimEvent.ADMIN_FORCE_APPROVE.value
        assert transition_rows[0]["actor_id"] == "admin-1"

    def test_invalid_target_raises_and_inserts_no_override_row(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        # SETTLED has no ADMIN_FORCE_APPROVE entry in the transition table.
        claim_id = _insert_claim(conn, policy_id, status=ClaimStatus.SETTLED)

        with pytest.raises(InvalidClaimStateException):
            override(
                conn,
                claim_id=claim_id,
                admin_actor_id="admin-1",
                command=AdminOverrideCommand.FORCE_APPROVE,
                reason_code="attempted-fix",
            )

        assert _override_rows(conn) == []
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.SETTLED


class TestOverrideConcurrency:
    """F092: two overrides in a row -- the second against stale state fails."""

    def test_second_override_against_stale_state_raises(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id = _insert_claim(conn, policy_id, status=ClaimStatus.MANUAL_REVIEW)

        first_result = override(
            conn,
            claim_id=claim_id,
            admin_actor_id="admin-a",
            command=AdminOverrideCommand.FORCE_APPROVE,
            reason_code="admin-a-decision",
        )
        assert first_result.command == AdminOverrideCommand.FORCE_APPROVE

        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.AUTO_APPROVED

        # Second admin's command was valid for the ORIGINAL (MANUAL_REVIEW)
        # status but AUTO_APPROVED's only valid event is SETTLE -- so this
        # must fail rather than silently double-applying.
        with pytest.raises(InvalidClaimStateException):
            override(
                conn,
                claim_id=claim_id,
                admin_actor_id="admin-b",
                command=AdminOverrideCommand.FORCE_APPROVE,
                reason_code="admin-b-decision",
            )

        rows = _override_rows(conn)
        assert len(rows) == 1
        assert rows[0]["admin_actor_id"] == "admin-a"

        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.AUTO_APPROVED


class TestForceRetryRequiresTargetEvent:
    """FORCE_RETRY is ambiguous among 3 targets; caller must disambiguate."""

    def test_force_retry_without_target_event_raises_validation_error(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id = _insert_claim(conn, policy_id, status=ClaimStatus.PROCESSING_FAILED)

        with pytest.raises(ValidationError):
            override(
                conn,
                claim_id=claim_id,
                admin_actor_id="admin-1",
                command=AdminOverrideCommand.FORCE_RETRY,
                reason_code="pipeline-fixed",
            )

        assert _override_rows(conn) == []

    def test_force_retry_with_explicit_target_event_succeeds(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id = _insert_claim(conn, policy_id, status=ClaimStatus.PROCESSING_FAILED)

        result = override(
            conn,
            claim_id=claim_id,
            admin_actor_id="admin-1",
            command=AdminOverrideCommand.FORCE_RETRY,
            reason_code="pipeline-fixed",
            target_event=ClaimEvent.RETRY_TO_FRAUD_SCREENING,
        )

        assert result.command == AdminOverrideCommand.FORCE_RETRY
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.FRAUD_SCREENING


class TestOtherForcedCommands:
    """Cover FORCE_REJECT and FORCE_MANUAL_REVIEW mapping branches."""

    def test_force_reject_from_docs_pending(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id = _insert_claim(conn, policy_id, status=ClaimStatus.DOCS_PENDING)

        result = override(
            conn,
            claim_id=claim_id,
            admin_actor_id="admin-2",
            command=AdminOverrideCommand.FORCE_REJECT,
            reason_code="policy-lapsed-confirmed",
        )

        assert result.command == AdminOverrideCommand.FORCE_REJECT
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.REJECTED

    def test_force_manual_review_from_manual_review(
        self, conn: sqlite3.Connection, policy_id: int
    ) -> None:
        claim_id = _insert_claim(conn, policy_id, status=ClaimStatus.MANUAL_REVIEW)

        result = override(
            conn,
            claim_id=claim_id,
            admin_actor_id="admin-3",
            command=AdminOverrideCommand.FORCE_MANUAL_REVIEW,
            reason_code="needs-second-opinion",
        )

        assert result.command == AdminOverrideCommand.FORCE_MANUAL_REVIEW
        claim = ClaimRepository(conn).get_by_id(claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.MANUAL_REVIEW
