"""Policy repository (Repository layer, E3-S2).

Data access for the `policies` table: lookup by policy number. The
date-window / status check (`Policy.is_active_on()`) already lives on the
`Policy` dataclass itself (data-models.md sec 2.1) -- this repository's job
is only to reconstruct a fully-typed `Policy` instance from a SQLite row so
that method works correctly for callers (E3-S2 AC3).
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from src.types.enums import ClaimType, PolicyStatus
from src.types.models import Policy


class PolicyRepository:
    """SQLite-backed data access for `Policy` entities."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_by_number(self, policy_number: str) -> Policy | None:
        """Look up a policy by its unique `policy_number`.

        Returns `None` when no matching row exists (E3-S2 AC2) rather than
        raising, so callers can produce a domain-level error instead of
        handling a database exception.
        """
        row = self._connection.execute(
            "SELECT id, policy_number, product_type, status, sum_insured, "
            "effective_date, expiry_date, created_at "
            "FROM policies WHERE policy_number = ?",
            (policy_number,),
        ).fetchone()

        return None if row is None else _row_to_policy(row)

    def get_by_id(self, policy_id: int) -> Policy | None:
        """Look up a policy by its primary key `id`.

        Added in Group F (E5-S3) so `fraud_screening_service` can resolve
        the `Policy` a `Claim.policy_id` foreign key points at -- `claims`
        stores the numeric id, not the human-facing `policy_number`, so the
        E3-S2 `get_by_number()` lookup alone isn't enough for that caller.
        Same `None`-on-miss contract as `get_by_number()`.
        """
        row = self._connection.execute(
            "SELECT id, policy_number, product_type, status, sum_insured, "
            "effective_date, expiry_date, created_at "
            "FROM policies WHERE id = ?",
            (policy_id,),
        ).fetchone()

        return None if row is None else _row_to_policy(row)


def _row_to_policy(row: sqlite3.Row) -> Policy:
    return Policy(
        id=row["id"],
        policy_number=row["policy_number"],
        product_type=ClaimType(row["product_type"]),
        status=PolicyStatus(row["status"]),
        sum_insured=Decimal(row["sum_insured"]),
        effective_date=row["effective_date"],
        expiry_date=row["expiry_date"],
        created_at=row["created_at"],
    )
