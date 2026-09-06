"""E3-S4 AC2 / F037 structural check: audit repositories expose no update()/delete().

Uses `inspect.getmembers` to enumerate the public methods actually bound on
each of the five append-only repository classes and asserts none of them is
named `update` or `delete` (case-insensitively, so `Update`/`DELETE` would
also be caught). This is a genuine reflection check on the live class object,
not a static "I didn't write one" assumption -- adding a dummy
`def update(self): pass` to any of the five classes makes this test fail.
"""

from __future__ import annotations

import inspect

from src.repositories.admin_override_repository import AdminOverrideRepository
from src.repositories.assessment_repository import AssessmentRepository
from src.repositories.decision_repository import DecisionRepository
from src.repositories.fraud_screening_repository import FraudScreeningRepository
from src.repositories.settlement_repository import SettlementRepository

_FORBIDDEN_METHOD_NAMES = {"update", "delete"}

_AUDIT_REPOSITORY_CLASSES = [
    FraudScreeningRepository,
    AssessmentRepository,
    DecisionRepository,
    SettlementRepository,
    AdminOverrideRepository,
]


def _public_method_names(cls: type) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_audit_repositories_expose_no_update_or_delete_method() -> None:
    offenders: dict[str, set[str]] = {}
    for cls in _AUDIT_REPOSITORY_CLASSES:
        method_names = _public_method_names(cls)
        forbidden_hits = {
            name for name in method_names if name.lower() in _FORBIDDEN_METHOD_NAMES
        }
        if forbidden_hits:
            offenders[cls.__name__] = forbidden_hits

    assert offenders == {}, (
        f"found forbidden update()/delete() methods on audit repositories: {offenders}"
    )


def test_audit_repository_classes_still_expose_their_read_and_insert_methods() -> None:
    """Guard against the check above passing only because a class has no methods at all."""
    expected_public_methods = {
        FraudScreeningRepository: {"insert", "get_latest"},
        AssessmentRepository: {"insert", "get_latest_assessment"},
        DecisionRepository: {"insert", "get_latest"},
        SettlementRepository: {"insert", "list_all"},
        AdminOverrideRepository: {"insert", "list_admin_overrides"},
    }
    for cls, expected in expected_public_methods.items():
        actual = _public_method_names(cls)
        assert expected <= actual, f"{cls.__name__} is missing expected methods {expected - actual}"
