"""Comprehensive Flask REST API integration tests.

Tests all endpoints:
- /api/health (200 healthy, 503 degraded)
- /api/datasets
- /api/indicators
- /api/provenance
- /api/region (valid and 422 OUT_OF_INDIA)
- /api/crops
- /api/economics/coverage
- /api/assess (general, specific crop, rainfed vs irrigated, 422 OUT_OF_INDIA, 400 bad params, 503 missing required layers)
- /api/economics (GET and POST with scenario overrides)
- /api/analyze (valid trend, 422 OUT_OF_INDIA, 400 unknown indicator)
- /api/consensus (valid group, 400 unknown group)
"""
import pytest
from backend.app import create_app
from backend.teratrend.cube_store import CubeStore


@pytest.fixture
def app_with_cubes(synthetic_grid_and_store):
    """Create Flask test app wired with mock cube store containing GLDAS and HWSD."""
    store, _ = synthetic_grid_and_store
    app = create_app()
    app.config["TESTING"] = True
    app.extensions["cubes"] = store
    return app


@pytest.fixture
def client(app_with_cubes):
    return app_with_cubes.test_client()


def test_health_healthy(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert data["operational"] is True
    assert "gldas" in data["loaded_cubes"]
    assert "hwsd" in data["loaded_cubes"]


def test_health_degraded_when_missing_required():
    empty_store = CubeStore()
    app = create_app()
    app.config["TESTING"] = True
    app.extensions["cubes"] = empty_store
    client = app.test_client()

    res = client.get("/api/health")
    assert res.status_code == 503
    data = res.get_json()
    assert data["status"] == "degraded"
    assert data["operational"] is False
    assert "gldas" in data["missing_required_layers"]


def test_datasets_endpoint(client):
    res = client.get("/api/datasets")
    assert res.status_code == 200
    data = res.get_json()
    assert "gldas" in data
    assert "merra2" in data
    assert "hwsd" in data
    assert data["gldas"]["required"] is True
    assert data["gldas"]["loaded"] is True


def test_indicators_endpoint(client):
    res = client.get("/api/indicators")
    assert res.status_code == 200
    data = res.get_json()
    assert "air_temperature" in data
    assert "rainfall" in data
    assert "root_moisture" in data


def test_provenance_endpoint(client):
    res = client.get("/api/provenance")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, dict)


def test_region_endpoint(client):
    # Nagpur coordinates
    res = client.get("/api/region?lat=21.1458&lon=79.0882")
    assert res.status_code == 200
    data = res.get_json()
    assert data["state"] == "Maharashtra"
    assert data["is_union_territory"] is False

    # Out of India coordinates
    res_out = client.get("/api/region?lat=51.5074&lon=-0.1278")
    assert res_out.status_code == 422
    assert res_out.get_json()["code"] == "OUT_OF_INDIA"

    # Missing parameters
    res_bad = client.get("/api/region")
    assert res_bad.status_code == 400


def test_crops_endpoint(client):
    res = client.get("/api/crops")
    assert res.status_code == 200
    data = res.get_json()
    assert "wheat" in data
    assert "rice" in data
    assert "cotton" in data
    assert "rabi" in data["wheat"]["seasons"]


def test_economics_coverage_endpoint(client):
    res = client.get("/api/economics/coverage")
    assert res.status_code == 200
    data = res.get_json()
    assert data["total_cost_records"] > 0
    assert data["crops_count"] >= 15
    assert "wheat" in data["coverage_matrix"]


def test_assess_general_mode(client):
    # Nagpur, Maharashtra (21.1458, 79.0882)
    res = client.get("/api/assess?lat=21.1458&lon=79.0882")
    assert res.status_code == 200
    data = res.get_json()

    assert "location" in data
    assert data["location"]["region"]["state"] == "Maharashtra"
    assert "overall" in data
    assert data["overall"]["rating"] in ["GOOD", "MODERATE", "POOR"]
    assert 0.0 <= data["overall"]["score"] <= 100.0

    assert "factors" in data
    assert "temperature" in data["factors"]
    assert "moisture" in data["factors"]
    assert "soil_ph" in data["factors"]
    assert "soil_quality" in data["factors"]
    assert "climate" in data["factors"]

    assert "suited_crops" in data
    assert len(data["suited_crops"]) > 0
    assert "rankings" in data
    assert "balanced_pick" in data["rankings"]

    assert "economics" in data
    assert data["economics"]["currency"] == "INR"

    assert "industry_factors" in data
    assert "meta" in data
    assert data["meta"]["query_ms"] >= 0


