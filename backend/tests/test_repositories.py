"""Unit tests for TerraTrend database repositories."""
from __future__ import annotations

from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.base import Base
from db.models.reference import State
from db.repositories.clients_repo import ClientsRepository, LimitExceededError
from db.repositories.economics_repo import EconomicsRepository
from db.repositories.grid_repo import GridRepository
from db.repositories.reference_repo import ReferenceRepository
from db.repositories.results_repo import ResultsRepository
from db.seed import seed_database


@pytest.fixture
def repo_session(tmp_path: Path):
    """Create seeded SQLite database for repository testing."""
    db_file = tmp_path / "repo_test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    seed_database(session)
    session.commit()
    yield session
    session.close()
    engine.dispose()


def test_reference_repository(repo_session):
    """Test ReferenceRepository loads pure dictionaries."""
    repo = ReferenceRepository(repo_session)
    crops = repo.load_crops()
    assert "wheat" in crops
    assert crops["wheat"]["key"] == "wheat"
    assert len(crops["wheat"]["temperature_trapezoid"]) == 4

    rules = repo.load_amendment_rules()
    assert isinstance(rules, list)
    assert len(rules) > 0
    assert "condition" in rules[0]

    trend_rules = repo.load_trend_rules()
    assert "root_moisture_decreasing" in trend_rules
    assert "pearl_millet" in trend_rules["root_moisture_decreasing"]["crops"]

    regions = repo.load_regions()
    assert "states" in regions
    assert len(regions["states"]) == 36

    st = repo.get_state_by_name("Punjab")
    assert st is not None
    assert st["code"] == "PB"


def test_economics_repository(repo_session):
    """Test EconomicsRepository data loading, coverage, and mandi upserts."""
    repo = EconomicsRepository(repo_session)
    econ_data = repo.load_economics_data()
    assert len(econ_data.crop_costs) > 0
    assert len(econ_data.benchmark_yields) > 0
    assert "msp" in econ_data.prices

    cov = repo.coverage_matrix()
    assert cov["total_crops"] == 20
    assert cov["status"] == "complete"

    # Upsert dynamic mandi prices
    inserted = repo.upsert_mandi_prices([
        {
            "crop": "wheat",
            "state": "Punjab",
            "modal_price_per_q": 2375.0,
            "yoy_change_pct": 5.2,
            "volatility_cv": 0.12,
            "as_of": "2026-10-15",
            "source": "Agmarknet Live",
        }
    ])
    repo_session.commit()
    assert inserted == 1


def test_results_repository(repo_session):
    """Test ResultsRepository cache put, hit count increment, pruning, and geocode cache."""
    repo = ResultsRepository(repo_session)
    repo.put_cached(
        cache_key="test_cache_key_1",
        cell_lat=28.5,
        cell_lon=77.2,
        state_id=1,
        district_id=None,
        crop_key="wheat",
        season="rabi",
        irrigation="irrigated",
        options_hash="opt123",
        data_version="v1",
        result_json={"overall": {"score": 85.0}},
    )
    repo_session.commit()

    # Get cached: hit count should increment
    hit1 = repo.get_cached("test_cache_key_1")
    assert hit1 is not None
    assert hit1["overall"]["score"] == 85.0

    # Put and get geocode cache
    repo.put_geocode("new delhi", [{"name": "New Delhi", "lat": 28.61, "lon": 77.20}])
    repo_session.commit()
    geo_hit = repo.get_geocode("new delhi")
    assert geo_hit is not None
    assert geo_hit[0]["lat"] == 28.61

    # Prune and clear
    removed = repo.prune(max_rows=100)
    assert removed == 0  # Only 1 entry, under max_rows
    cleared = repo.clear()
    repo_session.commit()
    assert cleared == 1


def test_clients_repository(repo_session):
    """Test anonymous client creation, saved locations with limit, scenarios, and deletion."""
    repo = ClientsRepository(repo_session)
    cid = repo.create_or_touch_client()
    assert cid is not None

    # Save location
    loc = repo.save_location(client_id=cid, label="Plot North", lat=30.9, lon=75.8)
    repo_session.commit()
    assert loc["id"] is not None
    assert loc["label"] == "Plot North"

    # Enforce limit
    with pytest.raises(LimitExceededError):
        repo.save_location(client_id=cid, label="Plot Overflow", lat=30.9, lon=75.8, max_limit=1)

    # Save scenario
    scen = repo.save_scenario(
        client_id=cid,
        location_id=loc["id"],
        label="Wheat 2026",
        crop_key="wheat",
        options={"area_ha": 2.5},
        snapshot_json={"overall": {"score": 82.0}},
        data_version="v1.0.0",
    )
    repo_session.commit()
    assert scen["id"] is not None

    # List scenarios
    scens = repo.list_saved_scenarios(cid)
    assert len(scens) == 1

    # Delete client data
    deleted = repo.delete_client_data(cid)
    repo_session.commit()
    assert deleted is True
    assert len(repo.list_saved_locations(cid)) == 0


def test_grid_repository(repo_session):
    """Test bulk insertion into territorial grid and querying top crop cells."""
    repo = GridRepository(repo_session)
    cells_payload = [
        {
            "cell_lat": 30.5,
            "cell_lon": 76.0,
            "state_id": 1,
            "district_id": None,
            "overall_score": 88.0,
            "temperature_score": 85.0,
            "moisture_score": 90.0,
            "soil_ph_score": 92.0,
            "soil_quality_score": 84.0,
            "climate_score": 89.0,
            "data_version": "v1",
            "crop_scores": [
                {"crop_key": "wheat", "suitability_score": 91.5, "roi_pct": 42.0, "probability_of_loss_pct": 5.0},
                {"crop_key": "rice", "suitability_score": 75.0, "roi_pct": 28.0, "probability_of_loss_pct": 12.0},
            ],
        }
    ]
    inserted = repo.bulk_insert_cells_and_scores(cells_payload)
    repo_session.commit()
    assert inserted == 1

    best_wheat = repo.best_cells_for_crop("wheat", limit=10)
    assert len(best_wheat) == 1
    assert best_wheat[0]["suitability_score"] == 91.5

    summaries = repo.state_summary("wheat")
    assert isinstance(summaries, list)
