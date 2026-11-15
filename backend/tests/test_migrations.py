"""Tests for Alembic database migrations."""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_downgrade_cycle(tmp_path: Path):
    """Test full Alembic migration cycle: upgrade head -> downgrade base -> upgrade head."""
    db_file = tmp_path / "migration_test.db"
    db_url = f"sqlite:///{db_file}"

    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = backend_dir / "alembic.ini"
    assert ini_path.exists()

    cfg = AlembicConfig(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)

    # 1. Upgrade to head
    command.upgrade(cfg, "head")

    # Verify tables created
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "crops" in tables
    assert "states" in tables
    assert "crop_costs" in tables
    assert "assessments_cache" in tables
    assert "saved_scenarios" in tables
    assert "grid_cells" in tables

    # 2. Downgrade to base
    command.downgrade(cfg, "base")
    inspector = inspect(engine)
    remaining_tables = set(inspector.get_table_names())
    assert "crops" not in remaining_tables
    assert "crop_costs" not in remaining_tables

    # 3. Upgrade to head again
    command.upgrade(cfg, "head")
    inspector = inspect(engine)
    recreated_tables = set(inspector.get_table_names())
    assert "crops" in recreated_tables
    assert "states" in recreated_tables
    engine.dispose()
