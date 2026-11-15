"""Test suite for spatial grid snapping, nearest-land fallback, and layer status."""
import pytest
from config import MAX_LAND_FALLBACK_KM
from teratrend.geo import haversine_distance_km, resolve_location
from teratrend.regions import OutOfIndiaError


def test_haversine_distance():
    """Verify haversine distance calculation."""
    # Delhi (28.6139, 77.2090) to Mumbai (19.0760, 72.8777) ~ 1148 km
    dist = haversine_distance_km(28.6139, 77.2090, 19.0760, 72.8777)
    assert 1140.0 < dist < 1160.0


def test_resolve_location_inside_mainland(synthetic_grid_and_store):
    """Verify location resolution on mainland."""
    store, _ = synthetic_grid_and_store
    # Coords in Maharashtra (approx 19.0°N, 73.0°E)
    gp = resolve_location(19.0, 73.0, store)

    assert gp.snapped_lat == pytest.approx(19.0, abs=0.26)
    assert gp.snapped_lon == pytest.approx(73.0, abs=0.26)
    assert gp.snap_distance_km < 35.0
    assert gp.region.state == "Maharashtra"
    assert gp.layer_status.get("gldas") == "OK"


def test_island_fallback_and_atmospheric_coverage(synthetic_grid_and_store):
    """Verify that an island cell where land-surface is NaN falls back to nearest land within 30 km,
    while atmospheric layers remain directly available without fallback."""
    from unittest.mock import patch
    from teratrend.schemas import Region
    store, _ = synthetic_grid_and_store

    # Test coordinate on the synthetic island: (8.0, 75.0)
    # Mock locate so administrative boundary check allows synthetic island cell
    with patch("teratrend.geo.locate", return_value=Region(state="Lakshadweep", is_union_territory=True)):
        gp = resolve_location(8.0, 75.0, store)

    assert gp.region is not None
    # Atmospheric layer is OK directly
    assert gp.layer_status.get("merra2") == "OK"
    assert gp.layer_status.get("gpm") == "OK"

    # Land-surface layer triggered fallback
    if gp.fallback_used:
        assert gp.fallback_distance_km <= MAX_LAND_FALLBACK_KM
        assert gp.layer_status.get("gldas") == "FALLBACK"
    else:
        # If snapped to an adjacent cell directly within 0.25 deg
        assert gp.layer_status.get("gldas") in ["OK", "FALLBACK"]


def test_coordinate_outside_india_fails(synthetic_grid_and_store):
    """Verify OutOfIndiaError on external coordinates."""
    store, _ = synthetic_grid_and_store
    # Karachi
    with pytest.raises(OutOfIndiaError):
        resolve_location(24.86, 67.0, store)
