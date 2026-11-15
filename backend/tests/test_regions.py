"""Test suite for administrative region lookup and sovereign India boundary validation."""
import pytest
from shapely.geometry import Point

from config import INDIA_STATES_GEOJSON
from teratrend.regions import (
    OutOfIndiaError, get_india_union_geometry, is_inside_india,
    load_boundaries, locate
)


def test_points_outside_india_rejected():
    """Verify coordinates outside India (Dhaka, Kathmandu, Colombo, Karachi) are rejected with OUT_OF_INDIA."""
    outside_coords = [
        ("Kathmandu", 27.7172, 85.3240),
        ("Dhaka", 23.8103, 90.4125),
        ("Colombo", 6.9271, 79.8612),
        ("Karachi", 24.8607, 67.0011)
    ]

    for name, lat, lon in outside_coords:
        with pytest.raises(OutOfIndiaError) as exc_info:
            locate(lat, lon)
        assert exc_info.value.code == "OUT_OF_INDIA"
        assert not is_inside_india(lat, lon)


def test_points_inside_india_accepted():
    """Verify points within Indian states are located correctly."""
    # Delhi (NCT of Delhi)
    delhi_reg = locate(28.6139, 77.2090)
    assert "delhi" in delhi_reg.state.lower()
    assert delhi_reg.is_union_territory is True

    # Nagpur (Maharashtra)
    nagpur_reg = locate(21.1458, 79.0882)
    assert nagpur_reg.state == "Maharashtra"
    assert nagpur_reg.is_union_territory is False


def test_leh_and_tawang_official_territory():
    """Verify Leh (Ladakh) and Tawang (Arunachal Pradesh) are officially accepted within India."""
    if not INDIA_STATES_GEOJSON.exists():
        pytest.skip("Official boundary file not present")

    # Leh, Ladakh
    leh = locate(34.1526, 77.5771)
    assert any(term in leh.state.lower() for term in ["ladakh", "jammu & kashmir"])

    # Tawang, Arunachal Pradesh
    tawang = locate(27.5861, 91.8594)
    assert "arunachal" in tawang.state.lower()
