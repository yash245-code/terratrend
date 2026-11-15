"""Static AST test verifying strict clean-architecture purity of core scientific modules.

Modules implementing agronomic, trend, consensus, climatology, suitability, crop,
amendment, economics, industry, units, and regional logic MUST NEVER import
SQLAlchemy, Flask, or Alembic.
"""
from __future__ import annotations

import ast
from pathlib import Path
import pytest

PURE_MODULES = [
    "advisor.py",
    "amendments.py",
    "climatology.py",
    "consensus.py",
    "crops.py",
    "economics.py",
    "industry.py",
    "regions.py",
    "suitability.py",
    "trend_engine.py",
    "units.py",
]

FORBIDDEN_FRAMEWORKS = {"flask", "sqlalchemy", "alembic"}


@pytest.mark.parametrize("module_filename", PURE_MODULES)
def test_pure_modules_do_not_import_frameworks(module_filename: str):
    """Ensure pure domain logic modules contain no framework imports."""
    backend_dir = Path(__file__).resolve().parent.parent
    file_path = backend_dir / "teratrend" / module_filename
    assert file_path.exists(), f"Pure module file missing: {file_path}"

    source_code = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source_code, filename=str(file_path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_pkg = alias.name.split(".")[0]
                assert root_pkg not in FORBIDDEN_FRAMEWORKS, (
                    f"Forbidden import '{alias.name}' detected in pure module '{module_filename}' at line {node.lineno}"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_pkg = node.module.split(".")[0]
                assert root_pkg not in FORBIDDEN_FRAMEWORKS, (
                    f"Forbidden from-import '{node.module}' detected in pure module '{module_filename}' at line {node.lineno}"
                )
