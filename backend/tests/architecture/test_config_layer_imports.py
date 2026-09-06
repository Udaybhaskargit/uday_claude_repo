"""NFR-08 structural check: the Config layer must import only from Types.

Per .claude/architecture.md, Config is Layer 2 and may import from `src.types`
only -- never from `src.repositories`, `src.services`, `src.api`, `src.db`, or
any UI/frontend code. Mirrors the parsing approach used by
`test_layer_imports.py` for the Types layer (Group A): parse each module under
backend/src/config/ with `ast` rather than grepping, so it is robust to import
style.
"""

import ast
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "src" / "config"
_ALLOWED_TOP_LEVEL_MODULES = {"src", "types", "__future__"}
_FORBIDDEN_TOP_LEVEL_MODULES = {"repositories", "services", "api", "ui", "db"}
_FORBIDDEN_DOTTED_PREFIXES = (
    "src.repositories",
    "src.services",
    "src.api",
    "src.ui",
    "src.db",
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


def test_config_layer_source_files_exist() -> None:
    python_files = list(_CONFIG_DIR.glob("*.py"))
    assert python_files, "expected backend/src/config/*.py to contain modules"


def test_config_layer_imports_nothing_from_higher_layers() -> None:
    for py_file in _CONFIG_DIR.glob("*.py"):
        for module_name in _imported_module_names(py_file):
            top_level = module_name.split(".")[0]
            assert top_level not in _FORBIDDEN_TOP_LEVEL_MODULES, (
                f"{py_file.name} imports forbidden top-level module '{module_name}'"
            )
            assert not module_name.startswith(_FORBIDDEN_DOTTED_PREFIXES), (
                f"{py_file.name} imports forbidden module '{module_name}'"
            )


def test_config_layer_imports_only_stdlib_or_types() -> None:
    """Every non-stdlib import in src/config/ must resolve to `src.types.*`."""
    stdlib_modules = {"json", "os", "dataclasses", "pathlib", "collections", "typing"}
    for py_file in _CONFIG_DIR.glob("*.py"):
        for module_name in _imported_module_names(py_file):
            top_level = module_name.split(".")[0]
            if top_level in stdlib_modules or top_level == "__future__":
                continue
            assert module_name == "src.types" or module_name.startswith("src.types."), (
                f"{py_file.name} imports non-Types, non-stdlib module '{module_name}'"
            )
