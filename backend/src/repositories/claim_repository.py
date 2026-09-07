"""Claim repository (Repository layer, E3-S3).

Data access for the `claims` table: creation, status mutation exclusively via
the E1-S2 state-machine gate (`src.types.state_machine.transition`), filtered
listing for the document/fraud/assessor/admin queues, and duplicate-FNOL
detection.

Per NFR-08 / `backend/tests/architecture/test_state_mutation_gate.py`, this
repository never assigns to `Claim.status` itself -- `apply_transition()`
delegates the decision entirely to `state_machine.transition()` and only
persists the result.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from src.types.enums import ClaimEvent, ClaimStatus, ClaimType
from src.types.models import Claim, ClaimStateTransition
from src.types.state_machine import transition


class ClaimRepository:
    """SQLite-backed data access for `Claim` entities."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(
        self,
        *,
        policy_id: int,
        claim_type: ClaimType,
        incident_date: str,
        claim_amount: Decimal,
        parent_claim_id: int | None = None,
    ) -> int:
        """Insert a new claim row with `status='INTAKE'` and return its id.

        `claim_amount` is stored as a canonical decimal string, e.g.
        `str(Decimal("35000.00"))`, per the Money-fields convention in
        data-models.md (AC1).

        `parent_claim_id` (E7-S2 AC1) links a reopened sub-claim back to the
        original claim it disputes; it is optional and defaults to `None` for
        every ordinary (non-reopen) FNOL submission, so this is a
        backward-compatible additive change -- every existing caller that
        omits it keeps getting `NULL` in that column, unchanged from before.
        """
        now = datetime.now(UTC).isoformat()
        cursor = self._connection.execute(
            "INSERT INTO claims "
            "(policy_id, claim_type, incident_date, claim_amount, status, "
            "parent_claim_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                policy_id,
                claim_type.value,
                incident_date,
                str(Decimal(claim_amount)),
                ClaimStatus.INTAKE.value,
                parent_claim_id,
                now,
                now,
            ),
        )
        self._connection.commit()
        claim_id = cursor.lastrowid
        assert claim_id is not None
        return claim_id

    def get_by_id(self, claim_id: int) -> Claim | None:
        """Look up a claim by id, or `None` if it does not exist."""
        row = self._connection.execute(
            "SELECT id, policy_id, claim_type, incident_date, claim_amount, "
            "status, parent_claim_id, created_at, updated_at "
            "FROM claims WHERE id = ?",
            (claim_id,),
        ).fetchone()

        if row is None:
            return None

        return _row_to_claim(row)

    def apply_transition(
        self, claim_id: int, event: ClaimEvent, actor_id: str | None = None
    ) -> ClaimStateTransition:
        """Apply `event` to the claim identified by `claim_id`.

        Loads the claim, calls `state_machine.transition()` -- the ONLY place
        allowed to decide the next state -- and, only if that succeeds,
        persists both the `claims.status` update and the new
        `claim_state_transitions` audit row in a single DB transaction (AC2).

        If `transition()` raises `InvalidClaimStateException`, it propagates
        unchanged and no write happens at all: the DB statements below never
        run because they're only reached after `transition()` returns
        successfully (AC3).

        Raises `LookupError` if no claim with `claim_id` exists.
        """
        claim = self.get_by_id(claim_id)
        if claim is None:
            raise LookupError(f"Claim {claim_id} not found.")

        claim_transition = transition(claim, event, actor_id)

        with self._connection:
            self._connection.execute(
                "UPDATE claims SET status = ?, updated_at = ? WHERE id = ?",
                (claim_transition.to_state.value, claim_transition.timestamp, claim_id),
            )
            self._connection.execute(
                "INSERT INTO claim_state_transitions "
                "(claim_id, from_state, to_state, event, actor_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    claim_transition.claim_id,
                    claim_transition.from_state.value,
                    claim_transition.to_state.value,
                    claim_transition.event,
                    claim_transition.actor_id,
                    claim_transition.timestamp,
                ),
            )

        return claim_transition

    def list_by_status_and_product(
        self,
        status: ClaimStatus | None = None,
        claim_type: ClaimType | None = None,
    ) -> list[Claim]:
        """Return claims filtered by `status` and/or `claim_type`.

        Both filters are optional and composable (AC4): omitting one means
        "don't filter on that column".
        """
        query = (
            "SELECT id, policy_id, claim_type, incident_date, claim_amount, "
            "status, parent_claim_id, created_at, updated_at FROM claims"
        )
        conditions: list[str] = []
        params: list[str] = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)
        if claim_type is not None:
            conditions.append("claim_type = ?")
            params.append(claim_type.value)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        rows = self._connection.execute(query, params).fetchall()
        return [_row_to_claim(row) for row in rows]

    def exists_duplicate(self, policy_id: int, incident_date: str) -> bool:
        """True iff a claim already exists for this `(policy_id, incident_date)`.

        Interpretation note (the story says "non-void" but does not define an
        exclusion list of statuses): any existing claim row for the pair
        counts as a duplicate, regardless of its current status. There is no
        documented set of statuses to exclude, so treating every row as
        "non-void" is the narrowest reading that doesn't silently invent a
        rule the spec never stated.
        """
        row = self._connection.execute(
            "SELECT 1 FROM claims WHERE policy_id = ? AND incident_date = ? LIMIT 1",
            (policy_id, incident_date),
        ).fetchone()
        return row is not None

    def count_recent_claims(
        self,
        policy_id: int,
        before_date: str,
        window_days: int,
        exclude_claim_id: int | None = None,
    ) -> int:
        """Count claims on `policy_id` filed in the `window_days` before `before_date`.

        Added in Group F (E5-S3) to supply `FraudScoringInput.recent_claim_
        count_90d` (the CLAIM_FREQUENCY rule). The window is the half-open
        interval `(before_date - window_days, before_date]` -- inclusive of
        `before_date` itself so a same-day prior claim counts, exclusive of
        the far edge so exactly `window_days` ago does not double-count
        against an adjacent window. `exclude_claim_id` lets a caller omit the
        very claim being scored from its own frequency count, since that
        claim's own row already exists in `claims` by the time scoring runs.
        """
        window_start = (date.fromisoformat(before_date) - timedelta(days=window_days)).isoformat()

        query = (
            "SELECT COUNT(*) AS n FROM claims "
            "WHERE policy_id = ? AND incident_date > ? AND incident_date <= ?"
        )
        params: list[int | str] = [policy_id, window_start, before_date]

        if exclude_claim_id is not None:
            query += " AND id != ?"
            params.append(exclude_claim_id)

        row = self._connection.execute(query, params).fetchone()
        count: int = row["n"]
        return count


def _row_to_claim(row: sqlite3.Row) -> Claim:
    return Claim(
        id=row["id"],
        policy_id=row["policy_id"],
        claim_type=ClaimType(row["claim_type"]),
        incident_date=row["incident_date"],
        claim_amount=Decimal(row["claim_amount"]),
        status=ClaimStatus(row["status"]),
        parent_claim_id=row["parent_claim_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
