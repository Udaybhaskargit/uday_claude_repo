"""Static check of the real, committed `backend/migrations/` files (E3-S1 AC1 / F024).

This is a direct assertion against the actual shipped `.sql` files, distinct
from the synthetic-directory edge-case tests in `test_migration_runner.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
_FILENAME_RE = re.compile(r"^(\d{4})_[a-z_]+\.sql$")

EXPECTED_NAMES = [
    "0001_create_policies.sql",
    "0002_create_claims.sql",
    "0003_create_claim_documents.sql",
    "0004_create_fraud_screenings.sql",
    "0005_create_assessments.sql",
    "0006_create_decisions.sql",
    "0007_create_settlements.sql",
    "0008_create_claim_state_transitions.sql",
    "0009_create_admin_overrides.sql",
]


def test_migration_filenames_match_naming_convention() -> None:
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
    assert sql_files, "expected backend/migrations/*.sql files to exist"

    for path in sql_files:
        assert _FILENAME_RE.match(path.name), (
            f"{path.name} does not match NNNN_description.sql"
        )


def test_migration_numbers_are_sequential_starting_at_one() -> None:
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
    numbers = [int(_FILENAME_RE.match(p.name).group(1)) for p in sql_files]  # type: ignore[union-attr]

    assert numbers == list(range(1, len(numbers) + 1))


def test_exactly_nine_expected_migration_files_present() -> None:
    actual_names = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
    assert actual_names == EXPECTED_NAMES
