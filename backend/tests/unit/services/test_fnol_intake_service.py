"""Unit tests for `src.services.fnol_intake_service`.

Covers E4-S1 (F040-F043), E4-S2 (F044-F047), and E4-S3 (F048-F050).
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.repositories.claim_document_repository import ClaimDocumentRepository
from src.repositories.claim_repository import ClaimRepository
from src.services.fnol_intake_service import submit_fnol
from src.types.enums import ClaimEvent, ClaimStatus, ClaimType, DocumentType, VerificationStatus
from src.types.exceptions import (
    DuplicateClaimException,
    PolicyNotActiveException,
    UnknownClaimTypeError,
)

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
    status: str = "ACTIVE",
    sum_insured: str = "500000.00",
    effective_date: str = "2025-01-01",
    expiry_date: str = "2026-12-31",
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


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = _seed_connection(tmp_path)
    yield connection
    connection.close()


@pytest.fixture
def policy_number(conn: sqlite3.Connection) -> str:
    _insert_policy(conn, policy_number="POL-001")
    return "POL-001"


class TestSubmitFnolMotor:
    """F040: MOTOR FNOL -> claim_type=MOTOR, checklist = POLICE_FIR + INVOICE."""

    def test_motor_fnol_creates_claim_and_checklist(
        self, conn: sqlite3.Connection, policy_number: str
    ) -> None:
        claim = submit_fnol(
            conn,
            policy_number=policy_number,
            claim_type=ClaimType.MOTOR,
            incident_date="2026-03-10",
            claim_amount=Decimal("40000.00"),
        )

        assert claim.claim_type == ClaimType.MOTOR

        documents = ClaimDocumentRepository(conn).list_by_claim(claim.id)
        assert len(documents) == 2
        document_types = {d.document_type for d in documents}
        assert document_types == {DocumentType.POLICE_FIR, DocumentType.INVOICE}
        assert all(d.verification_status == VerificationStatus.MISSING for d in documents)


class TestSubmitFnolHealth:
    """F041: HEALTH FNOL -> checklist = HOSPITAL_BILL + DISCHARGE_SUMMARY."""

    def test_health_fnol_creates_exact_checklist(
        self, conn: sqlite3.Connection, policy_number: str
    ) -> None:
        claim = submit_fnol(
            conn,
            policy_number=policy_number,
            claim_type=ClaimType.HEALTH,
            incident_date="2026-04-01",
            claim_amount=Decimal("15000.00"),
        )

        assert claim.claim_type == ClaimType.HEALTH

        documents = ClaimDocumentRepository(conn).list_by_claim(claim.id)
        assert len(documents) == 2
        document_types = {d.document_type for d in documents}
        assert document_types == {DocumentType.HOSPITAL_BILL, DocumentType.DISCHARGE_SUMMARY}
        assert all(d.verification_status == VerificationStatus.MISSING for d in documents)


class TestSubmitFnolLife:
    """F042: LIFE FNOL -> checklist = DEATH_CERTIFICATE (exactly one row)."""

    def test_life_fnol_creates_single_checklist_row(
        self, conn: sqlite3.Connection, policy_number: str
    ) -> None:
        claim = submit_fnol(
            conn,
            policy_number=policy_number,
            claim_type=ClaimType.LIFE,
            incident_date="2026-02-01",
            claim_amount=Decimal("500000.00"),
        )

        assert claim.claim_type == ClaimType.LIFE

        documents = ClaimDocumentRepository(conn).list_by_claim(claim.id)
        assert len(documents) == 1
        assert documents[0].document_type == DocumentType.DEATH_CERTIFICATE
        assert documents[0].verification_status == VerificationStatus.MISSING


class TestSubmitFnolLifecycle:
    """F043: claim starts at INTAKE, ends at DOCS_PENDING once checklist attached."""

    def test_claim_starts_intake_and_ends_docs_pending(
        self, conn: sqlite3.Connection, policy_number: str
    ) -> None:
        claim_repository = ClaimRepository(conn)

        claim = submit_fnol(
            conn,
            policy_number=policy_number,
            claim_type=ClaimType.MOTOR,
            incident_date="2026-05-01",
            claim_amount=Decimal("10000.00"),
        )

        # The claim returned by submit_fnol reflects the final DOCS_PENDING state.
        assert claim.status == ClaimStatus.DOCS_PENDING

        # Re-query directly from the repository -- don't just trust the return value.
        persisted = claim_repository.get_by_id(claim.id)
        assert persisted is not None
        assert persisted.status == ClaimStatus.DOCS_PENDING

        transition_rows = conn.execute(
            "SELECT * FROM claim_state_transitions WHERE claim_id = ?", (claim.id,)
        ).fetchall()
        assert len(transition_rows) == 1
        assert transition_rows[0]["from_state"] == ClaimStatus.INTAKE.value
        assert transition_rows[0]["to_state"] == ClaimStatus.DOCS_PENDING.value
        assert transition_rows[0]["event"] == ClaimEvent.ATTACH_CHECKLIST.value

    def test_actor_id_is_recorded_on_the_transition(
        self, conn: sqlite3.Connection, policy_number: str
    ) -> None:
        claim = submit_fnol(
            conn,
            policy_number=policy_number,
            claim_type=ClaimType.MOTOR,
            incident_date="2026-06-01",
            claim_amount=Decimal("20000.00"),
            actor_id="customer-42",
        )

        transition_row = conn.execute(
            "SELECT actor_id FROM claim_state_transitions WHERE claim_id = ?", (claim.id,)
        ).fetchone()
        assert transition_row["actor_id"] == "customer-42"


class TestUnknownClaimType:
    """Defensive: a claim_type outside {MOTOR, HEALTH, LIFE} fails loudly."""

    def test_raises_unknown_claim_type_error(
        self, conn: sqlite3.Connection, policy_number: str
    ) -> None:
        with pytest.raises(UnknownClaimTypeError):
            submit_fnol(
                conn,
                policy_number=policy_number,
                claim_type="BOGUS",  # type: ignore[arg-type]
                incident_date="2026-07-01",
                claim_amount=Decimal("1000.00"),
            )

        # No claim row should have been created for the rejected claim_type.
        rows = conn.execute("SELECT COUNT(*) AS n FROM claims").fetchone()
        assert rows["n"] == 0


class TestPolicyActiveValidation:
    """E4-S2 / F044-F047: policy must be ACTIVE on incident_date."""

    def test_lapsed_policy_raises_and_creates_no_claim(self, conn: sqlite3.Connection) -> None:
        """F044."""
        _insert_policy(conn, policy_number="POL-LAPSED", status="LAPSED")

        with pytest.raises(PolicyNotActiveException) as excinfo:
            submit_fnol(
                conn,
                policy_number="POL-LAPSED",
                claim_type=ClaimType.MOTOR,
                incident_date="2026-03-10",
                claim_amount=Decimal("10000.00"),
            )

        assert excinfo.value.policy_number == "POL-LAPSED"
        rows = conn.execute("SELECT COUNT(*) AS n FROM claims").fetchone()
        assert rows["n"] == 0

    def test_incident_after_expiry_raises(self, conn: sqlite3.Connection) -> None:
        """F045."""
        _insert_policy(
            conn,
            policy_number="POL-EXPIRED-WINDOW",
            status="ACTIVE",
            effective_date="2025-01-01",
            expiry_date="2025-12-31",
        )

        with pytest.raises(PolicyNotActiveException):
            submit_fnol(
                conn,
                policy_number="POL-EXPIRED-WINDOW",
                claim_type=ClaimType.MOTOR,
                incident_date="2026-01-15",
                claim_amount=Decimal("10000.00"),
            )

    def test_incident_within_window_proceeds(self, conn: sqlite3.Connection) -> None:
        """F046."""
        _insert_policy(
            conn,
            policy_number="POL-IN-WINDOW",
            status="ACTIVE",
            effective_date="2025-01-01",
            expiry_date="2025-12-31",
        )

        claim = submit_fnol(
            conn,
            policy_number="POL-IN-WINDOW",
            claim_type=ClaimType.MOTOR,
            incident_date="2025-06-15",
            claim_amount=Decimal("10000.00"),
        )

        assert claim.status == ClaimStatus.DOCS_PENDING

    def test_unresolvable_policy_number_raises_policy_not_active(
        self, conn: sqlite3.Connection
    ) -> None:
        """No such policy at all is treated the same as an inactive one."""
        with pytest.raises(PolicyNotActiveException):
            submit_fnol(
                conn,
                policy_number="DOES-NOT-EXIST",
                claim_type=ClaimType.MOTOR,
                incident_date="2026-03-10",
                claim_amount=Decimal("10000.00"),
            )


class TestDuplicateFnolDetection:
    """E4-S3 / F048-F049: reject a second FNOL for the same (policy, date)."""

    def test_duplicate_policy_and_date_raises_and_creates_no_second_claim(
        self, conn: sqlite3.Connection, policy_number: str
    ) -> None:
        """F048."""
        submit_fnol(
            conn,
            policy_number=policy_number,
            claim_type=ClaimType.MOTOR,
            incident_date="2026-03-10",
            claim_amount=Decimal("10000.00"),
        )

        with pytest.raises(DuplicateClaimException) as excinfo:
            submit_fnol(
                conn,
                policy_number=policy_number,
                claim_type=ClaimType.MOTOR,
                incident_date="2026-03-10",
                claim_amount=Decimal("20000.00"),
            )

        assert excinfo.value.policy_number == policy_number
        rows = conn.execute("SELECT COUNT(*) AS n FROM claims").fetchone()
        assert rows["n"] == 1

    def test_distinct_incident_date_on_same_policy_succeeds(
        self, conn: sqlite3.Connection, policy_number: str
    ) -> None:
        """F049."""
        submit_fnol(
            conn,
            policy_number=policy_number,
            claim_type=ClaimType.MOTOR,
            incident_date="2026-03-10",
            claim_amount=Decimal("10000.00"),
        )

        second_claim = submit_fnol(
            conn,
            policy_number=policy_number,
            claim_type=ClaimType.MOTOR,
            incident_date="2026-04-01",
            claim_amount=Decimal("20000.00"),
        )

        assert second_claim.status == ClaimStatus.DOCS_PENDING
        rows = conn.execute("SELECT COUNT(*) AS n FROM claims").fetchone()
        assert rows["n"] == 2
