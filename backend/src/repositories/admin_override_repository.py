"""AdminOverride repository (Repository layer, E3-S4).

Data access for the append-only `admin_overrides` audit trail
(data-models.md sec 2.9). Only `insert()` and `list_admin_overrides()` are
exposed -- no `update()`/`delete()`, per E3-S4 AC2.
"""

from __future__ import annotations

import sqlite3

from src.types.enums import AdminOverrideCommand
from src.types.models import AdminOverride


class AdminOverrideRepository:
    """SQLite-backed, insert-only data access for `AdminOverride` entities."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert(
        self,
        claim_id: int,
        admin_actor_id: str,
        command: AdminOverrideCommand,
        reason_code: str,
    ) -> int:
        """Append a new admin override row and return its id."""
        cursor = self._connection.execute(
            "INSERT INTO admin_overrides "
            "(claim_id, admin_actor_id, command, reason_code, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (claim_id, admin_actor_id, command.value, reason_code),
        )
        self._connection.commit()
        new_id = cursor.lastrowid
        assert new_id is not None
        return new_id

    def list_admin_overrides(self, claim_id: int) -> list[AdminOverride]:
        """Return all override rows for `claim_id`, oldest first.

        Ordered ascending by `created_at`/`id` (opposite of the "latest"
        lookups on the other audit repositories), per E3-S4 AC4.
        """
        rows = self._connection.execute(
            "SELECT id, claim_id, admin_actor_id, command, reason_code, created_at "
            "FROM admin_overrides WHERE claim_id = ? "
            "ORDER BY created_at ASC, id ASC",
            (claim_id,),
        ).fetchall()

        return [
            AdminOverride(
                id=row["id"],
                claim_id=row["claim_id"],
                admin_actor_id=row["admin_actor_id"],
                command=AdminOverrideCommand(row["command"]),
                reason_code=row["reason_code"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
