"""FraudScreening repository (Repository layer, E3-S4).

Data access for the append-only `fraud_screenings` table. Every fraud
scoring run inserts a new row rather than overwriting the previous one, so
retries preserve the full audit history (NFR-02, data-models.md sec 2.4).
Only `insert()` and `get_latest()` are exposed -- no `update()`/`delete()`,
per E3-S4 AC2.
"""

from __future__ import annotations

import json
import sqlite3

from src.types.models import FraudScreening


class FraudScreeningRepository:
    """SQLite-backed, insert-only data access for `FraudScreening` entities."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert(
        self,
        claim_id: int,
        score: int,
        breakdown: list[dict[str, object]],
        threshold: int,
        flagged: bool,
    ) -> int:
        """Append a new fraud screening row for `claim_id` and return its id.

        Never overwrites a prior screening for the same claim (E3-S4 AC1) --
        each call inserts an independent row.
        """
        cursor = self._connection.execute(
            "INSERT INTO fraud_screenings "
            "(claim_id, score, breakdown, threshold, flagged, created_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (claim_id, score, json.dumps(breakdown), threshold, int(flagged)),
        )
        self._connection.commit()
        new_id = cursor.lastrowid
        assert new_id is not None
        return new_id

    def get_latest(self, claim_id: int) -> FraudScreening | None:
        """Return the most recently inserted screening for `claim_id`.

        Ties on `created_at` (possible under SQLite's second-level timestamp
        granularity) are broken by the highest `id`, which is always the most
        recently inserted row since ids are monotonically increasing.
        """
        row = self._connection.execute(
            "SELECT id, claim_id, score, breakdown, threshold, flagged, created_at "
            "FROM fraud_screenings WHERE claim_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (claim_id,),
        ).fetchone()

        if row is None:
            return None

        return FraudScreening(
            id=row["id"],
            claim_id=row["claim_id"],
            score=row["score"],
            breakdown=json.loads(row["breakdown"]),
            threshold=row["threshold"],
            flagged=bool(row["flagged"]),
            created_at=row["created_at"],
        )
