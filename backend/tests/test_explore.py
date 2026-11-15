"""Tests for Spatial Exploration endpoints."""
from __future__ import annotations

import pytest
from app import create_app
from db.base import get_session
from db.repositories.grid_repo import GridRepository


@pytest.fixture
def explore_client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_explore_endpoints(explore_client):
    """Verify best-places and state-summary responses."""
    # Clean any previous test cell at this coordinate
    with get_session() as session:
        from sqlalchemy import delete
        from db.models.grid import GridCell
        session.execute(delete(GridCell).where(GridCell.cell_lat == 31.0, GridCell.cell_lon == 75.5))
        session.commit()

        repo = GridRepository(session)
        repo.bulk_insert_cells_and_scores([
            {
                "cell_lat": 31.0,
                "cell_lon": 75.5,
                "state_id": 1,
                "district_id": None,
                "overall_score": 85.0,
                "temperature_score": 80.0,
                "moisture_score": 85.0,
                "soil_ph_score": 90.0,
                "soil_quality_score": 85.0,
                "climate_score": 85.0,
                "data_version": "v1",
                "crop_scores": [
                    {"crop_key": "wheat", "suitability_score": 90.0, "roi_pct": 35.0, "probability_of_loss_pct": 8.0}
                ],
            }
        ])
        session.commit()

    # Best places query
    res1 = explore_client.get("/api/explore/best-places?crop=wheat&limit=5")
    assert res1.status_code == 200
    data1 = res1.get_json()
    assert data1["crop"] == "wheat"
    assert data1["count"] >= 1

    # State summary query
    res2 = explore_client.get("/api/explore/state-summary?crop=wheat")
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["crop"] == "wheat"
    assert "states" in data2
