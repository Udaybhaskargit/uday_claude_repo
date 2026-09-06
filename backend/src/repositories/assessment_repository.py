"""Assessment repository (Repository layer, E3-S4).

Data access for the append-only `assessments` table. Every assessment run
inserts a new row (data-models.md sec 2.5); `get_latest_assessment()` returns
the most recently inserted row for a claim so callers see the latest payable
amount without ever mutating history (E3-S4 AC3). Only `insert()` and
`get_latest_assessment()` are exposed -- no `update()`/`delete()`, per
E3-S4 AC2.

Money fields are stored as canonical decimal strings (data-models.md
Conventions) and reconstructed as `Decimal` on read -- never floats (NFR-01).
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from src.types.models import Assessment


class AssessmentRepository:
    """SQLite-backed, insert-only data access for `Assessment` entities."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert(
        self,
        claim_id: int,
        claim_amount: Decimal,
        sum_insured: Decimal,
        deductible: Decimal,
        co_pay: Decimal,
        payable_amount: Decimal,
    ) -> int:
        """Append a new assessment row for `claim_id` and return its id."""
        cursor = self._connection.execute(
            "INSERT INTO assessments "
            "(claim_id, claim_amount, sum_insured, deductible, co_pay, "
            "payable_amount, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (
                claim_id,
                str(claim_amount),
                str(sum_insured),
                str(deductible),
                str(co_pay),
                str(payable_amount),
            ),
        )
        self._connection.commit()
        new_id = cursor.lastrowid
        assert new_id is not None
        return new_id

    def get_latest_assessment(self, claim_id: int) -> Assessment | None:
        """Return the most recently inserted assessment for `claim_id`.

        Ordered by `created_at DESC, id DESC` so the highest `id` (always the
        most recently inserted row) breaks any timestamp ties caused by
        SQLite's second-level `created_at` granularity (E3-S4 AC3).
        """
        row = self._connection.execute(
            "SELECT id, claim_id, claim_amount, sum_insured, deductible, "
            "co_pay, payable_amount, created_at FROM assessments "
            "WHERE claim_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (claim_id,),
        ).fetchone()

        if row is None:
            return None

        return Assessment(
            id=row["id"],
            claim_id=row["claim_id"],
            claim_amount=Decimal(row["claim_amount"]),
            sum_insured=Decimal(row["sum_insured"]),
            deductible=Decimal(row["deductible"]),
            co_pay=Decimal(row["co_pay"]),
            payable_amount=Decimal(row["payable_amount"]),
            created_at=row["created_at"],
        )
