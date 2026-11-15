"""Shared pytest fixtures, synthetic mini-cubes, and test doubles for TeraTrend."""
import json
from pathlib import Path
import sys
from typing import Any, Dict, List
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, Polygon, box
import xarray as xr

# Ensure backend directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import Config
from teratrend.cube_store import CubeStore
from teratrend.schemas import Region


@pytest.fixture(scope="session")
def synthetic_india_polygon():
    """Create a synthetic MultiPolygon with mainland, notch, and an island."""
    # Mainland: (70 to 80 E, 10 to 20 N) with a notch on west coast
    mainland_coords = [
        (70.0, 10.0), (70.0, 14.0), (72.0, 15.0), (70.0, 16.0),
        (70.0, 20.0), (80.0, 20.0), (80.0, 10.0), (70.0, 10.0)
    ]
    mainland = Polygon(mainland_coords)
    # Small island near (75.0, 8.0)
    island_coords = [(74.5, 7.5), (74.5, 8.5), (75.5, 8.5), (75.5, 7.5), (74.5, 7.5)]
    island = Polygon(island_coords)
    return MultiPolygon([mainland, island])


@pytest.fixture(scope="session")
def synthetic_grid_and_store(synthetic_india_polygon, tmp_path_factory):
    """Build synthetic mini-cubes for every dataset and an in-memory CubeStore."""
    tmp_dir = tmp_path_factory.mktemp("cubes")

    # Coordinate domain: lats 7.0 to 20.0 step 0.25 (53 lats), lons 70.0 to 81.0 step 0.25 (45 lons)
    lats = np.arange(7.0, 20.0 + 0.25, 0.25)
    lons = np.arange(70.0, 81.0 + 0.25, 0.25)
    n_lat = len(lats)
    n_lon = len(lons)

    # 1. India mask grid
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    india_mask = np.zeros((n_lat, n_lon), dtype=bool)
    from shapely.geometry import Point
    for i in range(n_lat):
        for j in range(n_lon):
            pt = Point(lons[j], lats[i])
            if synthetic_india_polygon.contains(pt) or synthetic_india_polygon.intersects(pt):
                india_mask[i, j] = True

    grid_ds = xr.Dataset(
        data_vars={
            "india_mask": (["lat", "lon"], india_mask.astype(np.int8)),
            "state_id": (["lat", "lon"], np.where(india_mask, 1, -1).astype(np.int16))
        },
        coords={"lat": lats, "lon": lons}
    )
    grid_path = tmp_dir / "india_grid.nc"
    grid_ds.to_netcdf(grid_path)

    # Monthly time axis for 15 years (2010 to 2024 = 180 months)
    times = pd.date_range("2010-01-01", "2024-12-31", freq="MS")
    n_time = len(times)

    # Define land-surface NaN mask: an island cell at (lat=8.0, lon=75.0) where land-surface is NaN
    # but atmospheric is valid!
    island_lat_idx = int(np.where(lats == 8.0)[0][0])
    island_lon_idx = int(np.where(lons == 75.0)[0][0])

    land_valid_mask = np.copy(india_mask)
    land_valid_mask[island_lat_idx, island_lon_idx] = False  # Small island cell marked water in LSM

    # 2. GLDAS mini-cube
    # Controllable warming trend: +0.03 K / year
    t_trend = np.linspace(0, 0.45, n_time)
    base_t = (298.15 + t_trend[:, None, None]).repeat(n_lat, axis=1).repeat(n_lon, axis=2).astype(np.float32)  # ~25°C
    base_rf = np.full((n_time, n_lat, n_lon), 3.5e-5, dtype=np.float32)  # ~90 mm/month
    base_moist = np.full((n_time, n_lat, n_lon), 180.0, dtype=np.float32)     # kg/m^2
    base_ev = np.full((n_time, n_lat, n_lon), 2.0e-5, dtype=np.float32)

    gldas_t = np.where(land_valid_mask[None, :, :], base_t, np.nan).astype(np.float32)
    gldas_rf = np.where(land_valid_mask[None, :, :], base_rf, np.nan).astype(np.float32)
    gldas_sm = np.where(land_valid_mask[None, :, :], base_moist, np.nan).astype(np.float32)
    gldas_ev = np.where(land_valid_mask[None, :, :], base_ev, np.nan).astype(np.float32)

    gldas_ds = xr.Dataset(
        data_vars={
            "air_temperature": (["time", "lat", "lon"], gldas_t),
            "rainfall": (["time", "lat", "lon"], gldas_rf),
            "root_moisture": (["time", "lat", "lon"], gldas_sm),
            "surface_moisture": (["time", "lat", "lon"], gldas_sm * 0.2),
            "evapotranspiration": (["time", "lat", "lon"], gldas_ev)
        },
        coords={"time": times, "lat": lats, "lon": lons}
    )
    gldas_ds.to_netcdf(tmp_dir / "gldas_cube.nc")

    # 3. MERRA-2 mini-cube (Atmospheric set: covers island cell too!)
    m2_t = np.where(india_mask[None, :, :], base_t + 0.2, np.nan).astype(np.float32)
    m2_rf = np.where(india_mask[None, :, :], base_rf * 0.98, np.nan).astype(np.float32)
    m2_wet = np.where(india_mask[None, :, :], np.full((n_time, n_lat, n_lon), 0.50, dtype=np.float32), np.nan).astype(np.float32)
    merra2_ds = xr.Dataset(
        data_vars={
            "air_temperature": (["time", "lat", "lon"], m2_t),
            "rainfall": (["time", "lat", "lon"], m2_rf),
            "root_moisture": (["time", "lat", "lon"], m2_wet),
            "surface_moisture": (["time", "lat", "lon"], m2_wet * 0.8),
            "evapotranspiration": (["time", "lat", "lon"], m2_rf * 0.6)
        },
        coords={"time": times, "lat": lats, "lon": lons}
    )
    merra2_ds.to_netcdf(tmp_dir / "merra2_cube.nc")

    # 4. GPM mini-cube (precipitation in mm/hr)
    gpm_rf_rate = 0.12  # mm/hr
    gpm_data = np.where(india_mask[None, :, :], np.full((n_time, n_lat, n_lon), gpm_rf_rate, dtype=np.float32), np.nan).astype(np.float32)
    gpm_ds = xr.Dataset(
        data_vars={"rainfall": (["time", "lat", "lon"], gpm_data)},
        coords={"time": times, "lat": lats, "lon": lons}
    )
    gpm_ds.to_netcdf(tmp_dir / "gpm_cube.nc")

    # 5. MODIS mini-cube (NDVI, EVI) with slight trend (raw unscaled MODIS values 5000 to 7500)
    ndvi_trend = np.linspace(5000.0, 7500.0, n_time)[:, None, None].repeat(n_lat, axis=1).repeat(n_lon, axis=2).astype(np.float32)
    modis_ndvi = np.where(land_valid_mask[None, :, :], ndvi_trend, np.nan).astype(np.float32)
    modis_ds = xr.Dataset(
        data_vars={"ndvi": (["time", "lat", "lon"], modis_ndvi)},
        coords={"time": times, "lat": lats, "lon": lons}
    )
    modis_ds.to_netcdf(tmp_dir / "modis_cube.nc")

    # 6. AIRS mini-cube
    airs_t = np.where(india_mask[None, :, :], base_t - 0.1, np.nan).astype(np.float32)
    rh_trend = np.linspace(60.0, 70.0, n_time)[:, None, None].repeat(n_lat, axis=1).repeat(n_lon, axis=2).astype(np.float32)
    airs_rh = np.where(india_mask[None, :, :], rh_trend, np.nan).astype(np.float32)
    airs_ds = xr.Dataset(
        data_vars={
            "air_temperature": (["time", "lat", "lon"], airs_t),
            "surface_humidity": (["time", "lat", "lon"], airs_rh)
        },
        coords={"time": times, "lat": lats, "lon": lons}
    )
    airs_ds.to_netcdf(tmp_dir / "airs_cube.nc")

    # 7. OMI mini-cube
    no2_trend = np.linspace(2.0, 3.0, n_time)[:, None, None].repeat(n_lat, axis=1).repeat(n_lon, axis=2).astype(np.float32)
    o3_trend = np.linspace(270.0, 290.0, n_time)[:, None, None].repeat(n_lat, axis=1).repeat(n_lon, axis=2).astype(np.float32)
    omi_no2 = np.where(india_mask[None, :, :], no2_trend, np.nan).astype(np.float32)
    omi_o3 = np.where(india_mask[None, :, :], o3_trend, np.nan).astype(np.float32)
    omi_ds = xr.Dataset(
        data_vars={
            "no2": (["time", "lat", "lon"], omi_no2),
            "ozone": (["time", "lat", "lon"], omi_o3)
        },
        coords={"time": times, "lat": lats, "lon": lons}
    )
    omi_ds.to_netcdf(tmp_dir / "omi_cube.nc")

    # 8. HWSD Static Soil mini-cube
    hwsd_ds = xr.Dataset(
        data_vars={
            "soil_ph_top": (["lat", "lon"], np.where(land_valid_mask, 6.8, np.nan).astype(np.float32)),
            "soil_ph_sub": (["lat", "lon"], np.where(land_valid_mask, 7.0, np.nan).astype(np.float32)),
            "soil_organic_carbon": (["lat", "lon"], np.where(land_valid_mask, 1.2, np.nan).astype(np.float32)),
            "soil_cec": (["lat", "lon"], np.where(land_valid_mask, 18.0, np.nan).astype(np.float32)),
            "soil_sand": (["lat", "lon"], np.where(land_valid_mask, 40.0, np.nan).astype(np.float32)),
            "soil_silt": (["lat", "lon"], np.where(land_valid_mask, 35.0, np.nan).astype(np.float32)),
            "soil_clay": (["lat", "lon"], np.where(land_valid_mask, 25.0, np.nan).astype(np.float32)),
            "soil_salinity": (["lat", "lon"], np.where(land_valid_mask, 1.2, np.nan).astype(np.float32)),
            "soil_sodicity": (["lat", "lon"], np.where(land_valid_mask, 4.0, np.nan).astype(np.float32)),
            "soil_gravel": (["lat", "lon"], np.where(land_valid_mask, 5.0, np.nan).astype(np.float32)),
        },
        coords={"lat": lats, "lon": lons}
    )
    hwsd_ds.to_netcdf(tmp_dir / "hwsd_cube.nc")

    # Initialize CubeStore with tmp_dir
    store = CubeStore(tmp_dir)
    store.load_all()
    return store, tmp_dir
