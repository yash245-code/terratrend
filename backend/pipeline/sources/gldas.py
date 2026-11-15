"""GLDAS Noah L4 Monthly 0.25° dataset source handler."""
import logging
from pathlib import Path
from typing import Any, List, Optional
import earthaccess
import numpy as np
import pandas as pd
import xarray as xr

from config import DATASETS
from pipeline.regrid import apply_india_mask
from pipeline.sources.base import DatasetSource

log = logging.getLogger("teratrend")


class GLDASSource(DatasetSource):
    """Source handler for GLDAS_NOAH025_M v2.1."""

    def __init__(self):
        super().__init__("gldas")

    def search(
        self,
        start_year: int,
        end_year: int,
        bbox: tuple = (68.0, 6.0, 98.0, 38.0)
    ) -> List[Any]:
        log.info(f"Searching GLDAS granules ({start_year}-{end_year}) over {bbox}...")
        results = earthaccess.search_data(
            short_name="GLDAS_NOAH025_M",
            version="2.1",
            temporal=(f"{start_year}-01-01", f"{end_year}-12-31"),
            bounding_box=bbox
        )
        log.info(f"Found {len(results)} GLDAS granules.")
        return results

    def fetch(
        self,
        granules: List[Any],
        out_dir: Path,
        backend: str = "auto"
    ) -> List[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Downloading {len(granules)} GLDAS granules to {out_dir}...")
        downloaded = earthaccess.download(granules, str(out_dir))
        return [Path(p) for p in downloaded if Path(p).exists()]

    def to_cube(
        self,
        raw_dir: Path,
        target_grid: xr.Dataset
    ) -> xr.Dataset:
        raw_files = sorted(list(raw_dir.glob("*.nc*")))
        if not raw_files:
            raise FileNotFoundError(f"No NetCDF files found in GLDAS raw directory: {raw_dir}")

        log.info(f"Processing {len(raw_files)} raw GLDAS files into cube...")
        target_lats = target_grid["lat"].values
        target_lons = target_grid["lon"].values
        india_mask = target_grid["india_mask"].values

        # Open and subset by coordinate
        datasets = []
        for rf in raw_files:
            try:
                ds = xr.open_dataset(rf)
                # Ensure lat and lon coordinate names match
                lat_key = "lat" if "lat" in ds.coords else "latitude"
                lon_key = "lon" if "lon" in ds.coords else "longitude"
                ds = ds.rename({lat_key: "lat", lon_key: "lon"})

                sub = ds.sel(
                    lat=slice(min(target_lats), max(target_lats)),
                    lon=slice(min(target_lons), max(target_lons))
                )
                datasets.append(sub)
            except Exception as e:
                log.warning(f"Error reading GLDAS granule {rf.name}: {e}")

        if not datasets:
            raise ValueError(f"Could not load any valid GLDAS datasets from {raw_dir}")

        merged = xr.concat(datasets, dim="time").sortby("time")

        # Map variables
        var_map = {
            "SoilMoi0_10cm_inst": "surface_moisture",
            "SoilMoi10_40cm_inst": "root_moisture",
            "Tair_f_inst": "air_temperature",
            "Rainf_f_tavg": "rainfall",
            "Evap_tavg": "evapotranspiration"
        }

        cube_vars = {}
        for rk, vk in var_map.items():
            if rk in merged.data_vars:
                cube_vars[vk] = merged[rk].interp(lat=target_lats, lon=target_lons, method="nearest")

        res_ds = xr.Dataset(data_vars=cube_vars, coords=target_grid.coords)
        # Apply India mask
        res_ds = apply_india_mask(res_ds, india_mask, land_masked=True)
        return res_ds
