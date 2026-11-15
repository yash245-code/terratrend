"""Tests for database seeding and JSON export."""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from db.base import Base
from db.export import export_database
from db.models.reference import Crop, State
from db.seed import seed_database


@pytest.fixture
def seed_session(tmp_path: Path):
    """Create isolated SQLite database with full schema for seeding tests."""
    db_file = tmp_path / "seed_test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


def test_seed_and_idempotency(seed_session):
    """Verify seed imports 20 crops, 36 states, and subsequent seed runs update idempotently."""
    # Run 1: initial seed
    stats1 = seed_database(seed_session)
    seed_session.commit()

    assert stats1["crops"]["inserted"] == 20
    assert stats1["regions"]["inserted"] == 36
    assert stats1["rules"]["inserted"] > 0
    assert stats1["economics"]["inserted"] > 0

    # Verify counts in DB
    crop_cnt = seed_session.scalar(select(func.count(Crop.id)))
    state_cnt = seed_session.scalar(select(func.count(State.id)))
    assert crop_cnt == 20
    assert state_cnt == 36

    # Run 2: second run should not insert duplicates
    stats2 = seed_database(seed_session)
    seed_session.commit()

    assert stats2["crops"]["inserted"] == 0
    assert stats2["regions"]["inserted"] == 0
    assert stats2["crops"]["updated"] == 20
    assert stats2["regions"]["updated"] == 36

    # DB total count must remain exact
    crop_cnt2 = seed_session.scalar(select(func.count(Crop.id)))
    assert crop_cnt2 == 20


def test_export_database(seed_session, tmp_path: Path):
    """Verify database export writes valid JSON files matching seed format."""
    seed_database(seed_session)
    seed_session.commit()

    out_dir = tmp_path / "exported_seed"
    counts = export_database(seed_session, to_dir=out_dir)

    assert counts["crops"] == 20
    assert (out_dir / "crops" / "crop_requirements.json").exists()
    assert (out_dir / "rules" / "amendments.json").exists()
    assert (out_dir / "economics" / "crop_costs.json").exists()

    with open(out_dir / "crops" / "crop_requirements.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "wheat" in data
    assert data["wheat"]["key"] == "wheat"
