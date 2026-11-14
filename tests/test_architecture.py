"""Enforces the dependency rule of design §2: the core imports no framework or SDK."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "clinical_deid"
FORBIDDEN = {"fastapi", "starlette", "transformers", "torch", "boto3", "botocore", "httpx"}
CORE_FILES = sorted(
    [*PACKAGE.joinpath("domain").glob("*.py"), PACKAGE / "ports.py", PACKAGE / "cascade.py"]
)


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda p: p.name)
def test_core_module_imports_no_external_framework(path: Path):
    assert path.exists()
    assert _imported_roots(path).isdisjoint(FORBIDDEN)


@pytest.mark.parametrize(
    "path", sorted(PACKAGE.rglob("*.py")), ids=lambda p: str(p.relative_to(PACKAGE))
)
def test_product_never_imports_offline_modeling_code(path: Path):
    """ADR-0007: ``modeling/`` is offline tooling; the deployed package must not depend on it."""
    assert "modeling" not in _imported_roots(path)


def test_core_files_are_present():
    names = {p.name for p in CORE_FILES}
    assert {"entities.py", "categories.py", "masker.py", "ports.py", "cascade.py"} <= names
