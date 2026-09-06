"""NFR-08 structural check: the Types layer must import nothing else in src/.

Per .claude/architecture.md, Types is Layer 1 (the lowest layer) and may not
import from Config, Repository, Service, API, or UI. This test parses every
module under backend/src/types/ with the ast module (rather than grepping) so it
is robust to import style (absolute, relative, aliased, multi-name).
"""

import ast
from pathlib import Path

_TYPES_DIR = Path(__file__).resolve().parents[2] / "src" / "types"
_FORBIDDEN_TOP_LEVEL_MODULES = {"config", "repositories", "services", "api", "ui"}
_FORBIDDEN_DOTTED_PREFIXES = (
    "src.config",
    "src.repositories",
    "src.services",
    "src.api",
    "src.ui",
)


def _imported_module_names(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


def test_types_layer_source_files_exist() -> None:
    python_files = list(_TYPES_DIR.glob("*.py"))
    assert python_files, "expected backend/src/types/*.py to contain modules"


def test_types_layer_imports_nothing_from_higher_layers() -> None:
    for py_file in _TYPES_DIR.glob("*.py"):
        for module_name in _imported_module_names(py_file):
            top_level = module_name.split(".")[0]
            assert top_level not in _FORBIDDEN_TOP_LEVEL_MODULES, (
                f"{py_file.name} imports forbidden top-level module '{module_name}'"
            )
            assert not module_name.startswith(_FORBIDDEN_DOTTED_PREFIXES), (
                f"{py_file.name} imports forbidden module '{module_name}'"
            )
