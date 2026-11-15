"""OMI Level 3 Daily Tropospheric NO2 & Total Ozone source handler.

Aggregates daily Level 3 products to monthly cubes with incremental accumulators
and minimum valid day thresholds.
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import earthaccess
import numpy as np
import pandas as pd
import xarray as xr

from config import DATASETS
from pipeline.regrid import apply_india_mask, bilinear_interp_to_grid
from pipeline.sources.base import DatasetSource

log = logging.getLogger("teratrend")


class OMISource(DatasetSource):
    """Source handler for OMI Level 3 (OMNO2d / OMTO3d)."""

    def __init__(self):
        super().__init__("omi")

    def search(
        self,
        start_year: int,
        end_year: int,
        bbox: tuple = (68.0, 6.0, 98.0, 38.0)
    ) -> List[Any]:
        log.info(f"Searching OMI daily granules ({start_year}-{end_year})...")
        results = earthaccess.search_data(
            short_name="OMNO2d",
            version="003",
            temporal=(f"{start_year}-01-01", f"{end_year}-12-31"),
            bounding_box=bbox
        )
        log.info(f"Found {len(results)} OMI daily granules.")
        return results

    def fetch(
        self,
        granules: List[Any],
        out_dir: Path,
        backend: str = "auto"
    ) -> List[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        downloaded = earthaccess.download(granules, str(out_dir))
        return [Path(p) for p in downloaded if Path(p).exists()]

    def to_cube(
        self,
        raw_dir: Path,
        target_grid: xr.Dataset,
        min_valid_days: int = 10
    ) -> xr.Dataset:
        raw_files = sorted(list(raw_dir.glob("*.he5*")) + list(raw_dir.glob("*.nc*")))
        if not raw_files:
            raise FileNotFoundError(f"No OMI data files found in {raw_dir}")

        target_lats = target_grid["lat"].values
        target_lons = target_grid["lon"].values
        india_mask = target_grid["india_mask"].values

        log.info(f"Aggregating {len(raw_files)} daily OMI granules to monthly cube...")

        # Group raw files by year-month
        # Typical OMI filename: OMI-Aura_L3-OMNO2d_2020m0115_...
        month_groups: Dict[str, List[Path]] = {}
        for rf in raw_files:
            name = rf.name
            # Extract YYYY and MM
            parts = name.split("_")
            for p in parts:
                if len(p) == 9 and p[4] == "m":
                    ym = f"{p[:4]}-{p[5:7]}"
                    month_groups.setdefault(ym, []).append(rf)
                    break

        monthly_datasets = []
        for ym, files in sorted(month_groups.items()):
            # Incremental sum and count accumulators
            accum_sum = np.zeros((len(target_lats), len(target_lons)), dtype=float)
            accum_cnt = np.zeros((len(target_lats), len(target_lons)), dtype=int)

            for f in files:
                try:
                    ds = xr.open_dataset(f)
                    var_da = ds.get("ColumnAmountNO2TropCloudScreened")
                    if var_da is None:
                        var_da = ds.get("ColumnAmountNO2")
                    if var_da is not None:
                        # Clean fills
                        clean = xr.where((var_da < 0) | (var_da > 1e18), np.nan, var_da)
                        regridded = bilinear_interp_to_grid(clean, target_lats, target_lons)
                        vals = regridded.values
                        valid_mask = ~np.isnan(vals)
                        accum_sum[valid_mask] += vals[valid_mask]
                        accum_cnt[valid_mask] += 1
                except Exception as e:
                    log.warning(f"Error reading daily OMI file {f.name}: {e}")

            # Apply min_valid_days threshold
            valid_cell_mask = accum_cnt >= min_valid_days
            monthly_mean = np.where(valid_cell_mask, accum_sum / np.maximum(accum_cnt, 1), np.nan)
            # Convert units to 1e15 molec/cm^2
            monthly_mean_scaled = monthly_mean * 1e-15

            t_stamp = pd.to_datetime(f"{ym}-15")
            da_month = xr.DataArray(
                monthly_mean_scaled.astype(np.float32),
                coords={"lat": target_lats, "lon": target_lons},
                dims=["lat", "lon"]
            )
            monthly_datasets.append(da_month.expand_dims(time=[t_stamp]))

        if not monthly_datasets:
            raise ValueError(f"Could not aggregate any valid monthly OMI grids from {raw_dir}")

        merged = xr.concat(monthly_datasets, dim="time").sortby("time")
        res_ds = xr.Dataset(data_vars={"no2": merged}, coords=target_grid.coords)
        res_ds = apply_india_mask(res_ds, india_mask, land_masked=False)
        return res_ds
