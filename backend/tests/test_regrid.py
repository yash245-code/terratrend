"""Test suite for spatial regridding, masking, and categorical modal aggregation."""
import numpy as np
import pytest
import xarray as xr

from pipeline.regrid import (
    apply_india_mask, bilinear_interp_to_grid, coarsen_with_valid_fraction,
    mask_fill_values, modal_categorical_regrid
)


def test_coarsen_with_50pct_valid_rule():
    """Verify coarsen keeps cells with >= 50% valid pixels and drops cells with < 50%."""
    # 5x5 block = 25 cells
    # Case A: 13 valid cells out of 25 (> 50%) -> should keep mean
    block_a = np.full((5, 5), np.nan)
    block_a[:3, :4] = 10.0  # 12 cells
    block_a[3, 0] = 10.0    # 13 cells
    da_a = xr.DataArray(block_a, dims=["lat", "lon"])
    res_a = coarsen_with_valid_fraction(da_a, factor=5, min_valid_fraction=0.50)
    assert not np.isnan(res_a.values[0, 0])
    assert res_a.values[0, 0] == pytest.approx(10.0)

    # Case B: 10 valid cells out of 25 (< 50%) -> should become NaN
    block_b = np.full((5, 5), np.nan)
    block_b[:2, :5] = 10.0  # 10 cells
    da_b = xr.DataArray(block_b, dims=["lat", "lon"])
    res_b = coarsen_with_valid_fraction(da_b, factor=5, min_valid_fraction=0.50)
    assert np.isnan(res_b.values[0, 0])


def test_modal_categorical_regrid():
    """Verify categorical soil classes are aggregated by mode, never interpolated."""
    # 5x5 block with 18 cells of class 3 (clay loam) and 7 cells of class 1 (sand)
    block = np.full((5, 5), 3.0)
    block[:2, :3] = 1.0  # 6 cells of class 1
    block[2, 0] = 1.0    # 7 cells of class 1
    da = xr.DataArray(block, dims=["lat", "lon"], coords={"lat": np.arange(5), "lon": np.arange(5)})

    target_lats = np.array([2.0])
    target_lons = np.array([2.0])
    res = modal_categorical_regrid(da, target_lats, target_lons, factor=5)

    # Modal class must be 3.0 (most frequent)
    assert res.values[0, 0] == 3.0


def test_bilinear_no_extrapolation():
    """Verify bilinear interpolation sets out-of-bounds coordinates to NaN (no extrapolation)."""
    src_lats = np.array([10.0, 11.0, 12.0])
    src_lons = np.array([75.0, 76.0, 77.0])
    data = np.ones((3, 3))
    da = xr.DataArray(data, coords={"lat": src_lats, "lon": src_lons}, dims=["lat", "lon"])

    # Query out-of-bounds latitude (15.0)
    target_lats = np.array([10.5, 15.0])
    target_lons = np.array([75.5, 76.0])

    interp = bilinear_interp_to_grid(da, target_lats, target_lons)
    assert interp.sel(lat=10.5, lon=75.5).values == pytest.approx(1.0)
    assert np.isnan(interp.sel(lat=15.0, lon=76.0).values)


def test_india_mask_application():
    """Verify India mask sets cells outside India to NaN."""
    data = np.ones((3, 3))
    da = xr.DataArray(data, coords={"lat": [10.0, 11.0, 12.0], "lon": [75.0, 76.0, 77.0]}, dims=["lat", "lon"])
    mask = np.array([
        [True, True, False],
        [True, False, False],
        [False, False, False]
    ])

    masked = apply_india_mask(da, mask, land_masked=True)
    assert masked.values[0, 0] == 1.0
    assert np.isnan(masked.values[0, 2])
    assert np.isnan(masked.values[2, 2])
