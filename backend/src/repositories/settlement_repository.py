"""Settlement repository (Repository layer, E3-S4).

Data access for the append-only, immutable `settlements` table
(data-models.md sec 2.7). Immutability is structural here: this module
exposes only `insert()` and `list_all()` -- no `update()`/`delete()` method
exists anywhere in this class, per E3-S4 AC2 / E7-S1 AC2.
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
