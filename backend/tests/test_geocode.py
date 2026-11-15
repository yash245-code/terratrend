"""Tests for OpenStreetMap Nominatim geocoding client with India polygon filtering.
"""
from unittest.mock import MagicMock, patch
import pytest
from backend.teratrend.geocode import geocode, _GEOCODE_CACHE


def test_geocode_empty_query():
    res = geocode("   ")
    assert res["available"] is False
    assert "Empty search query" in res["reason"]


@patch("backend.teratrend.geocode.requests.get")
def test_geocode_success_inside_india(mock_get):
    _GEOCODE_CACHE.clear()

    # Mock response for "Nagpur"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "lat": "21.1458",
            "lon": "79.0882",
            "display_name": "Nagpur, Maharashtra, India",
            "type": "city",
            "importance": 0.8
        }
    ]
    mock_get.return_value = mock_resp

    res = geocode("Nagpur")
    assert res["available"] is True
    assert res["lat"] == 21.1458
    assert res["lon"] == 79.0882
    assert "OpenStreetMap Nominatim (non-NASA" in res["source"]
    assert mock_get.call_count == 1

    # Verify cache hit does not call requests.get again
    res2 = geocode("Nagpur")
    assert res2["available"] is True
    assert mock_get.call_count == 1


@patch("backend.teratrend.geocode.requests.get")
def test_geocode_outside_india_filtered(mock_get):
    _GEOCODE_CACHE.clear()

    # Mock response returning Paris coordinates
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "lat": "48.8566",
            "lon": "2.3522",
            "display_name": "Paris, France",
            "type": "city"
        }
    ]
    mock_get.return_value = mock_resp

    res = geocode("Paris")
    assert res["available"] is False
    assert "outside official Indian territory" in res["reason"]


@patch("backend.teratrend.geocode.requests.get")
def test_geocode_timeout_handling(mock_get):
    _GEOCODE_CACHE.clear()
    import requests
    mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

    res = geocode("SomeLocation")
    assert res["available"] is False
    assert "timed out" in res["reason"]
