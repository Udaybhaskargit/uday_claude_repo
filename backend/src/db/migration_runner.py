"""Hand-rolled SQL migration runner (Repository layer, E3-S1).

Discovers numbered `.sql` files in a migrations directory, validates strict
sequential numbering with no gaps starting at `0001`, and applies each
not-yet-applied migration exactly once. Already-applied migrations are
checksum-verified on every run so a post-application edit to a committed
migration file is caught as a startup error rather than silently ignored
(BRD sec 7.5).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

from src.types.exceptions import ConfigError

_MIGRATION_FILENAME_RE = re.compile(r"^(\d{4})_[a-z_]+\.sql$")

_BOOKKEEPING_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


def run_migrations(conn: sqlite3.Connection, migrations_dir: str) -> None:
    """Apply every not-yet-applied migration in `migrations_dir`, in order.

    Raises `ConfigError` (F024/F027) if:
      - a migration filename doesn't match `NNNN_description.sql`;
      - the migration numbers have a duplicate or a gap (must start at
        `0001` and increase by exactly 1 with no skips); or
      - an already-applied migration's on-disk checksum no longer matches
        the checksum recorded when it was applied (a post-application edit).

    Re-running against a database that already has every migration applied
    is a no-op (F026): each file is skipped once its checksum is confirmed
    unchanged.
    """
    migration_paths = _discover_migrations(migrations_dir)

    conn.execute(_BOOKKEEPING_TABLE_DDL)
    conn.commit()

    applied_checksums = _load_applied_checksums(conn)

    for path in migration_paths:
        checksum = _checksum(path)
        recorded_checksum = applied_checksums.get(path.name)

        if recorded_checksum is not None:
            if recorded_checksum != checksum:
                raise ConfigError(
                    f"Migration {path.name!r} failed checksum verification: "
                    f"it was modified after being applied (post-application "
                    f"edit detected). Recorded checksum {recorded_checksum!r}, "
                    f"on-disk checksum {checksum!r}."
                )
            continue

        sql = path.read_text(encoding="utf-8")
        with conn:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (filename, checksum, applied_at) "
                "VALUES (?, ?, datetime('now'))",
                (path.name, checksum),
            )


def _discover_migrations(migrations_dir: str) -> list[Path]:
    """Return migration file paths sorted by numeric prefix, validated for
    strict sequential numbering (no gaps, no duplicates, starting at 1)."""
    directory = Path(migrations_dir)
    candidate_paths = sorted(directory.glob("*.sql"), key=lambda p: p.name)

    numbered: list[tuple[int, Path]] = []
    for path in candidate_paths:
        match = _MIGRATION_FILENAME_RE.match(path.name)
        if match is None:
            raise ConfigError(
                f"Migration filename {path.name!r} does not match the "
                f"required NNNN_description.sql pattern."
            )
        numbered.append((int(match.group(1)), path))

    numbered.sort(key=lambda item: item[0])

    seen_numbers: set[int] = set()
    for number, path in numbered:
        if number in seen_numbers:
            raise ConfigError(
                f"Duplicate migration number {number:04d} found (file "
                f"{path.name!r}); migration numbers must be unique."
            )
        seen_numbers.add(number)

    expected_number = 1
    for number, path in numbered:
        if number != expected_number:
            raise ConfigError(
                f"Migration numbering gap: expected {expected_number:04d}, "
                f"found {number:04d} (file {path.name!r}). Migration numbers "
                f"must be strictly sequential with no gaps, starting at 0001."
            )
        expected_number += 1

    return [path for _, path in numbered]


def _load_applied_checksums(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT filename, checksum FROM schema_migrations").fetchall()
    return {filename: checksum for filename, checksum in rows}


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
