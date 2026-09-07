"""Unit tests for `src.services.fraud_screening_service` (E5-S3, F059-F062)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from src.config.fraud_rules_config import FraudRulesConfig
from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.repositories.claim_repository import ClaimRepository
from src.repositories.fraud_screening_repository import FraudScreeningRepository
from src.services.document_checklist_service import check_documents_complete, verify_document
from src.services.fnol_intake_service import submit_fnol
from src.services.fraud_screening_service import run_fraud_screening
from src.types.enums import ClaimStatus, ClaimType, DocumentType

REAL_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"

# Deterministically forces flagged=True (score 0 >= threshold 0) regardless
# of the claim's own data, since it carries zero fraud rules to evaluate.
_ALWAYS_FLAG_CONFIG = FraudRulesConfig(rules=(), threshold=0)
# Deterministically forces flagged=False (score 0 < threshold 1).
_NEVER_FLAG_CONFIG = FraudRulesConfig(rules=(), threshold=1)


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


@pytest.fixture
def fraud_screening_claim_id(conn: sqlite3.Connection) -> int:
    """A motor claim already advanced to FRAUD_SCREENING (docs fully verified)."""
    _insert_policy(conn, policy_number="POL-MOTOR")
    claim = submit_fnol(
        conn,
        policy_number="POL-MOTOR",
        claim_type=ClaimType.MOTOR,
        incident_date="2026-03-10",
        claim_amount=Decimal("40000.00"),
    )
    verify_document(conn, claim.id, DocumentType.POLICE_FIR)
    verify_document(conn, claim.id, DocumentType.INVOICE)
    assert check_documents_complete(conn, claim.id) is True
    return claim.id


class TestThresholdAtScoringTime:
    def test_stores_the_threshold_passed_at_call_time(
        self, conn: sqlite3.Connection, fraud_screening_claim_id: int
    ) -> None:
        """F059."""
        custom_config = FraudRulesConfig(rules=(), threshold=42)

        screening = run_fraud_screening(conn, fraud_screening_claim_id, custom_config)

        assert screening.threshold == 42

    def test_a_later_call_with_a_different_config_does_not_change_the_first_row(
        self, conn: sqlite3.Connection, fraud_screening_claim_id: int
    ) -> None:
        """F059: two independent screenings each keep their own call-time threshold."""
        first = run_fraud_screening(
            conn, fraud_screening_claim_id, FraudRulesConfig(rules=(), threshold=60)
        )
        assert first.threshold == 60

        # Simulate a retry re-entering FRAUD_SCREENING (E6-S3's retry path,
        # Group H, doesn't exist yet -- direct status reset stands in for it).
        conn.execute(
            "UPDATE claims SET status = 'FRAUD_SCREENING' WHERE id = ?",
            (fraud_screening_claim_id,),
        )
        conn.commit()

        run_fraud_screening(
            conn, fraud_screening_claim_id, FraudRulesConfig(rules=(), threshold=90)
        )

        first_row_still = conn.execute(
            "SELECT threshold FROM fraud_screenings WHERE id = ?", (first.id,)
        ).fetchone()
        assert first_row_still["threshold"] == 60


class TestFlaggedGating:
    def test_flagged_result_moves_claim_toward_manual_review(
        self, conn: sqlite3.Connection, fraud_screening_claim_id: int
    ) -> None:
        """F060."""
        screening = run_fraud_screening(conn, fraud_screening_claim_id, _ALWAYS_FLAG_CONFIG)

        assert screening.flagged is True
        claim = ClaimRepository(conn).get_by_id(fraud_screening_claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.MANUAL_REVIEW

    def test_unflagged_result_moves_claim_toward_assessment(
        self, conn: sqlite3.Connection, fraud_screening_claim_id: int
    ) -> None:
        """F061."""
        screening = run_fraud_screening(conn, fraud_screening_claim_id, _NEVER_FLAG_CONFIG)

        assert screening.flagged is False
        claim = ClaimRepository(conn).get_by_id(fraud_screening_claim_id)
        assert claim is not None
        assert claim.status == ClaimStatus.ASSESSMENT


class TestAppendOnlyScreenings:
    def test_two_screenings_on_the_same_claim_are_both_independently_queryable(
        self, conn: sqlite3.Connection, fraud_screening_claim_id: int
    ) -> None:
        """F062: e.g. after a retry, neither screening row overwrites the other."""
        first = run_fraud_screening(conn, fraud_screening_claim_id, _NEVER_FLAG_CONFIG)

        # Simulate re-entering FRAUD_SCREENING for a second scoring run.
        conn.execute(
            "UPDATE claims SET status = 'FRAUD_SCREENING' WHERE id = ?",
            (fraud_screening_claim_id,),
        )
        conn.commit()

        second = run_fraud_screening(conn, fraud_screening_claim_id, _ALWAYS_FLAG_CONFIG)

        assert first.id != second.id
        rows = conn.execute(
            "SELECT id, flagged FROM fraud_screenings WHERE claim_id = ? ORDER BY id",
            (fraud_screening_claim_id,),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["id"] == first.id
        assert rows[0]["flagged"] == 0
        assert rows[1]["id"] == second.id
        assert rows[1]["flagged"] == 1

        # Confirm via the repository directly too, not just raw SQL.
        latest = FraudScreeningRepository(conn).get_latest(fraud_screening_claim_id)
        assert latest is not None
        assert latest.id == second.id


class TestUnknownClaimId:
    def test_raises_lookup_error(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(LookupError):
            run_fraud_screening(conn, 999999, _NEVER_FLAG_CONFIG)
