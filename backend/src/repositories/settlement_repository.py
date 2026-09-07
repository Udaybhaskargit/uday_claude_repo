"""Settlement repository (Repository layer, E3-S4).

Data access for the append-only, immutable `settlements` table
(data-models.md sec 2.7). Immutability is structural here: this module
exposes only `insert()`, `list_all()`, and `get_latest_for_claim()` -- no
`update()`/`delete()` method exists anywhere in this class, per E3-S4 AC2 /
E7-S1 AC2 (`backend/tests/architecture/test_audit_repositories_insert_only.py`
enforces this via reflection on the live class).

`get_latest_for_claim()` was added in Group I (E7-S1) so
`settlement_service.settle()` can return the freshly-inserted row re-read
from the DB rather than constructing it from in-memory values, matching the
same "re-query, don't just trust local state" pattern already used by
`DecisionRepository.get_latest()` and `AssessmentRepository.
get_latest_assessment()`.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from src.types.models import Settlement


class SettlementRepository:
    """SQLite-backed, insert-only data access for `Settlement` entities."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert(
        self,
        claim_id: int,
        decision_id: int,
        payout_amount: Decimal,
        payment_reference: str,
    ) -> int:
        """Append a new settlement row and return its id."""
        cursor = self._connection.execute(
            "INSERT INTO settlements "
            "(claim_id, decision_id, payout_amount, payment_reference, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (claim_id, decision_id, str(payout_amount), payment_reference),
        )
        self._connection.commit()
        new_id = cursor.lastrowid
        assert new_id is not None
        return new_id

    def get_latest_for_claim(self, claim_id: int) -> Settlement | None:
        """Return the most recently inserted settlement for `claim_id`.

        Ordered by `created_at DESC, id DESC` so the highest `id` breaks any
        timestamp ties caused by SQLite's second-level `created_at`
        granularity, matching the same tie-break convention used by
        `DecisionRepository.get_latest()` / `AssessmentRepository.
        get_latest_assessment()`. Returns `None` if `claim_id` has no
        settlement yet.
        """
        row = self._connection.execute(
            "SELECT id, claim_id, decision_id, payout_amount, payment_reference, "
            "created_at FROM settlements WHERE claim_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (claim_id,),
        ).fetchone()

        if row is None:
            return None

        return Settlement(
            id=row["id"],
            claim_id=row["claim_id"],
            decision_id=row["decision_id"],
            payout_amount=Decimal(row["payout_amount"]),
            payment_reference=row["payment_reference"],
            created_at=row["created_at"],
        )

    def list_all(self) -> list[Settlement]:
        """Return every settlement row, oldest first (audit trail listing)."""
        rows = self._connection.execute(
            "SELECT id, claim_id, decision_id, payout_amount, payment_reference, "
            "created_at FROM settlements ORDER BY created_at ASC, id ASC"
        ).fetchall()

        return [
            Settlement(
                id=row["id"],
                claim_id=row["claim_id"],
                decision_id=row["decision_id"],
                payout_amount=Decimal(row["payout_amount"]),
                payment_reference=row["payment_reference"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
