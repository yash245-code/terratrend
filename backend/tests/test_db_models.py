"""Tests for TerraTrend SQLAlchemy models and database constraints."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base
from db.models.economics import BenchmarkYield, CropCost
from db.models.reference import Crop, CropRequirement, CropSoilPreference, District, State


@pytest.fixture
def memory_db():
    """Create in-memory SQLite database with enforced foreign keys and schema."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def test_state_district_models(memory_db: Session):
    """Test State and District persistence and uniqueness."""
    state = State(code="MH", name="Maharashtra", is_union_territory=False)
    memory_db.add(state)
    memory_db.commit()
    assert state.id is not None

    district = District(state_id=state.id, name="Nagpur", lgd_code=505)
    memory_db.add(district)
    memory_db.commit()
    assert district.id is not None
    assert district.state.code == "MH"

    # Duplicate state code should fail
    dup_state = State(code="MH", name="Other Maharashtra", is_union_territory=False)
    memory_db.add(dup_state)
    with pytest.raises(IntegrityError):
        memory_db.commit()
    memory_db.rollback()


def test_crop_requirement_trapezoid_check_constraint(memory_db: Session):
    """Test CheckConstraint enforcing trapezoid order: abs_min <= opt_min <= opt_max <= abs_max."""
    crop = Crop(
        key="mustard",
        name="Mustard",
        group="oilseeds",
        cycle_days=110,
        water_demand="low",
        base_yield_cv=0.15,
        salinity_ece_max=4.0,
        source="ICAR",
    )
    memory_db.add(crop)
    memory_db.commit()

    # Valid trapezoid
    valid_req = CropRequirement(
        crop_id=crop.id,
        factor="temperature",
        abs_min=10.0,
        opt_min=18.0,
        opt_max=28.0,
        abs_max=36.0,
    )
    memory_db.add(valid_req)
    memory_db.commit()
    assert valid_req.id is not None

    # Invalid trapezoid: opt_min > opt_max
    invalid_req = CropRequirement(
        crop_id=crop.id,
        factor="rainfall",
        abs_min=100.0,
        opt_min=500.0,
        opt_max=300.0,  # opt_min > opt_max
        abs_max=800.0,
    )
    memory_db.add(invalid_req)
    with pytest.raises(IntegrityError):
        memory_db.commit()
    memory_db.rollback()


def test_benchmark_yield_positive_constraint(memory_db: Session):
    """Test CheckConstraint enforcing yield_q_ha > 0."""
    crop = Crop(
        key="chickpea",
        name="Chickpea",
        group="pulses",
        cycle_days=105,
        water_demand="low",
        base_yield_cv=0.18,
        salinity_ece_max=2.0,
        source="ICAR",
    )
    memory_db.add(crop)
    memory_db.commit()

    # Non-positive yield must fail
    bad_yield = BenchmarkYield(
        crop_id=crop.id,
        yield_q_ha=0.0,  # Constraint violates yield_q_ha > 0
        source="DES",
    )
    memory_db.add(bad_yield)
    with pytest.raises(IntegrityError):
        memory_db.commit()
    memory_db.rollback()


def test_crop_cascade_delete(memory_db: Session):
    """Ensure deleting a crop cascades to delete its requirements and preferences."""
    crop = Crop(
        key="barley",
        name="Barley",
        group="cereals",
        cycle_days=115,
        water_demand="low",
        base_yield_cv=0.14,
        salinity_ece_max=8.0,
        source="ICAR",
    )
    memory_db.add(crop)
    memory_db.commit()

    req = CropRequirement(
        crop_id=crop.id,
        factor="temperature",
        abs_min=5.0,
        opt_min=12.0,
        opt_max=22.0,
        abs_max=30.0,
    )
    pref = CropSoilPreference(crop_id=crop.id, kind="texture", class_name="loam", level="preferred")
    memory_db.add_all([req, pref])
    memory_db.commit()

    # Delete crop
    memory_db.delete(crop)
    memory_db.commit()

    # Requirements and preferences should be deleted
    remaining_reqs = memory_db.scalars(select(CropRequirement).where(CropRequirement.crop_id == crop.id)).all()
    remaining_prefs = memory_db.scalars(select(CropSoilPreference).where(CropSoilPreference.crop_id == crop.id)).all()
    assert len(remaining_reqs) == 0
    assert len(remaining_prefs) == 0
