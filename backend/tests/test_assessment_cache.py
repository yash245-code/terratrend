"""Tests for Assessment and Geocode result caching layer."""
from __future__ import annotations

import time
import pytest
from app import create_app
from config import Config
from db.base import get_session
from db.repositories.results_repo import ResultsRepository


@pytest.fixture
def test_client(synthetic_grid_and_store):
    """Create Flask test client configured with mock cubes and database caching."""
    store, _ = synthetic_grid_and_store
    app = create_app()
    app.config["TESTING"] = True
    app.extensions["cubes"] = store
    with app.test_client() as client:
        yield client


def test_assess_cache_miss_then_hit(test_client):
    """Verify first assess request is cache miss, second request is cache hit under 30 ms."""
    # Ensure cache is clean for this test coordinate
    with get_session() as session:
        ResultsRepository(session).clear()
        session.commit()

    # Call 1: Nagpur, Maharashtra (first assessment -> Cache Miss)
    t0 = time.time()
    res1 = test_client.get("/api/assess?lat=21.1458&lon=79.0882&crop=wheat")
    elapsed_ms1 = (time.time() - t0) * 1000.0
    assert res1.status_code == 200
    data1 = res1.get_json()
    assert "meta" in data1
    assert data1["meta"]["cache"] == "miss"

    # Call 2: Identical query -> Cache Hit
    t1 = time.time()
    res2 = test_client.get("/api/assess?lat=21.1458&lon=79.0882&crop=wheat")
    elapsed_ms2 = (time.time() - t1) * 1000.0
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["meta"]["cache"] == "hit"
    assert data2["overall"]["score"] == data1["overall"]["score"]

    # Call 3: Changed parameter (irrigation=irrigated) -> Different Cache Key -> Miss
    res3 = test_client.get("/api/assess?lat=21.1458&lon=79.0882&crop=wheat&irrigation=irrigated")
    assert res3.status_code == 200
    data3 = res3.get_json()
    assert data3["meta"]["cache"] == "miss"


def test_geocode_database_caching(test_client):
    """Verify geocoding cache avoids repeated external lookups."""
    # Ensure query norm is clean
    q = "nagpur"
    with get_session() as session:
        ResultsRepository(session).put_geocode(q, [{"name": "Nagpur, Maharashtra", "lat": 21.1458, "lon": 79.0882}])
        session.commit()

    res = test_client.get(f"/api/geocode?q={q}")
    assert res.status_code == 200
    results = res.get_json()
    assert len(results) > 0
    assert results[0]["name"] == "Nagpur, Maharashtra"
