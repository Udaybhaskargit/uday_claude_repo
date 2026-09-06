"""Unit tests for `src.repositories.policy_repository` (E3-S2, F028-F030)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from src.db.connection import get_connection
from src.db.migration_runner import run_migrations
from src.repositories.policy_repository import PolicyRepository
from src.types.enums import ClaimType, PolicyStatus

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
) -> None:
    conn.execute(
        "INSERT INTO policies "
        "(policy_number, product_type, status, sum_insured, effective_date, "
        "expiry_date, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (policy_number, product_type, status, sum_insured, effective_date, expiry_date),
    )
    conn.commit()


def test_get_by_number_returns_policy_with_matching_sum_insured_and_dates(
    tmp_path: Path,
) -> None:
    """F028: a seeded active policy is returned with matching sum_insured/dates."""
    conn = _seed_connection(tmp_path)
    try:
        _insert_policy(
            conn,
            policy_number="POL-001",
            sum_insured="500000.00",
            effective_date="2025-01-01",
            expiry_date="2025-12-31",
        )
        repo = PolicyRepository(conn)

        policy = repo.get_by_number("POL-001")

        assert policy is not None
        assert policy.policy_number == "POL-001"
        assert isinstance(policy.sum_insured, Decimal)
        assert policy.sum_insured == Decimal("500000.00")
        assert policy.effective_date == "2025-01-01"
        assert policy.expiry_date == "2025-12-31"
        assert policy.product_type == ClaimType.MOTOR
        assert policy.status == PolicyStatus.ACTIVE
    finally:
        conn.close()


def test_get_by_number_returns_none_when_not_found(tmp_path: Path) -> None:
    """F029: an unknown policy number returns None, never raises."""
    conn = _seed_connection(tmp_path)
    try:
        repo = PolicyRepository(conn)

        result = repo.get_by_number("DOES-NOT-EXIST")

        assert result is None
    finally:
        conn.close()


def test_is_active_on_returns_false_outside_policy_window(tmp_path: Path) -> None:
    """F030: is_active_on() on the returned Policy is False outside its window."""
    conn = _seed_connection(tmp_path)
    try:
        _insert_policy(
            conn,
            policy_number="POL-002",
            effective_date="2025-01-01",
            expiry_date="2025-12-31",
        )
        repo = PolicyRepository(conn)

        policy = repo.get_by_number("POL-002")

        assert policy is not None
        assert policy.is_active_on("2024-12-31") is False
        assert policy.is_active_on("2026-01-01") is False
    finally:
        conn.close()


def test_is_active_on_returns_true_inside_policy_window_for_active_status(
    tmp_path: Path,
) -> None:
    """Symmetry check: an ACTIVE policy is active on a date inside its window."""
    conn = _seed_connection(tmp_path)
    try:
        _insert_policy(
            conn,
            policy_number="POL-003",
            status=PolicyStatus.ACTIVE.value,
            effective_date="2025-01-01",
            expiry_date="2025-12-31",
        )
        repo = PolicyRepository(conn)

        policy = repo.get_by_number("POL-003")

        assert policy is not None
        assert policy.is_active_on("2025-06-15") is True
    finally:
        conn.close()
