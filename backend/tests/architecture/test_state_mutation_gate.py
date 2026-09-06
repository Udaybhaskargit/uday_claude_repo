"""NFR-08 structural check: only state_machine.py may assign to `.status`.

E1-S2 AC3 requires that transition() be the sole mechanism that mutates
Claim.status. This test walks the AST of every module under backend/src/types/
looking for an assignment (`=` or an augmented assignment) whose target is an
attribute named `status`, and asserts that no such assignment exists outside
state_machine.py -- and that state_machine.py does contain exactly this
mutation (so the gate isn't accidentally satisfied by having no code at all).
"""

import ast
from pathlib import Path

_TYPES_DIR = Path(__file__).resolve().parents[2] / "src" / "types"
_STATE_MACHINE_FILE = "state_machine.py"


def _assigns_to_status_attribute(file_path: Path) -> bool:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "status":
                    return True
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Attribute) and node.target.attr == "status":
                return True
    return False


def test_no_direct_status_assignment_outside_state_machine() -> None:
    guarded_files = [p for p in _TYPES_DIR.glob("*.py") if p.name != _STATE_MACHINE_FILE]
    assert guarded_files, "expected other backend/src/types/*.py modules to check"
    offenders = [p.name for p in guarded_files if _assigns_to_status_attribute(p)]
    assert offenders == [], (
        f"found a direct `.status =` assignment outside {_STATE_MACHINE_FILE} in: {offenders}"
    )


def test_state_machine_contains_the_sole_status_mutation() -> None:
    state_machine_file = _TYPES_DIR / _STATE_MACHINE_FILE
    assert _assigns_to_status_attribute(state_machine_file), (
        f"expected {_STATE_MACHINE_FILE} to contain the transition() gate's `.status =` assignment"
    )