def test_assess_specific_crop_and_irrigated(client):
    res = client.get("/api/assess?lat=21.1458&lon=79.0882&crop=wheat&irrigation=irrigated&tenure=leased&cost_basis=c2")
    assert res.status_code == 200
    data = res.get_json()
    assert data["mode"]["crop"] == "wheat"
    assert data["mode"]["irrigation"] == "irrigated"
    assert data["economics"]["crop"] == "wheat"
    assert data["economics"]["cost_basis"] == "c2"


def test_assess_out_of_india(client):
    # London, UK
    res = client.get("/api/assess?lat=51.5074&lon=-0.1278")
    assert res.status_code == 422
    data = res.get_json()
    assert data["code"] == "OUT_OF_INDIA"
    assert "India only" in data["error"]


def test_assess_bad_parameters(client):
    # Missing coordinates
    res1 = client.get("/api/assess")
    assert res1.status_code == 400

    # Invalid irrigation
    res2 = client.get("/api/assess?lat=21.1458&lon=79.0882&irrigation=invalid_type")
    assert res2.status_code == 400


def test_assess_required_layers_missing():
    empty_store = CubeStore()
    app = create_app()
    app.config["TESTING"] = True
    app.extensions["cubes"] = empty_store
    c = app.test_client()

    res = c.get("/api/assess?lat=21.1458&lon=79.0882")
    assert res.status_code == 503
    assert res.get_json()["code"] == "REQUIRED_LAYERS_MISSING"


def test_economics_get_and_post(client):
    # GET
    res_get = client.get("/api/economics?lat=21.1458&lon=79.0882&crop=wheat&area_ha=2.5")
    assert res_get.status_code == 200
    data_get = res_get.get_json()
    assert data_get["crop"] == "wheat"
    assert data_get["available"] is True
    assert data_get["area_ha"] == 2.5

    # POST with scenario overrides
    payload = {
        "lat": 21.1458,
        "lon": 79.0882,
        "crop": "wheat",
        "area_ha": 2.0,
        "yield_override_q_ha": 45.0,
        "cost_multiplier": 1.15
    }
    res_post = client.post("/api/economics", json=payload)
    assert res_post.status_code == 200
    data_post = res_post.get_json()
    assert data_post["crop"] == "wheat"
    assert data_post["yield"]["expected_q_ha"] == 45.0
    assert data_post["area_ha"] == 2.0


def test_analyze_endpoint(client):
    # Air temperature trend
    res = client.get("/api/analyze?lat=21.1458&lon=79.0882&indicator=air_temperature&source=gldas")
    assert res.status_code == 200
    data = res.get_json()
    assert data["indicator"] == "air_temperature"
    assert data["p_value"] is not None
    assert "sens_slope_per_decade" in data

    # Out of India
    res_out = client.get("/api/analyze?lat=51.5074&lon=-0.1278&indicator=air_temperature")
    assert res_out.status_code == 422
    assert res_out.get_json()["code"] == "OUT_OF_INDIA"

    # Unknown indicator
    res_unk = client.get("/api/analyze?lat=21.1458&lon=79.0882&indicator=super_growth")
    assert res_unk.status_code == 400


def test_consensus_endpoint(client):
    res = client.get("/api/consensus?lat=21.1458&lon=79.0882&group=temperature")
    assert res.status_code == 200
    data = res.get_json()
    assert data["group"] == "temperature"
    assert "consensus_level" in data

    # Unknown group
    res_unk = client.get("/api/consensus?lat=21.1458&lon=79.0882&group=unknown_group")
    assert res_unk.status_code == 400
