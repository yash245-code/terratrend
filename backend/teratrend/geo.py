"""TeraTrend geographic spatial resolution and grid snapping.

Handles point-in-polygon verification, nearest-grid snap on the 0.25° India grid,
haversine distance, and island / coastal nearest-land fallback within 30 km.
Does NOT import Flask or any network library.
"""
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from config import MAX_LAND_FALLBACK_KM
from teratrend.regions import OutOfIndiaError, locate
from teratrend.schemas import GridPoint, Region


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in kilometers."""
    r = 6371.0  # Earth's mean radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def find_nearest_india_cell(
    lat: float,
    lon: float,
    grid_lats: np.ndarray,
    grid_lons: np.ndarray,
    india_mask: np.ndarray
) -> Tuple[float, float, int, int, float]:
    """Find the nearest grid cell coordinate where india_mask is True.
    
    Returns:
        (snapped_lat, snapped_lon, lat_idx, lon_idx, distance_km)
    """
    # 2D coordinate mesh
    lon_grid, lat_grid = np.meshgrid(grid_lons, grid_lats)
    valid_mask = (india_mask == 1) | (india_mask == True)

    if not np.any(valid_mask):
        # Fallback to simple nearest coordinate if mask empty
        lat_idx = int(np.abs(grid_lats - lat).argmin())
        lon_idx = int(np.abs(grid_lons - lon).argmin())
        dist = haversine_distance_km(lat, lon, float(grid_lats[lat_idx]), float(grid_lons[lon_idx]))
        return float(grid_lats[lat_idx]), float(grid_lons[lon_idx]), lat_idx, lon_idx, dist

    # Compute Euclidean distance in degree space first to narrow down candidates
    deg_dist_sq = (lat_grid - lat) ** 2 + (lon_grid - lon) ** 2
    deg_dist_sq[~valid_mask] = np.inf

    best_flat = np.argmin(deg_dist_sq)
    best_lat_idx, best_lon_idx = np.unravel_index(best_flat, deg_dist_sq.shape)

    snapped_lat = float(grid_lats[best_lat_idx])
    snapped_lon = float(grid_lons[best_lon_idx])
    dist_km = haversine_distance_km(lat, lon, snapped_lat, snapped_lon)

    return snapped_lat, snapped_lon, int(best_lat_idx), int(best_lon_idx), dist_km


def resolve_location(
    lat: float,
    lon: float,
    store: Any,
    place_name: Optional[str] = None
) -> GridPoint:
    """Validate requested coordinates, check India sovereign boundary, and snap to 0.25° grid.
    
    Implements coastal and island nearest-land cell fallback within MAX_LAND_FALLBACK_KM (30 km)
    for land-surface datasets (GLDAS, HWSD, MODIS) while preserving full coverage for atmospheric
    datasets (MERRA-2, GPM, AIRS, OMI).
    """
    # 1. Range validation
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError(f"Invalid geographic coordinates: lat={lat}, lon={lon}")

    # 2. Region & Sovereign India validation
    region = locate(lat, lon)

    # 3. Retrieve grid coordinates and mask
    grid_lats = store.get_lats()
    grid_lons = store.get_lons()
    india_mask = store.get_india_mask()

    snapped_lat, snapped_lon, lat_idx, lon_idx, snap_dist_km = find_nearest_india_cell(
        lat, lon, grid_lats, grid_lons, india_mask
    )

    # 4. Check layer-wise validity & fallback for land-surface models
    layer_status: Dict[str, str] = {}
    fallback_used = False
    max_fallback_dist = 0.0

    land_surface_datasets = ["gldas", "hwsd", "modis"]
    atmospheric_datasets = ["merra2", "gpm", "airs", "omi"]

    # Atmospheric layers cover island/coastal cells directly
    for ds_name in atmospheric_datasets:
        if store.has_dataset(ds_name):
            layer_status[ds_name] = "OK"

    # For land-surface layers, check if snapped cell has valid data or requires fallback
    for ds_name in land_surface_datasets:
        if not store.has_dataset(ds_name):
            continue

        has_valid_data = store.check_cell_valid(ds_name, snapped_lat, snapped_lon)
        if has_valid_data:
            layer_status[ds_name] = "OK"
        else:
            # Search nearest valid land cell within MAX_LAND_FALLBACK_KM (30 km)
            fb_coord, fb_dist = store.find_nearest_valid_land_cell(
                ds_name, snapped_lat, snapped_lon, max_km=MAX_LAND_FALLBACK_KM
            )
            if fb_coord is not None and fb_dist <= MAX_LAND_FALLBACK_KM:
                fallback_used = True
                max_fallback_dist = max(max_fallback_dist, fb_dist)
                layer_status[ds_name] = "FALLBACK"
            else:
                layer_status[ds_name] = "NO_DATA"

    return GridPoint(
        requested_lat=lat,
        requested_lon=lon,
        snapped_lat=snapped_lat,
        snapped_lon=snapped_lon,
        snap_distance_km=snap_dist_km,
        region=region,
        place_name=place_name,
        fallback_used=fallback_used,
        fallback_distance_km=max_fallback_dist,
        layer_status=layer_status
    )
