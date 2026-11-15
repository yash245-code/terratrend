"""Tests for protected Admin endpoints and token authorization."""
from __future__ import annotations

import pytest
from app import create_app
from config import Config


@pytest.fixture
def admin_client():
    """Create test client configured with an ADMIN_TOKEN."""
    app = create_app()
    app.config["TESTING"] = True
    Config.ADMIN_TOKEN = "secret-teratrend-admin-key-2026"
    with app.test_client() as client:
        yield client
    Config.ADMIN_TOKEN = ""


def test_admin_auth_forbidden_without_token(admin_client):
    """Verify admin endpoints reject unauthorized callers with 403."""
    res1 = admin_client.post("/api/admin/reload-reference")
    assert res1.status_code == 403

    res2 = admin_client.post("/api/admin/cache/clear")
    assert res2.status_code == 403

    res3 = admin_client.get("/api/admin/data-health")
    assert res3.status_code == 403


def test_admin_auth_success_with_valid_token(admin_client):
    """Verify operations succeed when presented with valid X-Admin-Token."""
    headers = {"X-Admin-Token": "secret-teratrend-admin-key-2026"}

    # 1. Data health check
    res_health = admin_client.get("/api/admin/data-health", headers=headers)
    assert res_health.status_code == 200
    health_data = res_health.get_json()
    assert health_data["status"] == "healthy"
    assert "counts" in health_data

    # 2. Clear cache
    res_clear = admin_client.post("/api/admin/cache/clear", headers=headers)
    assert res_clear.status_code == 200
    assert res_clear.get_json()["status"] == "cleared"

    # 3. Reload reference cache
    res_reload = admin_client.post("/api/admin/reload-reference", headers=headers)
    assert res_reload.status_code == 200
    assert res_reload.get_json()["status"] == "reloaded"
