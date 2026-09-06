"""Decision repository (Repository layer, E3-S4).

Data access for the append-only `decisions` table (data-models.md sec 2.6).
Every decision run inserts a new row; `get_latest()` returns the most
recently inserted row for a claim. Only `insert()` and `get_latest()` are
exposed -- no `update()`/`delete()`, per E3-S4 AC2.
"""

from __future__ import annotations

import sqlite3

from src.types.enums import DecisionOutcome, ReasonCode
from src.types.models import Decision


class DecisionRepository:
    """SQLite-backed, insert-only data access for `Decision` entities."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert(
        self,
        claim_id: int,
        outcome: DecisionOutcome,
        reason_code: ReasonCode,
        decided_by: str,
    ) -> int:
        """Append a new decision row for `claim_id` and return its id."""
        cursor = self._connection.execute(
            "INSERT INTO decisions (claim_id, outcome, reason_code, decided_by, "
            "created_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (claim_id, outcome.value, reason_code.value, decided_by),
        )
        self._connection.commit()
        new_id = cursor.lastrowid
        assert new_id is not None
        return new_id

    def get_latest(self, claim_id: int) -> Decision | None:
        """Return the most recently inserted decision for `claim_id`.

        Ordered by `created_at DESC, id DESC` to break ties deterministically
        under SQLite's second-level `created_at` granularity.
        """
        row = self._connection.execute(
            "SELECT id, claim_id, outcome, reason_code, decided_by, created_at "
            "FROM decisions WHERE claim_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (claim_id,),
        ).fetchone()

        if row is None:
            return None

        return Decision(
            id=row["id"],
            claim_id=row["claim_id"],
            outcome=DecisionOutcome(row["outcome"]),
            reason_code=ReasonCode(row["reason_code"]),
            decided_by=row["decided_by"],
            created_at=row["created_at"],
        )
