"""Seed a fresh SQLite DB with sample data for frontend Playwright e2e runs.

Not part of the production app (Types/Config/Repository/Service/API layers) --
this is test/dev tooling only, mirroring the raw-INSERT + `submit_fnol()`
patterns already used by `backend/tests/integration/api/test_admin_router.py`
and `test_documents_router.py`. Run before starting `uvicorn src.main:app`
for a Playwright e2e session so the document-queue and admin-dashboard UI
stories (E11-S1, E11-S4) have real DOCS_PENDING / MANUAL_REVIEW / SETTLED
claims to render against -- the E9-S1 claims-intake router (`POST
/api/claims`) that would otherwise create this data isn't mounted on this
branch yet (it lands with Group I), so there is no other way to seed a
running instance of this app.

Usage:
    CLAIMFLOW_DB_PATH=./.e2e/claimflow.db python scripts/seed_e2e_db.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.db.connection import get_connection  # noqa: E402
from src.db.migration_runner import run_migrations  # noqa: E402
from src.services.fnol_intake_service import submit_fnol  # noqa: E402
from src.types.enums import ClaimType  # noqa: E402

MIGRATIONS_DIR = BACKEND_ROOT / "migrations"


def _insert_policy(conn: sqlite3.Connection, policy_number: str, product_type: str) -> int:
    cursor = conn.execute(
        "INSERT INTO policies (policy_number, product_type, status, sum_insured, "
        "effective_date, expiry_date, created_at) VALUES (?, ?, 'ACTIVE', '500000.00', "
        "'2025-01-01', '2027-12-31', datetime('now'))",
        (policy_number, product_type),
    )
    conn.commit()
    policy_id = cursor.lastrowid
    assert policy_id is not None
    return policy_id


def _insert_claim(
    conn: sqlite3.Connection,
    policy_id: int,
    *,
    claim_type: str,
    status: str,
    claim_amount: str,
    incident_date: str = "2026-03-11",
) -> int:
    cursor = conn.execute(
        "INSERT INTO claims (policy_id, claim_type, incident_date, claim_amount, status, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (policy_id, claim_type, incident_date, claim_amount, status),
    )
    conn.commit()
    claim_id = cursor.lastrowid
    assert claim_id is not None
    return claim_id


def _insert_decision(
    conn: sqlite3.Connection,
    claim_id: int,
    *,
    outcome: str = "AUTO_APPROVE",
    reason_code: str = "AUTO_APPROVED_LOW_RISK",
) -> int:
    cursor = conn.execute(
        "INSERT INTO decisions (claim_id, outcome, reason_code, decided_by, created_at) "
        "VALUES (?, ?, ?, 'system', datetime('now'))",
        (claim_id, outcome, reason_code),
    )
    conn.commit()
    decision_id = cursor.lastrowid
    assert decision_id is not None
    return decision_id


def _insert_settlement(
    conn: sqlite3.Connection,
    claim_id: int,
    decision_id: int,
    *,
    payout_amount: str,
    payment_reference: str,
) -> None:
    conn.execute(
        "INSERT INTO settlements (claim_id, decision_id, payout_amount, payment_reference, "
        "created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (claim_id, decision_id, payout_amount, payment_reference),
    )
    conn.commit()


def seed(db_path: str) -> None:
    db_file = Path(db_path)
    if db_file.exists():
        db_file.unlink()
    db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(db_path, check_same_thread=False)
    run_migrations(conn, str(MIGRATIONS_DIR))

    # E11-S1: two DOCS_PENDING claims with outstanding checklist items, for
    # the document verification queue to list.
    motor_docs_policy = _insert_policy(conn, "POL-MOTOR-E2E-1", "MOTOR")
    submit_fnol(
        conn,
        policy_number="POL-MOTOR-E2E-1",
        claim_type=ClaimType.MOTOR,
        incident_date="2026-03-10",
        claim_amount=Decimal("42500.00"),
    )
    health_docs_policy = _insert_policy(conn, "POL-HEALTH-E2E-1", "HEALTH")
    submit_fnol(
        conn,
        policy_number="POL-HEALTH-E2E-1",
        claim_type=ClaimType.HEALTH,
        incident_date="2026-03-12",
        claim_amount=Decimal("18000.00"),
    )
    assert motor_docs_policy != health_docs_policy

    # E11-S4: admin dashboard -- a MANUAL_REVIEW claim to drive the override
    # action, plus a SETTLED claim with a Decision + Settlement for the
    # read-only payout audit trail.
    review_policy = _insert_policy(conn, "POL-MOTOR-E2E-2", "MOTOR")
    review_claim_id = _insert_claim(
        conn, review_policy, claim_type="MOTOR", status="MANUAL_REVIEW", claim_amount="90000.00"
    )

    settled_policy = _insert_policy(conn, "POL-HEALTH-E2E-2", "HEALTH")
    settled_claim_id = _insert_claim(
        conn, settled_policy, claim_type="HEALTH", status="SETTLED", claim_amount="40000.00"
    )
    decision_id = _insert_decision(conn, settled_claim_id)
    _insert_settlement(
        conn,
        settled_claim_id,
        decision_id,
        payout_amount="35000.00",
        payment_reference=f"STUB-PAY-{settled_claim_id:07d}-01",
    )

    conn.close()
    print(
        f"Seeded {db_path}: 2 DOCS_PENDING claims for the document queue, "
        f"MANUAL_REVIEW claim {review_claim_id}, and SETTLED claim "
        f"{settled_claim_id} with a payout for the admin dashboard."
    )


if __name__ == "__main__":
    seed_db_path = os.environ.get("CLAIMFLOW_DB_PATH")
    if not seed_db_path:
        raise SystemExit("CLAIMFLOW_DB_PATH must be set before running this script.")
    seed(seed_db_path)
