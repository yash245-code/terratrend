"""End-to-end database layer integration test for TerraTrend."""
from __future__ import annotations

import pytest
from app import create_app
from config import Config
from db.base import get_session
from db.repositories.clients_repo import ClientsRepository
from db.repositories.results_repo import ResultsRepository
from teratrend.services.reference_cache import get_reference_cache


@pytest.fixture
def integration_client(synthetic_grid_and_store):
    """Full integration test client with mock cubes and active database."""
    store, _ = synthetic_grid_and_store
    app = create_app()
    app.config["TESTING"] = True
    app.extensions["cubes"] = store
    with app.test_client() as client:
        yield client


def test_complete_database_lifecycle(integration_client):
    """Verify complete end-to-end lifecycle: reference cache, assess, cache hit, save, rerun."""
    # 1. Reference Data Cache Verification
    cache = get_reference_cache()
    assert cache.counts["crops"] == 20
    assert cache.counts["states"] == 36
    assert cache.reference_version is not None

    # 2. First Assessment -> Cache Miss
    res1 = integration_client.get("/api/assess?lat=21.1458&lon=79.0882&crop=wheat")
    assert res1.status_code == 200
    data1 = res1.get_json()
    assert data1["meta"]["cache"] in ("miss", "hit")
    assert data1["overall"]["score"] > 0

    # 3. Second Assessment -> Guaranteed Cache Hit
    res2 = integration_client.get("/api/assess?lat=21.1458&lon=79.0882&crop=wheat")
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["meta"]["cache"] == "hit"
    assert data2["overall"]["score"] == data1["overall"]["score"]

    # 4. Anonymous Client and Location Save
    res_loc = integration_client.post(
        "/api/saved/locations",
        json={"label": "Plot Alpha", "lat": 21.1458, "lon": 79.0882},
    )
    assert res_loc.status_code == 201
    loc = res_loc.get_json()
    loc_id = loc["id"]

    # 5. Save Scenario Snapshot
    res_scen = integration_client.post(
        "/api/saved/scenarios",
        json={
            "location_id": loc_id,
            "label": "Scenario Alpha Baseline",
            "crop_key": "wheat",
            "options": {"lat": 21.1458, "lon": 79.0882, "area_ha": 3.0},
            "snapshot_json": data1,
            "data_version": data1["meta"].get("data_version", "v1.0.0"),
        },
    )
    assert res_scen.status_code == 201
    scen = res_scen.get_json()
    scen_id = scen["id"]

    # 6. Rerun Scenario and Verify Diff
    res_rerun = integration_client.post(f"/api/saved/scenarios/{scen_id}/run")
    assert res_rerun.status_code == 200
    rerun_data = res_rerun.get_json()
    assert "changes" in rerun_data
    assert "fresh_assessment" in rerun_data
    assert rerun_data["changes"]["score_diff"] == 0.0  # Identical data cubes

    # 7. Clean up Client Data
    res_del_me = integration_client.delete("/api/me")
    assert res_del_me.status_code == 200
    assert res_del_me.get_json()["status"] == "deleted"
