"""TeraTrend pure regridding and spatial harmonization functions.

Implements area-mean coarsening with >=50% valid pixel rules, bilinear interpolation
without extrapolation, modal categorical regridding, and India masking logic.
Pure numerical functions. Does NOT import Flask or any network library.
"""
from typing import Optional, Union
import numpy as np
from scipy import stats
import xarray as xr


def mask_fill_values(
    da: xr.DataArray,
    fill_value: Union[float, int],
    valid_range: Optional[tuple] = None
) -> xr.DataArray:
    """Mask fill values and out-of-range numbers as NaN."""
    masked = xr.where(da == fill_value, np.nan, da)
    if valid_range is not None:
        vmin, vmax = valid_range
        masked = xr.where((masked < vmin) | (masked > vmax), np.nan, masked)
    return masked


def coarsen_with_valid_fraction(
    da: xr.DataArray,
    factor: int = 5,
    min_valid_fraction: float = 0.50
) -> xr.DataArray:
    """Coarsen high-resolution grid (e.g. MODIS 0.05° -> 0.25°) by factor.
    
    Requires at least min_valid_fraction (default 50%) valid non-NaN sub-pixels.
    Otherwise the aggregated cell is marked NaN.
    """
    valid_flag = (~np.isnan(da)).astype(float)
    valid_count = valid_flag.coarsen(lat=factor, lon=factor, boundary="trim").sum()
    total_cells = float(factor * factor)
    fraction = valid_count / total_cells

    # Mean over valid pixels
    summed = xr.where(np.isnan(da), 0.0, da).coarsen(lat=factor, lon=factor, boundary="trim").sum()
    mean_val = xr.where(valid_count > 0, summed / valid_count, np.nan)

    # Apply 50% valid rule
    coarsened = xr.where(fraction >= min_valid_fraction, mean_val, np.nan)
    return coarsened


def modal_categorical_regrid(
    da: xr.DataArray,
    target_lats: np.ndarray,
    target_lons: np.ndarray,
    factor: int = 5
) -> xr.DataArray:
    """Regrid discrete categorical fields (e.g. USDA texture class, drainage class) using modal class.
    
    Categorical classes are NEVER interpolated.
    """
    # Coarsen using mode
    def block_mode(block, axis=None, **kwargs):
        if axis is None:
            clean = block[~np.isnan(block)]
            return stats.mode(clean, keepdims=False).mode if len(clean) > 0 else np.nan
        if isinstance(axis, (tuple, list)):
            block = np.moveaxis(block, axis, range(-len(axis), 0))
            orig_shape = block.shape[:-len(axis)]
            reshaped = block.reshape(*orig_shape, -1)
            res = stats.mode(reshaped, axis=-1, nan_policy="omit", keepdims=False)
            return res.mode
        res = stats.mode(block, axis=axis, nan_policy="omit", keepdims=False)
        return res.mode

    # Use xarray coarsen with custom reducer or numpy block reduction
    coarsened = da.coarsen(lat=factor, lon=factor, boundary="trim").reduce(block_mode)
    # Ensure coordinates match target grid exactly
    aligned = coarsened.assign_coords(lat=target_lats[:len(coarsened.lat)], lon=target_lons[:len(coarsened.lon)])
    return aligned


def bilinear_interp_to_grid(
    da: xr.DataArray,
    target_lats: np.ndarray,
    target_lons: np.ndarray
) -> xr.DataArray:
    """Interpolate continuous field to canonical grid using bilinear interpolation without extrapolation."""
    # Ensure source coordinates are strictly monotonic
    if da.lat[0] > da.lat[-1]:
        da = da.reindex(lat=da.lat[::-1])
    if da.lon[0] > da.lon[-1]:
        da = da.reindex(lon=da.lon[::-1])

    # Bilinear interpolation
    interp = da.interp(
        lat=target_lats,
        lon=target_lons,
        method="linear",
        kwargs={"bounds_error": False, "fill_value": np.nan}
    )
    return interp


def apply_india_mask(
    ds_or_da: Union[xr.Dataset, xr.DataArray],
    india_mask: Union[np.ndarray, xr.DataArray],
    land_masked: bool = True
) -> Union[xr.Dataset, xr.DataArray]:
    """Apply sovereign India mask to grid.
    
    If land_masked=False (atmospheric sets: MERRA-2, GPM, AIRS, OMI),
    keeps cells in India valid even if land-surface models mark them water.
    """
    mask_da = xr.DataArray(
        india_mask.astype(bool),
        coords={"lat": ds_or_da.lat, "lon": ds_or_da.lon},
        dims=["lat", "lon"]
    )
    # Mask out-of-India cells to NaN
    return xr.where(mask_da, ds_or_da, np.nan)
