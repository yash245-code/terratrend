"""Tests for anonymous farmer sessions, saved locations, and economic scenarios."""
from __future__ import annotations

import pytest
from app import create_app


@pytest.fixture
def saved_client(synthetic_grid_and_store):
    """Create test client with mock cubes for saved items testing."""
    store, _ = synthetic_grid_and_store
    app = create_app()
    app.config["TESTING"] = True
    app.extensions["cubes"] = store
    with app.test_client() as client:
        yield client


def test_anonymous_client_cookie_and_me_endpoint(saved_client):
    """Verify anonymous client receives persistent tt_client_id cookie and profile stats."""
    res = saved_client.get("/api/me")
    assert res.status_code == 200
    data = res.get_json()
    assert "client_id" in data
    assert data["saved_locations_count"] == 0
    assert data["saved_scenarios_count"] == 0

    # Cookie was set
    cookie = saved_client.get_cookie("tt_client_id")
    assert cookie is not None
    assert cookie.value == data["client_id"]


def test_saved_locations_crud(saved_client):
    """Verify full CRUD lifecycle for saved plot locations."""
    # 1. Create Location
    res = saved_client.post(
        "/api/saved/locations",
        json={"label": "Karnal Experimental Farm", "lat": 29.68, "lon": 76.99},
    )
    assert res.status_code == 201
    loc = res.get_json()
    assert loc["id"] is not None
    assert loc["label"] == "Karnal Experimental Farm"

    # 2. List Locations
    res_list = saved_client.get("/api/saved/locations")
    assert res_list.status_code == 200
    list_data = res_list.get_json()
    assert list_data["count"] == 1
    assert list_data["locations"][0]["id"] == loc["id"]

    # 3. Delete Location
    res_del = saved_client.delete(f"/api/saved/locations/{loc['id']}")
    assert res_del.status_code == 200
    assert res_del.get_json()["status"] == "deleted"

    # Verify Empty
    res_empty = saved_client.get("/api/saved/locations")
    assert res_empty.get_json()["count"] == 0


def test_saved_scenarios_crud_and_rerun(saved_client):
    """Verify scenario save, fetch, rerun comparison with snapshot, and deletion."""
    # 1. Save Scenario
    snapshot_payload = {
        "location": {"requested_lat": 21.1458, "requested_lon": 79.0882},
        "overall": {"score": 75.0, "verdict": "GOOD"},
        "selected_crop_economics": {
            "returns_data": {
                "net_return_per_ha": {"chosen": 45000.0},
                "roi_pct": {"chosen": 38.5},
            }
        },
    }

    res_post = saved_client.post(
        "/api/saved/scenarios",
        json={
            "label": "Wheat High Density",
            "crop_key": "wheat",
            "options": {"lat": 21.1458, "lon": 79.0882, "area_ha": 2.0},
            "snapshot_json": snapshot_payload,
            "data_version": "v1.0.0",
        },
    )
    assert res_post.status_code == 201
    scen = res_post.get_json()
    scen_id = scen["id"]
    assert scen_id is not None

    # 2. Get Scenario
    res_get = saved_client.get(f"/api/saved/scenarios/{scen_id}")
    assert res_get.status_code == 200
    assert res_get.get_json()["label"] == "Wheat High Density"

    # 3. Rerun Scenario
    res_run = saved_client.post(f"/api/saved/scenarios/{scen_id}/run")
    assert res_run.status_code == 200
    run_data = res_run.get_json()
    assert "changes" in run_data
    assert "fresh_assessment" in run_data
    assert run_data["scenario_id"] == scen_id

    # 4. Delete Scenario
    res_del = saved_client.delete(f"/api/saved/scenarios/{scen_id}")
    assert res_del.status_code == 200
    assert res_del.get_json()["status"] == "deleted"
