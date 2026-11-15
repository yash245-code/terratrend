"""Tests for pipeline dataset source handlers (OMI and HWSD).
"""
import pytest
import numpy as np
import xarray as xr
from pathlib import Path
from backend.pipeline.sources.omi import OMISource
from backend.pipeline.sources.hwsd import HWSDSource


def test_omi_daily_aggregation_min_valid_days(tmp_path):
    # Create target grid
    lats = np.array([20.0, 20.25], dtype=np.float32)
    lons = np.array([78.0, 78.25], dtype=np.float32)
    india_mask = np.ones((2, 2), dtype=bool)

    target_grid = xr.Dataset(
        data_vars={"india_mask": (("lat", "lon"), india_mask)},
        coords={"lat": lats, "lon": lons}
    )

    omi_dir = tmp_path / "raw_omi"
    omi_dir.mkdir()

    # Create 5 daily dummy files for 2020-05
    for day in range(1, 6):
        fn = omi_dir / f"OMI-Aura_L3-OMNO2d_2020m050{day}_v003.nc"
        da = xr.DataArray(
            np.full((2, 2), 2.5e15, dtype=np.float32),
            coords={"lat": lats, "lon": lons},
            dims=["lat", "lon"],
            name="ColumnAmountNO2TropCloudScreened"
        )
        ds = xr.Dataset({"ColumnAmountNO2TropCloudScreened": da})
        ds.to_netcdf(fn)

    src = OMISource()

    # With min_valid_days = 6 (more than 5 days available), result should be NaN
    cube_high_threshold = src.to_cube(omi_dir, target_grid, min_valid_days=6)
    assert np.isnan(cube_high_threshold["no2"].values).all()

    # With min_valid_days = 3 (we have 5 days), result should be valid and scaled by 1e-15
    cube_valid = src.to_cube(omi_dir, target_grid, min_valid_days=3)
    assert not np.isnan(cube_valid["no2"].values).any()
    # 2.5e15 * 1e-15 = 2.5
    assert np.isclose(cube_valid["no2"].values[0, 0, 0], 2.5, atol=1e-3)


def test_hwsd_attribute_handling(tmp_path):
    lats = np.array([20.0, 20.25], dtype=np.float32)
    lons = np.array([78.0, 78.25], dtype=np.float32)
    india_mask = np.ones((2, 2), dtype=bool)

    target_grid = xr.Dataset(
        data_vars={"india_mask": (("lat", "lon"), india_mask)},
        coords={"lat": lats, "lon": lons}
    )

    hwsd_dir = tmp_path / "raw_hwsd"
    hwsd_dir.mkdir()

    # Create synthetic HWSD file with T_PH_H2O
    ph_file = hwsd_dir / "HWSD.T_PH_H2O.nc4"
    da_ph = xr.DataArray(
        np.full((2, 2), 6.5, dtype=np.float32),
        coords={"lat": lats, "lon": lons},
        dims=["lat", "lon"],
        name="T_PH_H2O"
    )
    xr.Dataset({"T_PH_H2O": da_ph}).to_netcdf(ph_file)

    src = HWSDSource()
    cube = src.to_cube(hwsd_dir, target_grid)

    assert "soil_ph_top" in cube
    assert np.isclose(cube["soil_ph_top"].values[0, 0], 6.5)
    # Default fallback filled for other required variables
    assert "soil_organic_carbon" in cube
    assert "soil_cec" in cube
